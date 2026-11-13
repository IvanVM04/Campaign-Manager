import hashlib
import json
from types import SimpleNamespace

import pytest

from models.player_intent_analysis import PlayerIntentAnalysis
from operations.operation_reference import OperationReference
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import CreateEntityOperation
from services.llm_world.operation_parser import OperationParser
from services.turns import TurnResolutionCodec
from services.turns.turn_resolution_service import TurnResolutionPlan


def test_operation_codec_preserves_references_and_reconstructs_plan():
    operation = CreateEntityOperation(name="Aldric", entity_type="npc", description="Tabernero.")
    plan = TurnResolutionPlan(
        player_input="Entro en la taberna.", narrative="",
        world_operations=(ReferencedOperation(operation, ref="innkeeper"),),
        character_operations=(),
        ordered_operations=(ReferencedOperation(operation, ref="innkeeper"),),
    )
    payload = TurnResolutionCodec.serialize_operations(plan)
    decoded = json.loads(payload)
    assert decoded["operations"][0]["ref"] == "innkeeper"
    assert decoded["operations"][0]["type"] == "create_entity"

    record = SimpleNamespace(
        player_input=plan.player_input,
        proposal_json=payload,
        mechanics_json=None,
        intent_json=None,
    )
    restored = TurnResolutionCodec.plan_from_record(record, OperationParser())
    assert restored.player_input == plan.player_input
    assert restored.ordered_operations == plan.ordered_operations
    assert restored.world_operations == plan.world_operations
    assert restored.mechanics_result is None


def test_operation_codec_preserves_nested_operation_references():
    assert TurnResolutionCodec.operation_value({"entity_id": OperationReference("innkeeper")}) == {"entity_id": "$innkeeper"}


def test_operation_codec_rejects_unregistered_operation_types():
    class UnsupportedOperation:
        pass

    plan = TurnResolutionPlan(
        player_input="test", narrative="", world_operations=(),
        character_operations=(), ordered_operations=(UnsupportedOperation(),),
    )
    with pytest.raises(ValueError, match="unsupported operation type"):
        TurnResolutionCodec.serialize_operations(plan)



def test_intent_codec_round_trips_the_evidence_source_with_its_analysis():
    source = "Abro la puerta."
    analysis = PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 1,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": "Abro la puerta",
                "actor": "player",
                "action": "abrir la puerta",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["la puerta"],
                "attributed_to": None,
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
        source_text=source,
    )
    plan = TurnResolutionPlan(
        player_input=source,
        narrative="",
        world_operations=(),
        character_operations=(),
        ordered_operations=(),
        intent_analysis=analysis,
    )

    encoded = TurnResolutionCodec.intent_to_json(plan)
    restored = TurnResolutionCodec.intent_from_json(
        encoded,
        original_input=source,
    )
    restored_source = TurnResolutionCodec.intent_source_text(
        encoded,
        original_input=source,
    )

    assert restored == analysis
    assert restored_source == source


def test_intent_codec_preserves_clarification_source_on_recovery():
    original = "Abro la puerta."
    clarified = original + "\\nRespuesta del jugador: la puerta de roble."
    analysis = PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 1,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": "la puerta de roble",
                "actor": "player",
                "action": "abrir la puerta de roble",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["la puerta de roble"],
                "attributed_to": None,
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
        source_text=clarified,
    )
    plan = TurnResolutionPlan(
        player_input=clarified,
        narrative="",
        world_operations=(),
        character_operations=(),
        ordered_operations=(),
        intent_analysis=analysis,
    )
    encoded = TurnResolutionCodec.intent_to_json(plan)

    restored = TurnResolutionCodec.intent_from_json(
        encoded,
        original_input=original,
    )

    assert restored == analysis
    assert TurnResolutionCodec.intent_source_text(
        encoded,
        original_input=original,
    ) == clarified


def test_intent_codec_rejects_analysis_not_bound_to_original_request():
    payload = json.dumps({
        "schema_version": 1,
        "source_text": "Abro una ventana.",
        "source_sha256": hashlib.sha256(
            b"Abro una ventana."
        ).hexdigest(),
        "analysis": {
            "schema_version": 1,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": "Abro una ventana",
                "actor": "player",
                "action": "abrir una ventana",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["una ventana"],
                "attributed_to": None,
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
    })

    with pytest.raises(ValueError, match="not bound"):
        TurnResolutionCodec.intent_from_json(
            payload,
            original_input="Abro la puerta.",
        )


