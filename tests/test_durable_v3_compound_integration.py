import json
from dataclasses import replace

from models.character_state import CharacterState
from models.entity import Entity
from models.mechanics import MechanicsDecision, MechanicsDecisionType
from models.player_action_checkpoint import ActionExecutionState, PlayerActionCheckpoint
from models.turn_context import TurnContext
from models.world_state import WorldState
from repositories.turn_resolution_repository import TurnResolutionRepository
from services.turns.turn_resolution_service import TurnResolutionPlan
from tests.durable_turn_test_support import service_with_fake_models
from tests.test_v3_action_preview_service import _preview_service, _v3_response


def test_v3_compound_graph_uses_native_durable_commit_boundary(
    isolated_database,
    monkeypatch,
):
    source = "Yo intento abrir la puerta"
    service, _proposal_calls, narrative_calls = service_with_fake_models()
    base_context, recent, revision = service._capture_turn_snapshot()
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(
                id=8,
                name="Puerta de hierro",
                entity_type="location",
                aliases=["la puerta"],
            ),
        }
    )
    context = replace(
        base_context,
        active_character=CharacterState(entity_id=7),
        world=world,
    )
    assert isinstance(context, TurnContext)
    preview_service, interpreter_provider, _builder = _preview_service(
        world,
        _v3_response(source),
    )
    service.execution_service.v3_action_preview_service = preview_service
    service.execution_service.v3_action_execution_enabled = True
    monkeypatch.setattr(
        service,
        "_capture_turn_snapshot",
        lambda *, conversation_id=None: (context, recent, revision),
    )

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

    result = service.play_turn(
        source,
        idempotency_key="native-v3-compound-runtime-001",
    )

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-v3-compound-runtime-001",
        scope=service.scope,
    )
    assert result.narrative == "El personaje observa su entorno."
    assert record is not None
    assert record.lifecycle_state == "completed"
    assert record.action_checkpoint_json is not None
    checkpoint = PlayerActionCheckpoint.from_json(record.action_checkpoint_json)
    assert checkpoint.nodes[0].state is ActionExecutionState.RESOLVED
    assert planning_evidence == [source]
    assert interpreter_provider.call_count == 1
    adjudication = json.loads(record.adjudication_json)
    assert adjudication["v3_action_outcomes"][0]["outcome"] == "success"
    assert len(narrative_calls) == 1
    assert '"action_outcomes"' in narrative_calls[0]
    assert '"outcome":"success"' in narrative_calls[0]
