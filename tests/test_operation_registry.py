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
    operations = parsed["operations"]
    create_entity = operations["create_entity"]

    assert create_entity["required"] == "name:text"
    assert "entity_type:text" in create_entity["optional"]
    assert "aliases" in create_entity["optional"]
    assert "aliases" in parsed["field_notes"]
    assert "no los inventes" in parsed["field_notes"]["aliases"]
    assert create_entity["description"]
    assert len(create_entity["description"]) > 32
    assert parsed["examples"]["create_entity"]["name"] == "Aldric"
    assert parsed["examples"]["create_entity"]["entity_type"] == "npc"
    assert (
        "Tabernero" in parsed["examples"]["create_entity"]["description"]
    )
    assert "item_id" in parsed["field_notes"]
    assert "entity_type" in parsed["field_notes"]
    assert "persona identificada" in parsed["field_notes"]["entity_type"]
    entity_schema = DEFAULT_OPERATION_REGISTRY.get("create_entity").json_schema()
    assert "Hechos conocidos" in entity_schema["properties"]["description"]["description"]


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

    with pytest.raises(
        LLMExtractionError, match="require verified rules-engine resolution"
    ):
        response_parser.parse_operations(
            {"operations": [{
                "type": "change_character_hp", "entity_id": 12, "amount": -4,
            }]}
        )


def test_default_prompt_contract_is_compact_enough_to_leave_room_for_world_context():
    contract = DEFAULT_OPERATION_REGISTRY.render_prompt_contract()

    assert len(contract) <= 3500
    assert len(DEFAULT_OPERATION_REGISTRY.model_proposable_operation_types()) == 14


def test_empty_proposal_allowlist_renders_empty_contract_without_fallback():
    contract = json.loads(
        DEFAULT_OPERATION_REGISTRY.render_prompt_contract(())
    )

    assert contract["operations"] == {}
    assert contract["examples"] == {}
