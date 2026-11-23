import json

import pytest

from models.character_state import CharacterState
from models.entity import Entity
from models.mechanics import MechanicsDecision, MechanicsDecisionType
from models.player_action_checkpoint import ActionExecutionState, PlayerActionCheckpoint
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from repositories.turn_resolution_repository import TurnResolutionRepository
from services.turns.durable_native_turn_service import DurableNativeTurnError
from services.turns.turn_resolution_service import TurnResolutionPlan
from tests.durable_turn_test_support import service_with_fake_models
from tests.test_v3_action_preview_service import _preview_service, _v3_response


def _activate_v3_player_and_target(service):
    actor = EntityRepository().save_entity(
        Entity(name="Arin", entity_type="player_character"),
        campaign_id=service.scope.campaign_id,
    )
    target = EntityRepository().save_entity(
        Entity(
            name="Puerta de roble",
            entity_type="location",
            aliases=["puerta roble"],
        ),
        campaign_id=service.scope.campaign_id,
    )
    character = CharacterRepository().save_character(
        CharacterState(entity_id=actor.id, level=1),
        campaign_id=service.scope.campaign_id,
    )
    service.context_service.set_active_character(
        character.entity_id,
        campaign_id=service.scope.campaign_id,
    )
    world = service.world_service.load()
    assert actor.id in world.entities
    assert target.id in world.entities
    return world


def _unknown_target_response(source):
    payload = json.loads(_v3_response(source))
    payload["events"][0]["arguments"][1]["mention"]["text"] = "la llave"
    return json.dumps(payload, ensure_ascii=False)


def test_durable_v3_target_clarification_pauses_resumes_same_node_and_replays(
    monkeypatch,
):
    source = "Yo intento abrir la llave"
    service, proposal_calls, narrative_calls = service_with_fake_models()
    world = _activate_v3_player_and_target(service)
    preview_service, interpreter_provider, _builder = _preview_service(
        world,
        _unknown_target_response(source),
    )
    service.execution_service.v3_action_preview_service = preview_service
    service.execution_service.v3_action_execution_enabled = True

    planning_evidence = []

    def prepare_one_action(turn_context, evidence, **kwargs):
        planning_evidence.append(evidence)
        return TurnResolutionPlan(
            player_input=evidence,
            narrative="",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
            mechanics_decision=MechanicsDecision(
                decision=MechanicsDecisionType.NONE
            ),
            intent_analysis=kwargs.get("intent_analysis_override"),
            intent_evidence_text=kwargs.get("intent_evidence_text"),
        )

    monkeypatch.setattr(service.resolver, "prepare_turn", prepare_one_action)

    pending = service.play_turn(
        source,
        idempotency_key="native-v3-target-clarification-001",
    )
    assert pending.pending_clarification_id
    assert pending.narrative
    assert interpreter_provider.call_count == 1
    assert planning_evidence == []
    assert proposal_calls == []

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-v3-target-clarification-001",
        scope=service.scope,
    )
    assert record is not None
    assert record.lifecycle_state == "awaiting_input"
    assert record.action_checkpoint_json is not None
    checkpoint = PlayerActionCheckpoint.from_json(record.action_checkpoint_json)
    assert checkpoint.nodes[0].state is ActionExecutionState.AWAITING_INPUT
    assert checkpoint.nodes[0].clarification_slots == ("target",)

    with pytest.raises(DurableNativeTurnError):
        service.submit_clarification(
            pending.pending_clarification_id,
            "Un objeto que no existe",
        )
    still_pending = TurnResolutionRepository().get(record.id, scope=service.scope)
    assert still_pending is not None
    assert still_pending.lifecycle_state == "awaiting_input"
    assert interpreter_provider.call_count == 1
    assert planning_evidence == []

    completed = service.submit_clarification(
        pending.pending_clarification_id,
        "Puerta de roble",
    )
    assert completed.narrative == "El personaje observa su entorno."
    assert interpreter_provider.call_count == 1
    assert planning_evidence == [source]
    assert len(narrative_calls) == 1
    assert proposal_calls == []

    saved = TurnResolutionRepository().get(record.id, scope=service.scope)
    assert saved is not None
    assert saved.lifecycle_state == "completed"
    final_checkpoint = PlayerActionCheckpoint.from_json(
        saved.action_checkpoint_json
    )
    assert final_checkpoint.nodes[0].state is ActionExecutionState.RESOLVED
    assert final_checkpoint.nodes[0].candidate.resolved_references[-1].referent_id == (
        next(
            entity.id
            for entity in world.entities.values()
            if entity.name == "Puerta de roble"
        )
    )
    adjudication = json.loads(saved.adjudication_json)
    assert adjudication["clarification_history"] == [{
        "question": pending.narrative,
        "answer": "Puerta de roble",
    }]
    assert adjudication["last_challenge_id"] == (
        pending.pending_clarification_id.split(":", 1)[1]
    )
    assert adjudication["v3_action_outcomes"][0]["outcome"] == "success"

    replay = service.submit_clarification(
        pending.pending_clarification_id,
        "Puerta de roble",
    )
    assert replay.narrative == completed.narrative
    assert replay.already_processed is True
    assert interpreter_provider.call_count == 1
    assert len(narrative_calls) == 1
    assert planning_evidence == [source]
