import json

import pytest

from repositories.turn_resolution_repository import TurnResolutionRepository
from services.campaign_runtime import CampaignRuntimeFactory
from services.durable_native_turn_service import DurableNativeTurnError


def _service_with_fake_models():
    runtime = CampaignRuntimeFactory().get_runtime(1)
    service = runtime.durable_native_turn_service
    service.resolver.mechanics_adjudicator = None
    proposal_calls = []
    service.resolver.extractor.provider = lambda prompt: (
        proposal_calls.append(prompt) or '{"operations": []}'
    )
    narrative_calls = []
    service.resolver.dm_service.provider.generate = lambda prompt: (
        narrative_calls.append(prompt) or "El personaje observa su entorno."
    )
    return service, proposal_calls, narrative_calls


def test_native_turn_commits_before_narration_and_completes_durably():
    service, proposal_calls, narrative_calls = _service_with_fake_models()

    result = service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-test-turn-001",
    )

    assert result.narrative == "El personaje observa su entorno."
    assert result.already_processed is False
    assert len(proposal_calls) == 1
    assert len(narrative_calls) == 1
    assert "RESOLUCIÓN Y CONSECUENCIAS YA COMPROMETIDAS" in narrative_calls[0]
    assert '"operations": []' in narrative_calls[0]

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-test-turn-001",
        scope=service.scope,
    )
    assert record.lifecycle_state == "completed"
    assert record.committed_at is not None
    assert record.completed_at is not None
    assert record.context_revision is not None
    assert record.resulting_revision is not None
    assert record.turn_id is not None


def test_native_turn_retry_does_not_reapply_or_replan_completed_resolution():
    service, proposal_calls, narrative_calls = _service_with_fake_models()

    first = service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-test-turn-002",
    )
    second = service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-test-turn-002",
    )

    assert first.narrative == second.narrative
    assert second.already_processed is True
    assert len(proposal_calls) == 1
    assert len(narrative_calls) == 1


def test_narration_failure_leaves_committed_resolution_resumable():
    service, proposal_calls, _ = _service_with_fake_models()
    attempts = {"count": 0}
    proposal_payload = json.dumps({
        "operations": [{
            "type": "create_entity",
            "name": "Aldric",
            "entity_type": "npc",
            "description": "Tabernero.",
            "notes": "",
            "active": True,
        }]
    })
    service.resolver.extractor.provider = lambda prompt: (
        proposal_calls.append(prompt) or proposal_payload
    )

    def fail_once(prompt):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary narration outage")
        return "La narración se ha recuperado."

    service.resolver.dm_service.provider.generate = fail_once

    with pytest.raises(DurableNativeTurnError):
        service.play_turn(
            "Miro alrededor.",
            idempotency_key="native-test-turn-003",
        )

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-test-turn-003",
        scope=service.scope,
    )
    assert record.lifecycle_state == "narration_pending"
    assert record.resulting_revision is not None
    committed_world = service.world_service.repository.load_world(campaign_id=1)
    assert len(committed_world.entities) == 1

    resumed = service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-test-turn-003",
    )

    assert resumed.narrative == "La narración se ha recuperado."
    assert len(proposal_calls) == 1
    assert attempts["count"] == 2
    recovered_world = service.world_service.repository.load_world(campaign_id=1)
    assert len(recovered_world.entities) == 1


def test_silly_tavern_commits_before_external_narration_and_swipes_do_not_reapply():
    service, proposal_calls, _ = _service_with_fake_models()
    proposal_payload = json.dumps({
        "operations": [{
            "type": "create_entity",
            "name": "Aldric",
            "entity_type": "npc",
            "description": "Tabernero.",
            "notes": "",
            "active": True,
        }]
    })
    service.resolver.extractor.provider = lambda prompt: (
        proposal_calls.append(prompt) or proposal_payload
    )
    narrative_calls = []
    service.resolver.dm_service.provider.generate = lambda prompt: (
        narrative_calls.append(prompt) or "Esta llamada no debe ejecutarse."
    )

    prepared = service.prepare_external_turn(
        "Abro la puerta.",
        external_turn_id="st-chat-turn-001",
    )

    assert prepared.lifecycle_state == "narration_pending"
    assert prepared.resolution_id is not None
    assert "resulting_revision" in prepared.committed_resolution
    assert len(proposal_calls) == 1
    assert narrative_calls == []

    recovered_preparation = service.prepare_external_turn(
        "Abro la puerta.",
        external_turn_id="st-chat-turn-001",
    )
    assert recovered_preparation.resolution_id == prepared.resolution_id
    assert recovered_preparation.lifecycle_state == "narration_pending"
    assert len(proposal_calls) == 1

    from database import get_conn
    committed_world = service.world_service.repository.load_world(campaign_id=1)
    assert len(committed_world.entities) == 1

    first = service.complete_external_narration(
        external_turn_id="st-chat-turn-001",
        player_input="Abro la puerta.",
        narrative="La puerta se abre.",
        turn_version=1,
    )
    assert first.narrative == "La puerta se abre."

    second_preparation = service.prepare_external_turn(
        "Abro la puerta.",
        external_turn_id="st-chat-turn-001",
    )
    assert second_preparation.lifecycle_state == "completed"
    assert len(proposal_calls) == 1

    second = service.complete_external_narration(
        external_turn_id="st-chat-turn-001",
        player_input="Abro la puerta.",
        narrative="La puerta se abre con un chirrido.",
        turn_version=2,
    )
    assert second.narrative == "La puerta se abre con un chirrido."
    assert second.already_processed is True
    # Transcript version writes may advance the campaign context revision,
    # but the committed domain entity must not be applied a second time.
    regenerated_world = service.world_service.repository.load_world(campaign_id=1)
    assert len(regenerated_world.entities) == 1

    with get_conn() as conn:
        versions = conn.execute(
            """
            SELECT version, status, narrative
            FROM turns
            WHERE external_turn_id=?
            ORDER BY version
            """,
            ("st-chat-turn-001",),
        ).fetchall()

    assert [(row["version"], row["status"]) for row in versions] == [
        (1, "superseded"),
        (2, "active"),
    ]
    assert len(proposal_calls) == 1
    assert narrative_calls == []


def test_silly_tavern_narrative_retry_is_idempotent():
    service, proposal_calls, _ = _service_with_fake_models()
    service.prepare_external_turn(
        "Miro la habitación.",
        external_turn_id="st-chat-turn-002",
    )

    first = service.complete_external_narration(
        external_turn_id="st-chat-turn-002",
        player_input="Miro la habitación.",
        narrative="Hay una mesa.",
        turn_version=1,
    )
    replay = service.complete_external_narration(
        external_turn_id="st-chat-turn-002",
        player_input="Miro la habitación.",
        narrative="Hay una mesa.",
        turn_version=1,
    )

    assert first.narrative == replay.narrative
    assert replay.already_processed is True
    assert len(proposal_calls) == 1

    from database import get_conn
    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM turns WHERE external_turn_id=?",
            ("st-chat-turn-002",),
        ).fetchone()[0]
    assert count == 1


def test_silly_tavern_legacy_replay_versions_narrative_without_new_resolution():
    from database import get_conn
    from models.turn_record import TurnRecord

    service, proposal_calls, _ = _service_with_fake_models()
    legacy = service.turn_repository.save_turn(
        TurnRecord(
            player_input="Entro en la taberna.",
            narrative="La taberna está llena.",
            operation_count=1,
            successful_operation_count=1,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=True,
            external_turn_id="legacy-st-turn",
            version=1,
            status="active",
        ),
        scope=service.scope,
    )

    prepared = service.prepare_external_turn(
        "Entro en la taberna.",
        external_turn_id="legacy-st-turn",
    )
    assert prepared.legacy_replay is True
    assert prepared.lifecycle_state == "legacy_replay"
    assert proposal_calls == []

    replay = service.complete_external_narration(
        external_turn_id="legacy-st-turn",
        player_input="Entro en la taberna.",
        narrative="La taberna está abarrotada.",
        turn_version=2,
    )
    assert replay.narrative == "La taberna está abarrotada."
    assert replay.already_processed is True
    assert proposal_calls == []

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT version, status, operation_count, world_changed
            FROM turns
            WHERE external_turn_id=?
            ORDER BY version
            """,
            ("legacy-st-turn",),
        ).fetchall()

    assert [(row["version"], row["status"]) for row in rows] == [
        (1, "superseded"),
        (2, "active"),
    ]
    assert rows[1]["operation_count"] == legacy.operation_count
    assert rows[1]["world_changed"] == 1


def test_legacy_silly_tavern_replay_skips_a_persisted_failed_version():
    from models.turn_record import TurnRecord

    service, proposal_calls, _ = _service_with_fake_models()
    service.turn_repository.save_turn(
        TurnRecord(
            player_input="Abro la puerta.",
            narrative="Versión activa.",
            external_turn_id="legacy-failed-swipe",
            version=1,
            status="active",
        ),
        scope=service.scope,
    )
    service.turn_repository.save_turn(
        TurnRecord(
            player_input="Abro la puerta.",
            narrative="Versión fallida.",
            operation_count=1,
            successful_operation_count=0,
            failed_operation_count=1,
            all_operations_succeeded=False,
            external_turn_id="legacy-failed-swipe",
            version=2,
            status="failed",
        ),
        scope=service.scope,
    )

    preparation = service.prepare_external_turn(
        "Abro la puerta.",
        external_turn_id="legacy-failed-swipe",
    )
    assert preparation.legacy_replay is True

    result = service.complete_external_narration(
        external_turn_id="legacy-failed-swipe",
        player_input="Abro la puerta.",
        narrative="Nueva versión tras el intento fallido.",
        turn_version=3,
    )
    assert result.narrative == "Nueva versión tras el intento fallido."
    assert proposal_calls == []

    from database import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT version, status
            FROM turns
            WHERE external_turn_id=?
            ORDER BY version
            """,
            ("legacy-failed-swipe",),
        ).fetchall()
    assert [(row["version"], row["status"]) for row in rows] == [
        (1, "superseded"),
        (2, "failed"),
        (3, "active"),
    ]
