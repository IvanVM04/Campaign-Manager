from operations.character_operations import (
    ChangeCharacterHpOperation,
)
from services.llm_world.operation_parser import (
    OperationParser,
)


def test_parser_builds_change_character_hp_operation():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "change_character_hp",
                    "entity_id": 7,
                    "amount": -5,
                }
            ]
        }
    )

    assert len(operations) == 1

    operation = operations[0]

    assert isinstance(
        operation,
        ChangeCharacterHpOperation,
    )

    assert operation.entity_id == 7
    assert operation.amount == -5

def test_parser_normalizes_character_entity_id():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "change_character_hp",
                    "entity_id": "7",
                    "amount": -5,
                }
            ]
        }
    )

    operation = operations[0]

    assert isinstance(
        operation,
        ChangeCharacterHpOperation,
    )

    assert operation.entity_id == 7
    assert operation.amount == -5

import pytest

from services.llm_world.operation_parser import (
    OperationParseError,
)


def test_parser_rejects_non_integer_character_hp_amount():
    parser = OperationParser()

    with pytest.raises(
        OperationParseError,
        match="'amount' must be an integer",
    ):
        parser.parse(
            {
                "operations": [
                    {
                        "type": "change_character_hp",
                        "entity_id": 7,
                        "amount": "five",
                    }
                ]
            }
        )