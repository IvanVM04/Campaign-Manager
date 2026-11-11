import json

import pytest

from services.llm_world.llm_extraction_errors import LLMExtractionError
from services.llm_world.llm_world_response_parser import LLMWorldResponseParser
from services.llm_world.operation_parser import OperationParser
from services.llm_world.operation_registry import DEFAULT_OPERATION_REGISTRY


def test_registry_and_parser_share_the_same_operation_classes():
    parser = OperationParser()

    assert set(parser._BUILDERS) == {
        operation.name for operation in DEFAULT_OPERATION_REGISTRY.operations
    }
    assert parser._BUILDERS == DEFAULT_OPERATION_REGISTRY.builders


def test_registry_marks_model_proposable_operations_explicitly():
    allowed = DEFAULT_OPERATION_REGISTRY.model_proposable_operation_types()

    assert "create_entity" in allowed
    assert "create_event" in allowed
    assert "change_character_hp" not in allowed
    assert allowed == tuple(sorted(set(allowed)))
    assert DEFAULT_OPERATION_REGISTRY.is_model_proposable("change_character_hp") is False


def test_generated_json_schema_uses_dataclass_fields_and_required_values():
    metadata = DEFAULT_OPERATION_REGISTRY.get("create_item_instance")
    assert metadata is not None

    schema = metadata.json_schema()

    assert set(schema["properties"]) == {
        "type", "item_id", "instance_number", "owner_id",
        "location_id", "condition", "notes", "active",
    }
    assert schema["required"] == ["type", "item_id"]
    assert schema["properties"]["item_id"]["anyOf"][0] == {"type": "integer"}
    assert schema["properties"]["owner_id"]["anyOf"][-1] == {"type": "null"}
    assert schema["examples"][0]["type"] == "create_item_instance"


def test_prompt_contract_contains_descriptions_required_fields_and_examples():
    parsed = json.loads(
        DEFAULT_OPERATION_REGISTRY.render_prompt_contract(
            ("create_entity", "create_item_instance")
        )
    )
    variants = parsed["properties"]["operations"]["items"]["oneOf"]

    assert [variant["properties"]["type"]["const"] for variant in variants] == [
        "create_entity", "create_item_instance",
    ]
    create_entity = variants[0]
    assert create_entity["required"] == ["type", "name"]
    assert create_entity["properties"]["name"]["description"]
    assert create_entity["description"]
    assert create_entity["examples"][0]["name"] == "Guardia del mercado"


def test_prompt_contract_rejects_internal_or_unknown_operation_types():
    with pytest.raises(ValueError, match="not available"):
        DEFAULT_OPERATION_REGISTRY.render_prompt_contract(("change_character_hp",))
    with pytest.raises(ValueError, match="not available"):
        DEFAULT_OPERATION_REGISTRY.render_prompt_contract(("future_internal",))


def test_response_parser_rejects_internal_operation_before_parser_invocation():
    class ParserThatMustNotRun:
        def parse(self, payload):
            raise AssertionError("internal operation reached the structural parser")

    response_parser = LLMWorldResponseParser(ParserThatMustNotRun())

    with pytest.raises(LLMExtractionError, match="not permitted"):
        response_parser.parse_operations(
            {"operations": [{
                "type": "change_character_hp", "entity_id": 12, "amount": -4,
            }]}
        )
