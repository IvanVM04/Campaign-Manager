import sqlite3

import pytest

from database import transaction
from models.campaign_scope import CampaignScope
from models.turn_resolution_record import TurnResolutionRecord
from repositories.turn_resolution_repository import TurnResolutionRepository


def make_record(**overrides):
    values = {
        "campaign_id": 1,
        "player_input": "Abro la puerta.",
        "adapter_namespace": "native",
        "idempotency_key": "request-001",
        "request_fingerprint": "sha256:abc123",
    }
    values.update(overrides)
    return TurnResolutionRecord(**values)


def test_create_and_get_resolution(isolated_database):
    repository = TurnResolutionRepository()
    created = repository.create(make_record(), scope=CampaignScope(1))

    assert created.id is not None
    assert created.lifecycle_state == "accepted"
    assert created.attempt_count == 0

    loaded = repository.get(created.id, scope=CampaignScope(1))
    assert loaded == created


def test_idempotency_identity_is_unique_per_campaign_and_adapter(isolated_database):
    repository = TurnResolutionRepository()
    repository.create(make_record(), scope=CampaignScope(1))

    with pytest.raises(sqlite3.IntegrityError):
        repository.create(make_record(request_fingerprint="sha256:different"), scope=CampaignScope(1))

    with pytest.raises(sqlite3.IntegrityError):
        repository.create(make_record(), scope=CampaignScope(1))

    # The same key is independent in a distinct adapter namespace.
    other_adapter = repository.create(
        make_record(adapter_namespace="sillytavern"),
        scope=CampaignScope(1),
    )
    assert other_adapter.adapter_namespace == "sillytavern"


def test_same_idempotency_key_can_exist_in_another_campaign(isolated_database):
    from database import execute

    execute("INSERT INTO campaign (id, name) VALUES (?, ?)", (2, "Campaign 2"))
    repository = TurnResolutionRepository()
    repository.create(make_record(), scope=CampaignScope(1))
    second = repository.create(make_record(campaign_id=2), scope=CampaignScope(2))

    assert second.campaign_id == 2


def test_repository_rejects_scope_mismatch(isolated_database):
    repository = TurnResolutionRepository()
    with pytest.raises(ValueError, match="does not match"):
        repository.create(make_record(campaign_id=2), scope=CampaignScope(1))


def test_claim_and_transition_lifecycle(isolated_database):
    repository = TurnResolutionRepository()
    created = repository.create(make_record(), scope=CampaignScope(1))

    with transaction("IMMEDIATE") as conn:
        claimed = repository.claim_for_planning(
            created.id,
            scope=CampaignScope(1),
            lease_token="worker-a",
            lease_expires_at="2099-01-01T00:00:00Z",
            now="2026-11-04T00:00:00Z",
            conn=conn,
        )
        assert claimed.lifecycle_state == "planning"
        assert claimed.attempt_count == 1

        prepared = repository.transition(
            created.id,
            "prepared",
            scope=CampaignScope(1),
            expected_state="planning",
            expected_lease_token="worker-a",
            updates={
                "context_revision": 1,
                "proposal_json": '{"operations":[]}',
                "lease_token": None,
                "lease_expires_at": None,
            },
            conn=conn,
        )
        assert prepared.lifecycle_state == "prepared"

        committed = repository.transition(
            created.id,
            "committed",
            scope=CampaignScope(1),
            expected_state="prepared",
            updates={"committed_at": "2026-11-04T00:01:00Z"},
            conn=conn,
        )
        pending = repository.transition(
            created.id,
            "narration_pending",
            scope=CampaignScope(1),
            expected_state="committed",
            conn=conn,
        )
        completed = repository.transition(
            created.id,
            "completed",
            scope=CampaignScope(1),
            expected_state="narration_pending",
            updates={
                "narrative": "La puerta se abre.",
                "completed_at": "2026-11-04T00:02:00Z",
            },
            conn=conn,
        )

    assert completed.lifecycle_state == "completed"
    assert completed.narrative == "La puerta se abre."


def test_transition_rejects_skipping_commit_or_replaying_state(isolated_database):
    repository = TurnResolutionRepository()
    created = repository.create(make_record(), scope=CampaignScope(1))

    with transaction("IMMEDIATE") as conn:
        with pytest.raises(ValueError, match="claim_for_planning"):
            repository.transition(
                created.id,
                "planning",
                scope=CampaignScope(1),
                expected_state="accepted",
                conn=conn,
            )
        with pytest.raises(ValueError, match="invalid"):
            repository.transition(
                created.id,
                "completed",
                scope=CampaignScope(1),
                expected_state="accepted",
                conn=conn,
            )

    with transaction("IMMEDIATE") as conn:
        conn.execute(
            "UPDATE turn_resolutions SET lifecycle_state='committed' WHERE id=?",
            (created.id,),
        )
        with pytest.raises(ValueError, match="invalid"):
            repository.transition(
                created.id,
                "planning",
                scope=CampaignScope(1),
                expected_state="committed",
                conn=conn,
            )


def test_expired_planning_lease_can_be_reclaimed_but_active_lease_cannot(isolated_database):
    repository = TurnResolutionRepository()
    created = repository.create(make_record(), scope=CampaignScope(1))

    with transaction("IMMEDIATE") as conn:
        first = repository.claim_for_planning(
            created.id,
            scope=CampaignScope(1),
            lease_token="worker-a",
            lease_expires_at="2026-11-04T10:00:00Z",
            now="2026-11-04T09:59:00Z",
            conn=conn,
        )
        assert first.attempt_count == 1

    with transaction("IMMEDIATE") as conn:
        with pytest.raises(ValueError, match="not claimable"):
            repository.claim_for_planning(
                created.id,
                scope=CampaignScope(1),
                lease_token="worker-b",
                lease_expires_at="2026-11-04T10:02:00Z",
                now="2026-11-04T10:01:00Z",
                conn=conn,
            )

    with transaction("IMMEDIATE") as conn:
        second = repository.claim_for_planning(
            created.id,
            scope=CampaignScope(1),
            lease_token="worker-b",
            lease_expires_at="2026-11-04T10:03:00Z",
            now="2026-11-04T10:01:00Z",
            conn=conn,
        )
        assert second.attempt_count == 2
        assert second.lease_token == "worker-b"


def test_transition_requires_expected_state(isolated_database):
    repository = TurnResolutionRepository()
    created = repository.create(make_record(), scope=CampaignScope(1))

    with transaction("IMMEDIATE") as conn:
        with pytest.raises(ValueError, match="state changed"):
            repository.transition(
                created.id,
                "planning",
                scope=CampaignScope(1),
                expected_state="prepared",
                conn=conn,
            )


def test_resolution_is_campaign_scoped(isolated_database):
    from database import execute

    execute("INSERT INTO campaign (id, name) VALUES (?, ?)", (2, "Campaign 2"))
    repository = TurnResolutionRepository()
    created = repository.create(make_record(), scope=CampaignScope(1))

    assert repository.get(created.id, scope=CampaignScope(2)) is None
    assert repository.get_by_idempotency_key(
        "native", "request-001", scope=CampaignScope(2)
    ) is None
