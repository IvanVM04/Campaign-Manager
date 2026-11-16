"""Deterministic tests for safe, field-level Intent validation diagnostics."""
from __future__ import annotations

import json
import logging

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.intent_validation_diagnostics import (
    IntentAnalysisValidationError,
    diagnose_intent_analysis_error,
)
from models.player_intent_analysis import PlayerIntentAnalysis
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.providers import FakeLLMProvider
from services.turns import IntentInterpreter, IntentInterpreterError


def _source() -> str:
    return "Abro la puerta."


def _payload() -> dict:
    return {
        "schema_version": 2,
        "category": "action",
        "steps": [{
            "index": 0,
            "source_excerpt": _source(),
            "actor": "player",
            "action": "abrir la puerta",
            "modality": "attempted",
            "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": ["la puerta"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "Abro",
                "family": "interaction",
                "arguments": [{
                    "role": "theme",
                    "mention": {
                        "text": "la puerta",
                        "kind_hint": "world_entity",
                    },
                }],
            },
        }],
        "active_step_index": 0,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }


def _context() -> TurnContext:
    return TurnContext(
        campaign=CampaignState(campaign_id=1, name="Diagnostics"),
        current_session=None,
        active_character=CharacterState(entity_id=20),
        world=WorldState(),
    )


def _assert_diagnostic(
    payload: dict,
    source: str,
    *,
    code: str,
    field: str,
) -> None:
    with pytest.raises(IntentAnalysisValidationError) as captured:
        PlayerIntentAnalysis.from_payload(payload, source_text=source)
    error = captured.value
    assert error.validation_code == code
    assert error.validation_field == field
    assert error.validation_reason
    assert code in str(error)
    assert field in str(error)


def test_source_excerpt_failure_reports_player_evidence_field():
    value = _payload()
    value["steps"][0]["source_excerpt"] = "Cierro la ventana."

    _assert_diagnostic(
        value,
        _source(),
        code="evidence_not_in_player_text",
        field="steps[].source_excerpt",
    )


def test_action_predicate_failure_reports_exact_semantic_field_without_value():
    value = _payload()
    value["steps"][0]["action_frame"]["predicate"] = "PRIVATE_COMPLETION"

    with pytest.raises(IntentAnalysisValidationError) as captured:
        PlayerIntentAnalysis.from_payload(value, source_text=_source())

    assert captured.value.validation_code == "evidence_not_in_player_text"
    assert captured.value.validation_field == "steps[].action_frame.predicate"
    assert "PRIVATE_COMPLETION" not in str(captured.value)


def test_action_argument_must_be_grounded_in_its_own_step_excerpt():
    source = "Abro la puerta. La llave está dentro del cofre."
    value = _payload()
    value["steps"][0]["action_frame"]["arguments"].append({
        "role": "instrument",
        "mention": {
            "text": "la llave",
            "kind_hint": "item_instance",
        },
    })

    _assert_diagnostic(
        value,
        source,
        code="evidence_not_in_step_excerpt",
        field="steps[].action_frame.arguments[].mention",
    )


def test_relation_claim_must_be_grounded_in_the_referenced_step():
    source = "Mara habla con Aldric. Bram protege a Mara."
    value = _payload()
    value["category"] = "report"
    value["steps"][0]["source_excerpt"] = "Mara habla con Aldric."
    value["steps"][0]["action"] = "hablar con Aldric"
    value["steps"][0]["modality"] = "reported"
    value["steps"][0]["action_frame"] = {
        "predicate": "habla",
        "family": "communication",
        "arguments": [],
    }
    value["steps"][0]["target_mentions"] = ["Mara", "Aldric"]
    value["active_step_index"] = None
    value["relation_claims"] = [{
        "step_index": 0,
        "subject": {"text": "Bram", "kind_hint": "character"},
        "predicate": "protege",
        "object": {"text": "Mara", "kind_hint": "character"},
        "relation_family": "protection",
        "polarity": "positive",
        "modality": "reported",
        "source_excerpt": "Bram protege a Mara.",
        "attributed_to": None,
        "temporal_expression": None,
    }]

    _assert_diagnostic(
        value,
        source,
        code="evidence_not_in_step_excerpt",
        field="relation_claims[].step_evidence",
    )


def test_unsupported_enum_reports_field_but_never_model_supplied_value():
    value = _payload()
    value["steps"][0]["modality"] = "PRIVATE_ENUM_VALUE"

    with pytest.raises(IntentAnalysisValidationError) as captured:
        PlayerIntentAnalysis.from_payload(value, source_text=_source())

    assert captured.value.validation_code == "unsupported_enum_value"
    assert captured.value.validation_field == "steps[].modality"
    assert "PRIVATE_ENUM_VALUE" not in str(captured.value)


def test_interpreter_logs_safe_code_field_and_reason_without_completion(
    caplog: pytest.LogCaptureFixture,
):
    value = _payload()
    value["steps"][0]["action_frame"]["predicate"] = "PRIVATE_COMPLETION"
    provider = FakeLLMProvider(
        response=json.dumps({"intent_analysis": value})
    )
    interpreter = IntentInterpreter(provider)

    with (
        caplog.at_level(logging.WARNING, logger="services.turns.intent_interpreter"),
        pytest.raises(IntentInterpreterError) as captured,
    ):
        interpreter.interpret(_context(), _source())

    error = captured.value
    assert error.validation_stage == "intent_analysis_validation"
    assert error.validation_code == "evidence_not_in_player_text"
    assert error.validation_field == "steps[].action_frame.predicate"
    assert "PRIVATE_COMPLETION" not in str(error)
    record = next(
        item
        for item in caplog.records
        if item.getMessage() == "llm.intent.invalid_response"
    )
    assert record.validation_code == "evidence_not_in_player_text"
    assert record.validation_field == "steps[].action_frame.predicate"
    assert record.validation_reason == "evidence_mismatch"
    assert "PRIVATE_COMPLETION" not in record.getMessage()
    assert "PRIVATE_COMPLETION" not in repr(record.__dict__)


@pytest.mark.parametrize(
    ("message", "code", "field", "reason"),
    [
        (
            "v1 intent analysis cannot contain semantic frames",
            "invalid_versioned_contract",
            "schema_version",
            "invariant",
        ),
        (
            "v2 intent steps require a SemanticActionFrame",
            "missing_or_invalid_action_frame",
            "steps[].action_frame",
            "type_mismatch",
        ),
        (
            "clarification requires a bounded question",
            "invalid_clarification_question",
            "clarification_question",
            "text_constraint",
        ),
        (
            "clarification_question requires requires_clarification",
            "clarification_state_mismatch",
            "clarification_question",
            "invariant",
        ),
        (
            "intent JSON must be text or None",
            "invalid_type",
            "intent_json",
            "type_mismatch",
        ),
        (
            "enum fields must be strings",
            "invalid_type",
            "enum_value",
            "type_mismatch",
        ),
        (
            "semantic arguments must not repeat the same role and mention",
            "duplicate_semantic_argument",
            "steps[].action_frame.arguments[]",
            "duplicate_value",
        ),
        (
            "relation subject and object must be SemanticMention values",
            "invalid_type",
            "relation_claims[].subject_or_object",
            "type_mismatch",
        ),
    ],
)
def test_remaining_intent_contract_failures_have_specific_safe_codes(
    message: str,
    code: str,
    field: str,
    reason: str,
):
    diagnostic = diagnose_intent_analysis_error(ValueError(message))

    assert diagnostic.code == code
    assert diagnostic.field == field
    assert diagnostic.reason == reason

def test_interpreter_logs_safe_relation_selector_reason_code(
    caplog: pytest.LogCaptureFixture,
):
    from tests.test_pending_intent_correction import relation_analysis

    answer = "Quise decir que Mara protege a Aldric, no a Bram."
    response = {
        "status": "corrected",
        "pending_corrections": [
            {
                "step_index": 0,
                "slot": "relation_subject:0",
                "previous_value": "Bram",
                "replacement": {
                    "text": "Aldric",
                    "kind_hint": "character",
                },
                "source_excerpt": answer,
            }
        ],
        "clarification_question": None,
    }
    interpreter = IntentInterpreter(
        FakeLLMProvider(response=json.dumps(response))
    )

    with (
        caplog.at_level(
            logging.WARNING,
            logger="services.turns.intent_interpreter",
        ),
        pytest.raises(IntentInterpreterError) as captured,
    ):
        interpreter.understand_pending(
            _context(),
            "Mara protege a Bram.\n\nDM: ¿A quién protege Mara?\n" + answer,
            pending_analysis=relation_analysis(),
            correction_evidence_text=answer,
            evidence_text=answer,
        )

    error = captured.value
    assert error.validation_stage == "pending_corrections_validation"
    assert error.validation_code == "invalid_pending_corrections"
    assert error.validation_reason == "relation_selector_opposite_endpoint"

    record = next(
        item
        for item in caplog.records
        if item.getMessage() == "llm.intent.invalid_response"
    )
    assert record.validation_reason == "relation_selector_opposite_endpoint"
    assert "Bram" not in repr(record.__dict__)
    assert "Mara" not in repr(record.__dict__)
    assert "Aldric" not in repr(record.__dict__)
