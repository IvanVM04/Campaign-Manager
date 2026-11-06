import json
from types import SimpleNamespace

import pytest

from operations.operation_reference import OperationReference
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import CreateEntityOperation
from services.operation_parser import OperationParser
from services.turns import TurnResolutionCodec
from services.turn_resolution_service import TurnResolutionPlan


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

    record = SimpleNamespace(player_input=plan.player_input, proposal_json=payload, mechanics_json=None)
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



def test_legacy_codec_import_reexports_canonical_implementation():
    from services.turn_resolution_codec import (
        TurnResolutionCodec as LegacyTurnResolutionCodec,
    )

    assert LegacyTurnResolutionCodec is TurnResolutionCodec
