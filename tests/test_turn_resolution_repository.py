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


def test_create_and_get_resolution_persists_shared_intent_json(isolated_database):
    repository = TurnResolutionRepository()
    intent_json = (
        '{"schema_version":1,"source_text":"Abro la puerta.",'
        '"analysis":{"schema_version":1}}'
    )
    created = repository.create(
        make_record(intent_json=intent_json),
        scope=CampaignScope(1),
    )

    loaded = repository.get(created.id, scope=CampaignScope(1))

    assert created.intent_json == intent_json
    assert loaded.intent_json == intent_json



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

        repository.transition(
            created.id,
            "committed",
            scope=CampaignScope(1),
            expected_state="prepared",
            updates={"committed_at": "2026-11-04T00:01:00Z", "resulting_revision": 2},
            conn=conn,
        )
        repository.transition(
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
    assert completed.resulting_revision == 2

    with transaction("IMMEDIATE") as conn, pytest.raises(
        sqlite3.IntegrityError, match="evidence is immutable"
    ):
        conn.execute(
            "UPDATE turn_resolutions SET proposal_json='{\"operations\":[{}]}' WHERE id=?",
            (created.id,),
        )


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

    with transaction("IMMEDIATE") as conn, pytest.raises(
        sqlite3.IntegrityError, match="invalid"
    ):
        conn.execute(
                "UPDATE turn_resolutions SET lifecycle_state='committed', committed_at='2026-11-04T00:01:00Z', resulting_revision=2 WHERE id=?",
                (created.id,),
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

    with transaction("IMMEDIATE") as conn, pytest.raises(
        ValueError, match="not claimable"
    ):
        repository.claim_for_planning(
                created.id,
                scope=CampaignScope(1),
                lease_token="worker-b",
                lease_expires_at="2026-11-04T10:02:00Z",
                now="2026-11-04T09:59:30Z",
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

    with transaction("IMMEDIATE") as conn, pytest.raises(
        ValueError, match="state changed"
    ):
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

def test_reclaimed_planning_lease_fences_out_late_worker(isolated_database):
    repository = TurnResolutionRepository()
    created = repository.create(make_record(), scope=CampaignScope(1))

    with transaction("IMMEDIATE") as conn:
        first = repository.claim_for_planning(
            created.id, scope=CampaignScope(1), lease_token="worker-a",
            lease_expires_at="2026-11-04T10:00:00Z",
            now="2026-11-04T09:59:00Z", conn=conn,
        )

    with transaction("IMMEDIATE") as conn:
        reclaimed = repository.claim_for_planning(
            created.id, scope=CampaignScope(1), lease_token="worker-b",
            lease_expires_at="2026-11-04T10:03:00Z",
            now="2026-11-04T10:01:00Z", conn=conn,
        )

    assert first.lease_token == "worker-a"
    assert reclaimed.lease_token == "worker-b"
    assert reclaimed.attempt_count == 2

    with transaction("IMMEDIATE") as conn, pytest.raises(
        ValueError, match="planning lease was superseded"
    ):
        repository.transition(
            created.id, "prepared", scope=CampaignScope(1),
            expected_state="planning", expected_lease_token="worker-a",
            updates={"context_revision": 1}, conn=conn,
        )

    with transaction("IMMEDIATE") as conn:
        prepared = repository.transition(
            created.id, "prepared", scope=CampaignScope(1),
            expected_state="planning", expected_lease_token="worker-b",
            updates={
                "context_revision": 1,
                "proposal_json": '{"operations":[]}',
                "lease_token": None,
                "lease_expires_at": None,
            },
            conn=conn,
        )

    assert prepared.lifecycle_state == "prepared"
    assert prepared.lease_token is None



def _empty_action_checkpoint(resolution_id, source_text, revision, marker):
    import hashlib

    from models.player_action_checkpoint import PlayerActionCheckpoint

    return PlayerActionCheckpoint(
        resolution_id=resolution_id,
        context_revision=revision,
        source_sha256=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        interpretation_sha256=hashlib.sha256(marker.encode("utf-8")).hexdigest(),
        nodes=(),
    )


def test_action_checkpoint_is_saved_with_context_and_lease_cas(isolated_database):
    repository = TurnResolutionRepository()
    created = repository.create(make_record(), scope=CampaignScope(1))
    with transaction("IMMEDIATE") as conn:
        claimed = repository.claim_for_planning(
            created.id,
            scope=CampaignScope(1),
            lease_token="worker-a",
            lease_expires_at="2099-01-01T00:00:00Z",
            now="2026-11-20T10:00:00Z",
            conn=conn,
        )
    checkpoint = _empty_action_checkpoint(
        created.id, created.player_input, 3, "interpretation-v1"
    ).to_json()

    with transaction("IMMEDIATE") as conn:
        saved = repository.save_action_checkpoint(
            created.id,
            checkpoint,
            scope=CampaignScope(1),
            expected_state="planning",
            expected_lease_token="worker-a",
            expected_context_revision=None,
            expected_checkpoint_json=None,
            now="2026-11-20T10:00:00Z",
            conn=conn,
        )

    assert saved.action_checkpoint_json == checkpoint
    assert saved.context_revision == 3
    assert claimed.lease_token == "worker-a"
    assert repository.get(created.id, scope=CampaignScope(1)).action_checkpoint_json == checkpoint


def test_action_checkpoint_compare_and_swap_rejects_stale_revision_checkpoint_and_lease(
    isolated_database,
):
    repository = TurnResolutionRepository()
    created = repository.create(make_record(), scope=CampaignScope(1))
    with transaction("IMMEDIATE") as conn:
        repository.claim_for_planning(
            created.id,
            scope=CampaignScope(1),
            lease_token="worker-a",
            lease_expires_at="2099-01-01T00:00:00Z",
            now="2026-11-20T10:00:00Z",
            conn=conn,
        )
    checkpoint = _empty_action_checkpoint(
        created.id, created.player_input, 3, "interpretation-v1"
    ).to_json()
    with transaction("IMMEDIATE") as conn:
        repository.save_action_checkpoint(
            created.id, checkpoint, scope=CampaignScope(1),
            expected_state="planning", expected_lease_token="worker-a",
            expected_context_revision=None, expected_checkpoint_json=None,
            conn=conn,
        )

    updated_checkpoint = _empty_action_checkpoint(
        created.id, created.player_input, 3, "interpretation-v2"
    ).to_json()
    with transaction("IMMEDIATE") as conn, pytest.raises(
        ValueError, match="checkpoint changed"
    ):
        repository.save_action_checkpoint(
            created.id, updated_checkpoint, scope=CampaignScope(1),
            expected_state="planning", expected_lease_token="worker-a",
            expected_context_revision=3, expected_checkpoint_json="stale",
            now="2026-11-20T10:00:00Z", conn=conn,
        )

    with transaction("IMMEDIATE") as conn, pytest.raises(
        ValueError, match="lease was superseded"
    ):
        repository.save_action_checkpoint(
            created.id, updated_checkpoint, scope=CampaignScope(1),
            expected_state="planning", expected_lease_token="worker-b",
            expected_context_revision=3, expected_checkpoint_json=checkpoint,
            now="2026-11-20T10:00:00Z", conn=conn,
        )


def test_committed_action_checkpoint_is_immutable(isolated_database):
    repository = TurnResolutionRepository()
    created = repository.create(make_record(), scope=CampaignScope(1))
    with transaction("IMMEDIATE") as conn:
        repository.claim_for_planning(
            created.id,
            scope=CampaignScope(1),
            lease_token="worker-a",
            lease_expires_at="2099-01-01T00:00:00Z",
            now="2026-11-20T10:00:00Z",
            conn=conn,
        )
    checkpoint = _empty_action_checkpoint(
        created.id, created.player_input, 3, "interpretation-v1"
    ).to_json()
    with transaction("IMMEDIATE") as conn:
        repository.save_action_checkpoint(
            created.id, checkpoint, scope=CampaignScope(1),
            expected_state="planning", expected_lease_token="worker-a",
            expected_context_revision=None, expected_checkpoint_json=None,
            conn=conn,
        )
        prepared = repository.transition(
            created.id, "prepared", scope=CampaignScope(1),
            expected_state="planning", expected_lease_token="worker-a",
            updates={
                "proposal_json": '{"operations":[]}',
                "lease_token": None,
                "lease_expires_at": None,
            },
            conn=conn,
        )
        committed = repository.transition(
            created.id, "committed", scope=CampaignScope(1),
            expected_state="prepared",
            updates={
                "committed_at": "2026-11-20T10:01:00Z",
                "resulting_revision": 4,
            },
            conn=conn,
        )
    assert prepared.lifecycle_state == "prepared"
    assert committed.lifecycle_state == "committed"

    with transaction("IMMEDIATE") as conn, pytest.raises(
        sqlite3.IntegrityError, match="action checkpoint is immutable"
    ):
        conn.execute(
            "UPDATE turn_resolutions SET action_checkpoint_json=? WHERE id=?",
            ("{}", created.id),
        )



def test_action_checkpoint_cannot_be_written_through_generic_transition(isolated_database):
    repository = TurnResolutionRepository()
    created = repository.create(make_record(), scope=CampaignScope(1))

    with transaction("IMMEDIATE") as conn, pytest.raises(
        ValueError, match="unsupported update fields"
    ):
        repository.transition(
            created.id,
            "planning",
            scope=CampaignScope(1),
            expected_state="accepted",
            updates={"action_checkpoint_json": "{}"},
            conn=conn,
        )


def test_new_resolution_cannot_inject_checkpoint_before_claiming_lease(isolated_database):
    import hashlib

    from models.player_action_checkpoint import PlayerActionCheckpoint

    source = "Investigo."
    checkpoint = PlayerActionCheckpoint(
        resolution_id=1,
        context_revision=1,
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        interpretation_sha256=hashlib.sha256(b"{}").hexdigest(),
        nodes=(),
    )
    with pytest.raises(ValueError, match="active planning lease"):
        TurnResolutionRepository().create(
            make_record(action_checkpoint_json=checkpoint.to_json()),
            scope=CampaignScope(1),
        )
