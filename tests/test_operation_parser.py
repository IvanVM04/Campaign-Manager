import pytest

from operations.operation_reference import OperationReference
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import (
    CreateRelationOperation,
    GainResourceOperation,
    SpendResourceOperation,
    TransferResourceOperation,
    UpdateEntityOperation,
    UpdateRelationOperation,
)
from services.llm_world.operation_parser import OperationParseError, OperationParser


def test_operation_parser_normalizes_update_entity_id_from_string():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "update_entity",
                    "entity_id": "12",
                    "description": "Ahora está herido.",
                }
            ]
        }
    )

    assert len(operations) == 1
    assert operations[0].entity_id == 12
    assert isinstance(operations[0].entity_id, int)


def test_operation_parser_rejects_boolean_update_entity_id():
    parser = OperationParser()

    with pytest.raises(OperationParseError):
        parser.parse(
            {
                "operations": [
                    {
                        "type": "update_entity",
                        "entity_id": True,
                    }
                ]
            }
        )

def test_parser_accepts_operation_reference():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "ref": "sword",
                    "type": "create_item",
                    "name": "Espada oxidada",
                },
                {
                    "type": "create_item_instance",
                    "item_id": "$sword",
                    "owner_id": 7,
                },
            ]
        }
    )

    assert len(operations) == 2

    first = operations[0]
    second = operations[1]

    assert isinstance(
        first,
        ReferencedOperation,
    )
    assert first.ref == "sword"

    assert isinstance(
        second.item_id,
        OperationReference,
    )
    assert second.item_id.name == "sword"

def test_parser_rejects_non_string_create_item_significance():
    parser = OperationParser()

    with pytest.raises(OperationParseError):
        parser.parse(
            {
                "operations": [
                    {
                        "type": "create_item",
                        "name": "Espada",
                        "significance": 123,
                    }
                ]
            }
        )


def test_parser_rejects_non_string_create_resource_type():
    parser = OperationParser()

    with pytest.raises(OperationParseError):
        parser.parse(
            {
                "operations": [
                    {
                        "type": "create_resource",
                        "name": "Oro",
                        "resource_type": 123,
                    }
                ]
            }
        )


def test_parser_rejects_non_string_create_resource_unit():
    parser = OperationParser()

    with pytest.raises(OperationParseError):
        parser.parse(
            {
                "operations": [
                    {
                        "type": "create_resource",
                        "name": "Oro",
                        "unit": 123,
                    }
                ]
            }
        )


def test_parser_rejects_non_string_item_instance_condition():
    parser = OperationParser()

    with pytest.raises(OperationParseError):
        parser.parse(
            {
                "operations": [
                    {
                        "type": "create_item_instance",
                        "item_id": 1,
                        "condition": 123,
                    }
                ]
            }
        )

def test_gain_resource_accepts_owner_reference():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "gain_resource",
                    "resource_id": "$gold",
                    "owner_id": "$character",
                    "amount": 50,
                }
            ]
        }
    )

    operation = operations[0]

    assert isinstance(
        operation,
        GainResourceOperation,
    )

    assert isinstance(
        operation.resource_id,
        OperationReference,
    )

    assert operation.resource_id.name == "gold"

    assert isinstance(
        operation.owner_id,
        OperationReference,
    )

    assert operation.owner_id.name == "character"

def test_spend_resource_accepts_owner_reference():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "spend_resource",
                    "resource_id": "$gold",
                    "owner_id": "$character",
                    "amount": 25,
                }
            ]
        }
    )

    operation = operations[0]

    assert isinstance(
        operation,
        SpendResourceOperation,
    )

    assert isinstance(
        operation.resource_id,
        OperationReference,
    )

    assert isinstance(
        operation.owner_id,
        OperationReference,
    )

    assert operation.resource_id.name == "gold"
    assert operation.owner_id.name == "character"

def test_transfer_resource_accepts_references():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "transfer_resource",
                    "resource_id": "$gold",
                    "subject_id": "$from",
                    "target_id": "$to",
                    "amount": 10,
                }
            ]
        }
    )

    operation = operations[0]

    assert isinstance(
        operation,
        TransferResourceOperation,
    )

    assert isinstance(
        operation.resource_id,
        OperationReference,
    )

    assert isinstance(
        operation.subject_id,
        OperationReference,
    )

    assert isinstance(
        operation.target_id,
        OperationReference,
    )

    assert operation.resource_id.name == "gold"
    assert operation.subject_id.name == "from"
    assert operation.target_id.name == "to"

def test_create_relation_accepts_entity_references():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "create_relation",
                    "relation_id": "guard_aldren",
                    "subject_id": "$guard",
                    "relation_type": "miembro_de",
                    "target_id": "$faction",
                }
            ]
        }
    )

    operation = operations[0]

    assert isinstance(
        operation,
        CreateRelationOperation,
    )

    assert isinstance(
        operation.subject_id,
        OperationReference,
    )

    assert isinstance(
        operation.target_id,
        OperationReference,
    )

    assert operation.subject_id.name == "guard"
    assert operation.target_id.name == "faction"

def test_update_relation_accepts_target_reference():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "update_relation",
                    "relation_id": "guard_aldren",
                    "target_id": "$new_target",
                }
            ]
        }
    )

    operation = operations[0]

    assert isinstance(
        operation,
        UpdateRelationOperation,
    )

    assert isinstance(
        operation.target_id,
        OperationReference,
    )

    assert operation.target_id.name == "new_target"

def test_update_entity_accepts_entity_reference():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "update_entity",
                    "entity_id": "$npc",
                    "name": "Aldren el Rojo",
                }
            ]
        }
    )

    operation = operations[0]

    assert isinstance(
        operation,
        UpdateEntityOperation,
    )

    assert isinstance(
        operation.entity_id,
        OperationReference,
    )

    assert operation.entity_id.name == "npc"
    assert operation.name == "Aldren el Rojo"

def test_model_proposable_operation_registry_excludes_character_mutations():
    parser = OperationParser()

    allowed = parser.model_proposable_operation_types()

    assert "create_entity" in allowed
    assert "create_item_instance" in allowed
    assert "change_character_hp" not in allowed
    assert allowed == tuple(sorted(set(allowed)))


def test_parser_uses_registry_reference_fields_for_id_normalization():
    parser = OperationParser()
    metadata = parser.registry.get("transfer_resource")

    assert metadata is not None
    assert metadata.reference_fields == (
        "resource_id",
        "subject_id",
        "target_id",
    )

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "transfer_resource",
                    "resource_id": "$gold",
                    "subject_id": "12",
                    "target_id": 14,
                    "amount": 3,
                }
            ]
        }
    )

    assert operations[0].resource_id.name == "gold"
    assert operations[0].subject_id == 12
    assert operations[0].target_id == 14


def test_parser_accepts_and_normalizes_entity_aliases():
    operations = OperationParser().parse(
        {
            "operations": [
                {
                    "type": "create_entity",
                    "name": "Aldric",
                    "entity_type": "npc",
                    "aliases": [" el tabernero ", "el tabernero", "Aldric"],
                }
            ]
        }
    )
    assert operations[0].aliases == ["el tabernero", "Aldric"]


@pytest.mark.parametrize(
    "aliases",
    [
        "el tabernero",
        [12],
        [""],
        ["x" * 101],
        [f"alias-{index}" for index in range(21)],
    ],
)
def test_parser_rejects_malformed_or_unbounded_entity_aliases(aliases):
    with pytest.raises(OperationParseError, match="aliases|alias"):
        OperationParser().parse(
            {
                "operations": [
                    {
                        "type": "create_entity",
                        "name": "Aldric",
                        "aliases": aliases,
                    }
                ]
            }
        )
