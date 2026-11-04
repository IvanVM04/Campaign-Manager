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

def test_manual_roll_challenge_is_server_computed_and_hides_internal_decision():
    from types import SimpleNamespace

    from models.character_state import CharacterState
    from models.mechanics import MechanicsDecision, MechanicsDecisionType
    from rules_engine.dnd5e_2014.core.skills import Skill

    service, _, _ = _service_with_fake_models()
    character = CharacterState(
        entity_id=77,
        dexterity=16,
        skill_proficiencies=frozenset({Skill.STEALTH}),
    )
    decision = MechanicsDecision(
        decision=MechanicsDecisionType.SKILL_CHECK,
        skill=Skill.STEALTH,
        dc=15,
        advantage=True,
        reason="The character is moving unseen.",
    )

    pending = service._build_manual_roll_request(
        None, decision, SimpleNamespace(active_character=character), 12
    )
    result = service._manual_roll_result(
        SimpleNamespace(id=42, player_input="Me oculto."), pending
    )

    assert pending["modifier"] == 5
    assert pending["dc"] == 15
    assert pending["count"] == 2
    assert pending["context_revision"] == 12
    assert pending["challenge_id"]
    assert result.pending_roll_id == f"42:{pending['challenge_id']}"
    assert "decision" not in result.pending_roll
    assert "challenge_id" not in result.pending_roll


def test_manual_roll_submission_rejects_malformed_challenge_and_die_results():
    from services.durable_native_turn_service import DurableNativeTurnError

    service, _, _ = _service_with_fake_models()

    with pytest.raises(DurableNativeTurnError):
        service.submit_manual_roll("not-a-challenge", (12,))
    with pytest.raises(DurableNativeTurnError):
        service.submit_manual_roll("42:challenge", (0,))
    with pytest.raises(DurableNativeTurnError):
        service.submit_manual_roll("42:challenge", (12, 13, 14))


def test_native_clarification_survives_and_resumes_durably(monkeypatch):
    from services.turn_resolution_service import TurnResolutionPlan

    service, _, narrative_calls = _service_with_fake_models()
    plans = [
        TurnResolutionPlan(
            player_input="Abro la puerta.",
            narrative="¿Qué puerta?",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
            clarification_question="¿Qué puerta quieres abrir?",
        ),
        TurnResolutionPlan(
            player_input="Abro la puerta de roble.",
            narrative="",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
        ),
    ]
    calls = []

    def prepare_turn(context, player_input, **kwargs):
        calls.append(player_input)
        return plans.pop(0)

    monkeypatch.setattr(service.resolver, "prepare_turn", prepare_turn)

    pending = service.play_turn(
        "Abro una puerta.",
        idempotency_key="native-clarification-001",
    )
    assert pending.pending_clarification_id
    assert pending.narrative == "¿Qué puerta quieres abrir?"
    replayed_pending = service.play_turn(
        "Abro una puerta.",
        idempotency_key="native-clarification-001",
    )
    assert (
        replayed_pending.pending_clarification_id
        == pending.pending_clarification_id
    )

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-clarification-001",
        scope=service.scope,
    )
    assert record.lifecycle_state == "awaiting_input"
    assert record.context_revision is not None
    assert json.loads(record.adjudication_json)["clarification"]["question"] == (
        "¿Qué puerta quieres abrir?"
    )

    completed = service.submit_clarification(
        pending.pending_clarification_id,
        "La puerta de roble.",
    )

    assert completed.narrative == "El personaje observa su entorno."
    assert calls == [
        "Abro una puerta.",
        (
            "Abro una puerta."
            + "\n\nAclaración del DM: ¿Qué puerta quieres abrir?"
            + "\nRespuesta del jugador: La puerta de roble."
        ),
    ]
    repeated = service.submit_clarification(
        pending.pending_clarification_id,
        "La puerta de roble.",
    )
    assert repeated.narrative == completed.narrative
    assert repeated.already_processed is True
    assert len(narrative_calls) == 1

    saved = TurnResolutionRepository().get(record.id, scope=service.scope)
    assert saved.lifecycle_state == "completed"
    assert saved.player_input == "Abro una puerta."
    assert "La puerta de roble." in service._resolved_player_input(saved)
    assert json.loads(saved.adjudication_json)["clarification_history"] == [
        {
            "question": "¿Qué puerta quieres abrir?",
            "answer": "La puerta de roble.",
        }
    ]

    with pytest.raises(DurableNativeTurnError):
        service.submit_clarification(
            pending.pending_clarification_id,
            "Respuesta duplicada.",
        )


def test_native_clarification_rotates_challenge_when_more_detail_is_needed(monkeypatch):
    from services.turn_resolution_service import TurnResolutionPlan

    service, _, _ = _service_with_fake_models()
    questions = iter([
        "¿Qué puerta?",
        "¿La abres con cuidado o con fuerza?",
    ])
    calls = []

    def prepare_turn(context, player_input, **kwargs):
        calls.append(player_input)
        question = next(questions, None)
        return TurnResolutionPlan(
            player_input=player_input,
            narrative=question or "",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
            clarification_question=question,
        )

    monkeypatch.setattr(service.resolver, "prepare_turn", prepare_turn)
    first = service.play_turn(
        "Abro una puerta.",
        idempotency_key="native-clarification-002",
    )
    second = service.submit_clarification(
        first.pending_clarification_id,
        "La de roble.",
    )

    assert second.pending_clarification_id
    assert second.pending_clarification_id != first.pending_clarification_id
    assert second.narrative == "¿La abres con cuidado o con fuerza?"

    with pytest.raises(DurableNativeTurnError):
        service.submit_clarification(
            first.pending_clarification_id,
            "Respuesta antigua.",
        )


def test_silly_tavern_clarification_keeps_external_narration_durable(monkeypatch):
    from services.turn_resolution_service import TurnResolutionPlan

    service, _, narrative_calls = _service_with_fake_models()
    plans = [
        TurnResolutionPlan(
            player_input="Abro una puerta.",
            narrative="¿Cuál?",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
            clarification_question="¿Qué puerta quieres abrir?",
        ),
        TurnResolutionPlan(
            player_input="Abro la puerta de roble.",
            narrative="",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
        ),
    ]

    def prepare_turn(context, player_input, **kwargs):
        return plans.pop(0)

    monkeypatch.setattr(service.resolver, "prepare_turn", prepare_turn)
    prepared = service.prepare_external_turn(
        "Abro una puerta.",
        external_turn_id="st-clarification-001",
    )
    assert prepared.lifecycle_state == "awaiting_input"
    assert prepared.pending_clarification_id
    assert prepared.clarification_question == "¿Qué puerta quieres abrir?"

    recovered = service.get_external_clarification_state(
        "st-clarification-001"
    )
    assert recovered["has_clarification"] is True
    assert recovered["lifecycle_state"] == "awaiting_input"
    assert recovered["player_input"] == "Abro una puerta."
    assert recovered["pending_clarification_id"] == (
        prepared.pending_clarification_id
    )

    resumed = service.submit_clarification(
        prepared.pending_clarification_id,
        "La puerta de roble.",
        adapter_namespace="sillytavern",
        defer_narration=True,
        answer_external_turn_id="st-answer-clarification-001",
    )
    assert resumed.lifecycle_state == "narration_pending"
    assert resumed.clarification_question is None
    assert resumed.pending_clarification_id is None
    recovered_after_answer = service.get_external_clarification_state(
        "st-clarification-001"
    )
    assert recovered_after_answer["lifecycle_state"] == "narration_pending"
    assert recovered_after_answer["pending_clarification_id"] is None
    assert recovered_after_answer["last_pending_clarification_id"] == (
        prepared.pending_clarification_id
    )
    assert recovered_after_answer["last_answer"] == "La puerta de roble."
    assert recovered_after_answer["last_answer_external_turn_id"] == (
        "st-answer-clarification-001"
    )
    assert "La puerta de roble." in recovered_after_answer["resolved_player_input"]
    assert narrative_calls == []

    completed = service.complete_external_narration(
        external_turn_id="st-clarification-001",
        player_input="Abro una puerta.",
        narrative="La puerta de roble se abre.",
        turn_version=1,
    )
    assert completed.narrative == "La puerta de roble se abre."
    assert completed.already_processed is False
