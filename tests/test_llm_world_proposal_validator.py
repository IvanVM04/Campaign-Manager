import json

import pytest

from services.llm_world.llm_extraction_errors import LLMExtractionError
from services.llm_world.llm_world_proposal_validator import LLMWorldProposalValidator


class FakeParser:
    @staticmethod
    def model_proposable_operation_types():
        return ("create_entity",)


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


def test_oversized_proposal_response_fails_without_repair():
    validator, calls = make_validator(iter(['{"operations": []}']))
    validator.max_response_chars = 8

    with pytest.raises(LLMExtractionError, match="size limit"):
        validator.parse_with_repair("prompt", '{"operations": []}')

    assert calls == []


def test_repair_prompt_is_compact_and_does_not_repeat_full_world_prompt():
    validator, calls = make_validator(
        iter(['{"operations": []}'])
    )
    long_prompt = "WORLD CONTEXT " * 5000

    assert validator.parse_with_repair(
        long_prompt,
        '{"operations": [{"type": "unknown"}]}',
    ) == []
    assert len(calls) == 1
    assert "WORLD CONTEXT" not in calls[0]
    assert "PROPUESTA INVÁLIDA ANTERIOR" in calls[0]
    assert len(calls[0]) < 7000


def test_repair_prompt_respects_configured_estimated_token_budget():
    validator, calls = make_validator(
        iter(['{"operations": []}'])
    )
    validator.max_repair_prompt_tokens = 1400
    invalid_response = (
        '{"operations": [{"type": "unknown"}]}'
        + "invalid-output-" * 300
        + "TAIL_SENTINEL"
    )

    validator.parse_with_repair("prompt", invalid_response)

    from models.world_context_projection import estimate_tokens

    assert estimate_tokens(calls[0]) <= 1400
    assert "TAIL_SENTINEL" not in calls[0]
