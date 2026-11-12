import json

import pytest

from durable_turn_test_support import service_with_fake_models
from services.turns.durable_native_turn_service import DurableNativeTurnError


def test_silly_tavern_commits_before_external_narration_and_swipes_do_not_reapply():
    service, proposal_calls, _ = service_with_fake_models()
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
    service, proposal_calls, _ = service_with_fake_models()
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

def test_silly_tavern_rejects_transcript_without_durable_resolution():
    from models.turn_record import TurnRecord

    service, proposal_calls, _ = service_with_fake_models()
    service.turn_repository.save_turn(
        TurnRecord(
            player_input="Entro en la taberna.",
            narrative="La taberna está llena.",
            operation_count=1,
            successful_operation_count=1,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=True,
            external_turn_id="historical-st-turn",
            version=1,
            status="active",
        ),
        scope=service.scope,
    )

    with pytest.raises(DurableNativeTurnError, match="no durable resolution"):
        service.prepare_external_turn(
            "Entro en la taberna.",
            external_turn_id="historical-st-turn",
        )

    with pytest.raises(DurableNativeTurnError, match="no durable resolution"):
        service.complete_external_narration(
            external_turn_id="historical-st-turn",
            player_input="Entro en la taberna.",
            narrative="La taberna está abarrotada.",
            turn_version=2,
        )

    assert proposal_calls == []
    active = service.turn_repository.get_active_by_external_turn_id(
        "historical-st-turn",
        scope=service.scope,
    )
    assert active is not None
    assert active.version == 1
    assert active.narrative == "La taberna está llena."

def test_silly_tavern_clarification_keeps_external_narration_durable(monkeypatch):
    from services.turns.turn_resolution_service import TurnResolutionPlan

    service, _, narrative_calls = service_with_fake_models()
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

    service, _, _ = service_with_fake_models()
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
        service.execution_service,
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

    service, _, _ = service_with_fake_models()
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
    service, _, _ = service_with_fake_models()
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

    service, _, _ = service_with_fake_models()
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

    service, _, _ = service_with_fake_models()
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
        service.execution_service,
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

def test_external_narration_rejects_conflicting_content_for_existing_version():
    from database import get_conn

    service, proposal_calls, _ = service_with_fake_models()
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

    service, proposal_calls, _ = service_with_fake_models()
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
