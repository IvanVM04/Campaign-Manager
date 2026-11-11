import json

import pytest

from bootstrap.campaign_runtime import CampaignRuntimeFactory
from repositories.turn_resolution_repository import TurnResolutionRepository
from services.turns.durable_native_turn_service import DurableNativeTurnError


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
    from services.turns.durable_native_turn_service import DurableNativeTurnError

    service, _, _ = _service_with_fake_models()

    with pytest.raises(DurableNativeTurnError):
        service.submit_manual_roll("not-a-challenge", (12,))
    with pytest.raises(DurableNativeTurnError):
        service.submit_manual_roll("42:challenge", (0,))
    with pytest.raises(DurableNativeTurnError):
        service.submit_manual_roll("42:challenge", (12, 13, 14))


def test_native_clarification_survives_and_resumes_durably(monkeypatch):
    from services.turns.turn_resolution_service import TurnResolutionPlan

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
    from services.turns.turn_resolution_service import TurnResolutionPlan

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
    from services.turns.turn_resolution_service import TurnResolutionPlan

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

    replayed_answer = service.submit_clarification(
        prepared.pending_clarification_id,
        "La puerta de roble.",
        adapter_namespace="sillytavern",
        defer_narration=True,
        answer_external_turn_id="st-answer-clarification-001",
    )
    assert replayed_answer.lifecycle_state == "narration_pending"
    with pytest.raises(DurableNativeTurnError):
        service.submit_clarification(
            prepared.pending_clarification_id,
            "La puerta de roble.",
            adapter_namespace="sillytavern",
            defer_narration=True,
            answer_external_turn_id="different-answer-message-id",
        )

    completed = service.complete_external_narration(
        external_turn_id="st-clarification-001",
        player_input="Abro una puerta.",
        narrative="La puerta de roble se abre.",
        turn_version=1,
    )
    assert completed.narrative == "La puerta de roble se abre."
    assert completed.already_processed is False


def test_silly_tavern_manual_mode_returns_durable_roll_challenge(monkeypatch):
    from types import SimpleNamespace

    from models.turn_resolution_result import TurnResolutionResult

    service, _, _ = _service_with_fake_models()
    captured = {}
    pending = {
        "count": 2,
        "dice": "d20",
        "kind": "skill_check",
        "skill": "stealth",
        "ability": "dexterity",
        "dc": 15,
        "modifier": 5,
        "advantage": True,
        "disadvantage": False,
    }
    monkeypatch.setattr(
        service,
        "_play_turn_locked",
        lambda player_input, **kwargs: (
            captured.update(kwargs)
            or TurnResolutionResult(
                player_input=player_input,
                narrative="",
                pending_roll_id="42:" + "a" * 24,
                pending_roll=pending,
            )
        ),
    )
    monkeypatch.setattr(
        service.resolution_repository,
        "get_by_idempotency_key",
        lambda *args, **kwargs: SimpleNamespace(id=42, adjudication_json=None),
    )

    preparation = service.prepare_external_turn(
        "Me escondo del guardia.",
        external_turn_id="st-manual-turn",
        dice_mode="manual",
    )

    assert captured["dice_mode"] == "manual"
    assert captured["defer_narration"] is True
    assert preparation.lifecycle_state == "awaiting_input"
    assert preparation.pending_roll_id == "42:" + "a" * 24
    assert preparation.pending_roll == pending


def test_silly_tavern_manual_roll_state_exposes_pending_challenge_without_internal_decision(monkeypatch):
    from types import SimpleNamespace

    service, _, _ = _service_with_fake_models()
    pending = {
        "challenge_id": "secret-challenge",
        "count": 2,
        "dice": "d20",
        "kind": "skill_check",
        "modifier": 5,
        "decision": {"dc": 15, "reason": "private adjudication"},
    }
    record = SimpleNamespace(
        id=42,
        lifecycle_state="awaiting_input",
        player_input="Me escondo.",
        adjudication_json=json.dumps({"manual_roll": pending}),
    )
    monkeypatch.setattr(
        service.resolution_repository,
        "get_by_idempotency_key",
        lambda *args, **kwargs: record,
    )

    state = service.get_external_manual_roll_state("st-manual-turn")

    assert state["has_manual_roll"] is True
    assert state["pending_roll_id"] == "42:secret-challenge"
    assert state["pending_roll"] == {
        "count": 2,
        "dice": "d20",
        "kind": "skill_check",
        "modifier": 5,
    }
    assert "decision" not in state["pending_roll"]
    assert "challenge_id" not in state["pending_roll"]


def test_silly_tavern_manual_roll_state_is_scoped_to_sillytavern(monkeypatch):
    service, _, _ = _service_with_fake_models()
    captured = {}
    monkeypatch.setattr(
        service.resolution_repository,
        "get_by_idempotency_key",
        lambda namespace, key, **kwargs: (
            captured.update({"namespace": namespace, "key": key})
            or None
        ),
    )

    state = service.get_external_manual_roll_state("st-manual-turn")
    assert state["has_manual_roll"] is False
    assert captured == {
        "namespace": "sillytavern",
        "key": "st-manual-turn",
    }


def test_silly_tavern_completed_manual_roll_state_is_recoverable_for_same_reply(monkeypatch):
    from types import SimpleNamespace

    service, _, _ = _service_with_fake_models()
    pending = {
        "challenge_id": "secret-challenge",
        "count": 1,
        "dice": "d20",
        "kind": "ability_check",
        "modifier": 3,
        "submitted_rolls": [14],
        "submitted_external_turn_id": "answer-turn",
    }
    record = SimpleNamespace(
        id=42,
        lifecycle_state="completed",
        player_input="Me escondo.",
        adjudication_json=json.dumps({"manual_roll": pending}),
    )
    monkeypatch.setattr(
        service.resolution_repository,
        "get_by_idempotency_key",
        lambda *args, **kwargs: record,
    )

    state = service.get_external_manual_roll_state("st-manual-turn")

    assert state["has_manual_roll"] is True
    assert state["submitted_external_turn_id"] == "answer-turn"
    assert state["pending_roll_id"] == "42:secret-challenge"
    assert state["pending_roll"]["count"] == 1


def test_silly_tavern_turn_retry_uses_persisted_manual_dice_mode(monkeypatch):
    from types import SimpleNamespace

    from models.turn_resolution_result import TurnResolutionResult

    service, _, _ = _service_with_fake_models()
    captured = {}
    record = SimpleNamespace(
        id=42,
        adjudication_json=json.dumps({"dice_mode": "manual"}),
    )
    pending = {"count": 1, "kind": "ability_check", "modifier": 2}
    monkeypatch.setattr(
        service.resolution_repository,
        "get_by_idempotency_key",
        lambda *args, **kwargs: record,
    )
    monkeypatch.setattr(
        service.turn_repository,
        "get_active_by_external_turn_id",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        service,
        "_play_turn_locked",
        lambda player_input, **kwargs: (
            captured.update(kwargs)
            or TurnResolutionResult(
                player_input=player_input,
                narrative="",
                pending_roll_id="42:" + "a" * 24,
                pending_roll=pending,
            )
        ),
    )

    service.prepare_external_turn(
        "Me escondo.",
        external_turn_id="st-manual-turn",
        dice_mode="automatic",
    )

    assert captured["dice_mode"] == "manual"


def test_silly_tavern_world_event_survives_duplicate_delivery_and_runtime_reload():
    from bootstrap.campaign_runtime import CampaignRuntimeFactory

    factory = CampaignRuntimeFactory()
    service = factory.get_runtime(1).durable_native_turn_service
    event_id = "bridge-bell-discovery"
    event_title = "La campana rota de Puenteviejo"
    proposal_payload = json.dumps({
        "operations": [{
            "type": "create_event",
            "event_id": event_id,
            "event_type": "discovery",
            "title": event_title,
            "description": "El grupo descubre que la campana fue arrancada de su soporte.",
            "consequences": "La ausencia de la campana queda como pista conocida.",
            "session_id": None,
            "secret": False,
            "metadata": {"location": "Puenteviejo"},
        }]
    })
    proposal_calls = []
    service.resolver.extractor.provider = lambda prompt: (
        proposal_calls.append(prompt) or proposal_payload
    )

    prepared = service.prepare_external_turn(
        "Investigo el campanario.",
        external_turn_id="st-world-continuity-001",
    )
    assert prepared.lifecycle_state == "narration_pending"
    assert len(proposal_calls) == 1

    duplicate = service.prepare_external_turn(
        "Investigo el campanario.",
        external_turn_id="st-world-continuity-001",
    )
    assert duplicate.resolution_id == prepared.resolution_id
    assert len(proposal_calls) == 1

    persisted_world = service.world_service.repository.load_world(campaign_id=1)
    assert event_id in persisted_world.events
    assert persisted_world.events[event_id].title == event_title

    service.complete_external_narration(
        external_turn_id="st-world-continuity-001",
        player_input="Investigo el campanario.",
        narrative="Encuentras marcas recientes donde antes colgaba la campana.",
        turn_version=1,
    )

    # Simulate a backend runtime restart: the next turn must rebuild its
    # context from persisted campaign state, not an in-memory world snapshot.
    factory.invalidate(1)
    reloaded_service = factory.get_runtime(1).durable_native_turn_service
    reloaded_world = reloaded_service.world_service.repository.load_world(campaign_id=1)
    assert event_id in reloaded_world.events

    next_proposal_calls = []
    reloaded_service.resolver.extractor.provider = lambda prompt: (
        next_proposal_calls.append(prompt) or '{"operations": []}'
    )
    next_preparation = reloaded_service.prepare_external_turn(
        "Le pregunto a Mara si sabe algo de la campana.",
        external_turn_id="st-world-continuity-002",
    )

    assert next_preparation.lifecycle_state == "narration_pending"
    assert len(next_proposal_calls) == 1
    assert event_title in next_proposal_calls[0]
    assert "La ausencia de la campana queda como pista conocida." in next_proposal_calls[0]


def test_unexpected_native_turn_failure_logs_original_traceback(caplog):
    service, _, _ = _service_with_fake_models()

    def fail_during_preparation(*args, **kwargs):
        raise RuntimeError("simulated provider failure")

    service.resolver.prepare_turn = fail_during_preparation

    with (
        caplog.at_level(
            "ERROR",
            logger="services.durable_native_turn_service",
        ),
        pytest.raises(
            DurableNativeTurnError,
            match="native turn execution failed",
        ),
    ):
        service.play_turn(
            "Investigo el campanario.",
            idempotency_key="native-test-unexpected-error-001",
        )

    entries = [
        record
        for record in caplog.records
        if "Unexpected native turn execution failure" in record.getMessage()
    ]
    assert len(entries) == 1
    assert entries[0].exc_info is not None
    assert isinstance(entries[0].exc_info[1], RuntimeError)
    assert str(entries[0].exc_info[1]) == "simulated provider failure"
    assert "campaign_id=1" in entries[0].getMessage()
    assert "adapter_namespace=native" in entries[0].getMessage()
    assert "lifecycle_state=planning" in entries[0].getMessage()


def test_unexpected_planning_failure_releases_lease_and_recovers_after_runtime_restart():
    service, _, _ = _service_with_fake_models()

    def fail_during_preparation(*args, **kwargs):
        raise RuntimeError("temporary extraction provider outage")

    service.resolver.prepare_turn = fail_during_preparation

    with pytest.raises(
        DurableNativeTurnError,
        match="native turn execution failed",
    ):
        service.play_turn(
            "Investigo el campanario.",
            idempotency_key="native-planning-restart-recovery",
        )

    failed_attempt = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-planning-restart-recovery",
        scope=service.scope,
    )
    assert failed_attempt.lifecycle_state == "accepted"
    assert failed_attempt.attempt_count == 1
    assert failed_attempt.lease_token is None
    assert failed_attempt.lease_expires_at is None
    assert failed_attempt.last_error_code == "planning_failed"

    # A fresh runtime simulates a process restart: recovery must rely on the
    # persisted resolution, not the failed service instance or its lock.
    restarted_service = CampaignRuntimeFactory().get_runtime(
        service.scope.campaign_id
    ).durable_native_turn_service
    restarted_service.resolver.mechanics_adjudicator = None
    proposal_calls = []
    restarted_service.resolver.extractor.provider = lambda prompt: (
        proposal_calls.append(prompt) or '{"operations": []}'
    )
    narrative_calls = []
    restarted_service.resolver.dm_service.provider.generate = lambda prompt: (
        narrative_calls.append(prompt) or "La campana permanece inmóvil."
    )

    recovered = restarted_service.play_turn(
        "Investigo el campanario.",
        idempotency_key="native-planning-restart-recovery",
    )

    assert recovered.narrative == "La campana permanece inmóvil."
    assert len(proposal_calls) == 1
    assert len(narrative_calls) == 1

    completed = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-planning-restart-recovery",
        scope=service.scope,
    )
    assert completed.lifecycle_state == "completed"
    assert completed.attempt_count == 2
    assert completed.lease_token is None
    assert completed.lease_expires_at is None



def test_invalid_llm_proposal_releases_planning_lease_and_same_identity_retries():
    service, _, _ = _service_with_fake_models()
    responses = iter([
        '{"operations": [{"type": "start_interaction"}]}',
        '{"operations": [{"type": "start_interaction"}]}',
        '{"operations": []}',
    ])
    proposal_calls = []

    def proposal_provider(prompt):
        proposal_calls.append(prompt)
        return next(responses)

    service.resolver.extractor.provider = proposal_provider

    with pytest.raises(DurableNativeTurnError):
        service.play_turn(
            "Hablo con Mara.",
            idempotency_key="native-invalid-proposal-retry",
        )

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-invalid-proposal-retry",
        scope=service.scope,
    )
    assert record.lifecycle_state == "accepted"
    assert record.lease_token is None
    assert record.lease_expires_at is None
    assert record.last_error_code == "invalid_llm_proposal"
    assert len(proposal_calls) == 2

    recovered = service.play_turn(
        "Hablo con Mara.",
        idempotency_key="native-invalid-proposal-retry",
    )

    assert recovered.narrative == "El personaje observa su entorno."
    assert len(proposal_calls) == 3



def test_context_failure_after_commit_is_recoverable_without_reapplying_operations(monkeypatch):
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

    original_context_and_history = service._context_and_history
    context_calls = {"count": 0}

    def fail_once_after_commit(conn):
        context_calls["count"] += 1
        # Calls 1 and 2 build/validate the plan; call 3 is the context
        # reload for narration, after the consequences have been committed.
        if context_calls["count"] == 3:
            raise RuntimeError("temporary context read failure")
        return original_context_and_history(conn)

    monkeypatch.setattr(service, "_context_and_history", fail_once_after_commit)

    with pytest.raises(DurableNativeTurnError):
        service.play_turn(
            "Miro alrededor.",
            idempotency_key="native-context-failure-after-commit",
        )

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-context-failure-after-commit",
        scope=service.scope,
    )
    assert record.lifecycle_state == "narration_pending"
    assert record.resulting_revision is not None
    committed_world = service.world_service.repository.load_world(campaign_id=1)
    assert any(entity.name == "Aldric" for entity in committed_world.entities.values())
    assert len(proposal_calls) == 1

    recovered = service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-context-failure-after-commit",
    )

    assert recovered.narrative == "El personaje observa su entorno."
    assert len(proposal_calls) == 1
    recovered_world = service.world_service.repository.load_world(campaign_id=1)
    assert any(entity.name == "Aldric" for entity in recovered_world.entities.values())


def test_native_idempotency_key_rejects_different_player_input():
    service, proposal_calls, narrative_calls = _service_with_fake_models()
    service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-idempotency-input-conflict",
    )

    with pytest.raises(
        DurableNativeTurnError,
        match="idempotency key was already used for a different request",
    ):
        service.play_turn(
            "Abro la puerta.",
            idempotency_key="native-idempotency-input-conflict",
        )

    assert len(proposal_calls) == 1
    assert len(narrative_calls) == 1


def test_external_narration_rejects_conflicting_content_for_existing_version():
    from database import get_conn

    service, proposal_calls, _ = _service_with_fake_models()
    service.prepare_external_turn(
        "Miro la habitación.",
        external_turn_id="st-narrative-version-conflict",
    )
    service.complete_external_narration(
        external_turn_id="st-narrative-version-conflict",
        player_input="Miro la habitación.",
        narrative="Hay una mesa.",
        turn_version=1,
    )
    first_record = service.turn_repository.get_active_by_external_turn_id(
        "st-narrative-version-conflict",
        scope=service.scope,
    )

    with pytest.raises(
        DurableNativeTurnError,
        match="external turn version already exists with different content",
    ):
        service.complete_external_narration(
            external_turn_id="st-narrative-version-conflict",
            player_input="Miro la habitación.",
            narrative="Hay una ventana.",
            turn_version=1,
        )

    active = service.turn_repository.get_active_by_external_turn_id(
        "st-narrative-version-conflict",
        scope=service.scope,
    )
    assert active.id == first_record.id
    assert active.version == 1
    assert active.narrative == "Hay una mesa."
    assert len(proposal_calls) == 1
    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM turns WHERE external_turn_id=?",
            ("st-narrative-version-conflict",),
        ).fetchone()[0]
    assert count == 1


def test_external_narration_rejects_skipped_version_without_writing_transcript():
    from database import get_conn

    service, proposal_calls, _ = _service_with_fake_models()
    service.prepare_external_turn(
        "Miro la habitación.",
        external_turn_id="st-narrative-version-gap",
    )

    with pytest.raises(
        DurableNativeTurnError,
        match="external turn version must be 1",
    ):
        service.complete_external_narration(
            external_turn_id="st-narrative-version-gap",
            player_input="Miro la habitación.",
            narrative="Hay una mesa.",
            turn_version=2,
        )

    assert service.turn_repository.get_active_by_external_turn_id(
        "st-narrative-version-gap",
        scope=service.scope,
    ) is None
    assert len(proposal_calls) == 1
    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM turns WHERE external_turn_id=?",
            ("st-narrative-version-gap",),
        ).fetchone()[0]
    assert count == 0
