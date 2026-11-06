import json
from typing import ClassVar

import pytest

from operations.character_operations import ChangeCharacterHpOperation
from operations.world_operations import CreateEntityOperation
from services.llm_world.llm_extraction_errors import LLMExtractionError
from services.llm_world.llm_world_proposal_validator import LLMWorldProposalValidator


class FakeParser:
    _BUILDERS: ClassVar[dict[str, type]] = {
        "create_entity": CreateEntityOperation,
        "change_character_hp": ChangeCharacterHpOperation,
    }


def parse_response(raw):
    if not isinstance(raw, str):
        raise LLMExtractionError("LLM response must be a string")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMExtractionError("LLM response is not valid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("operations"), list):
        raise LLMExtractionError("Invalid operations payload")
    return payload


def make_validator(responses):
    calls = []

    def provider(prompt):
        calls.append(prompt)
        return next(responses)

    def parse_operations(payload):
        if payload["operations"] and payload["operations"][0].get("type") != "create_entity":
            raise LLMExtractionError("unsupported operation")
        return payload["operations"]

    validator = LLMWorldProposalValidator(
        provider=provider,
        operation_parser=FakeParser(),
        parse_response=parse_response,
        parse_operations=parse_operations,
    )
    return validator, calls


def test_valid_proposal_does_not_request_repair():
    validator, calls = make_validator(iter(['{"operations": [{"type": "create_entity"}]}']))

    result = validator.parse_with_repair("prompt", '{"operations": [{"type": "create_entity"}]}')

    assert result == [{"type": "create_entity"}]
    assert calls == []


def test_invalid_proposal_is_repaired_once_with_allowed_types():
    validator, calls = make_validator(
        iter(['{"operations": [{"type": "create_entity"}]}'])
    )

    result = validator.parse_with_repair(
        "prompt",
        '{"operations": [{"type": "unknown"}]}',
    )

    assert result == [{"type": "create_entity"}]
    assert len(calls) == 1
    assert '"create_entity"' in calls[0]
    assert '"change_character_hp"' not in calls[0]
    assert "PROPUESTA INVÁLIDA ANTERIOR" in calls[0]


def test_invalid_repair_raises_after_exactly_one_retry():
    validator, calls = make_validator(
        iter(['{"operations": [{"type": "unknown"}]}'])
    )

    with pytest.raises(LLMExtractionError, match="after one repair attempt"):
        validator.parse_with_repair(
            "prompt",
            '{"operations": [{"type": "unknown"}]}',
        )

    assert len(calls) == 1
