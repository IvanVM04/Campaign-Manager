"""Safe, field-level diagnostics for rejected player-intent model payloads.

Only fixed codes, field paths and reason categories leave the model trust
boundary. Raw exception messages may contain model-generated or player text.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IntentValidationDiagnostic:
    """Bounded diagnostic metadata that never contains source or model text."""

    code: str
    field: str
    reason: str

    @property
    def safe_message(self) -> str:
        return f"{self.code} (field={self.field})"


class IntentAnalysisValidationError(ValueError):
    """ValueError carrying a safe, machine-readable intent validation result."""

    def __init__(self, diagnostic: IntentValidationDiagnostic) -> None:
        self.diagnostic = diagnostic
        self.validation_code = diagnostic.code
        self.validation_field = diagnostic.field
        self.validation_reason = diagnostic.reason
        super().__init__(diagnostic.safe_message)


def diagnose_intent_analysis_error(
    error: BaseException,
) -> IntentValidationDiagnostic:
    """Map internal validation failures to stable, privacy-safe identifiers.

    The original message is inspected locally only. It is never copied into
    the returned diagnostic, log fields or public exception text.
    """
    message = str(error).casefold()

    evidence_rules = (
        (
            "relation claim is not grounded in its referenced intent step",
            "evidence_not_in_step_excerpt",
            "relation_claims[].step_evidence",
        ),
        (
            "relation source_excerpt is not grounded in player input",
            "evidence_not_in_player_text",
            "relation_claims[].source_excerpt",
        ),
        (
            "relation predicate is not literal player evidence",
            "evidence_not_in_player_text",
            "relation_claims[].predicate",
        ),
        (
            "source_excerpt is not grounded in player input",
            "evidence_not_in_player_text",
            "steps[].source_excerpt",
        ),
        (
            "target mention is not literal utterance evidence",
            "evidence_not_in_player_text",
            "steps[].target_mentions[]",
        ),
        (
            "target mention is not grounded in its intent step",
            "evidence_not_in_step_excerpt",
            "steps[].target_mentions[]",
        ),
        (
            "attribution is not grounded in player input",
            "evidence_not_in_player_text",
            "steps[].attributed_to",
        ),
        (
            "attribution is not grounded in its intent step",
            "evidence_not_in_step_excerpt",
            "steps[].attributed_to",
        ),
        (
            "action predicate is not literal player evidence",
            "evidence_not_in_player_text",
            "steps[].action_frame.predicate",
        ),
        (
            "action predicate is not grounded in its intent step",
            "evidence_not_in_step_excerpt",
            "steps[].action_frame.predicate",
        ),
        (
            "action argument is not grounded in its intent step",
            "evidence_not_in_step_excerpt",
            "steps[].action_frame.arguments[].mention",
        ),
        (
            "temporal_expression is not literal player evidence",
            "evidence_not_in_player_text",
            "relation_claims[].temporal_expression",
        ),
        (
            "is not literal player evidence",
            "evidence_not_in_player_text",
            "semantic_mentions[]",
        ),
        (
            "is not literal utterance evidence",
            "evidence_not_in_player_text",
            "steps[].target_mentions[]",
        ),
    )
    for fragment, code, field in evidence_rules:
        if fragment in message:
            if fragment == "is not literal player evidence":
                if "relation subject" in message:
                    field = "relation_claims[].subject"
                elif "relation object" in message:
                    field = "relation_claims[].object"
                elif "relation attribution" in message:
                    field = "relation_claims[].attributed_to"
                elif "argument mention" in message:
                    field = "steps[].action_frame.arguments[].mention"
            return IntentValidationDiagnostic(code, field, "evidence_mismatch")

    if "unsupported player intent schema version" in message:
        return IntentValidationDiagnostic(
            "unsupported_schema_version", "schema_version", "unsupported_value"
        )

    exact_rules = (
        (
            "v1 intent analysis cannot contain semantic frames",
            "invalid_versioned_contract",
            "schema_version",
            "invariant",
        ),
        (
            "v2 intent steps require a semanticactionframe",
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
            "intent json must be text or none",
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
            "relation subject and object must be semanticmention values",
            "invalid_type",
            "relation_claims[].subject_or_object",
            "type_mismatch",
        ),
    )
    for fragment, code, field, reason in exact_rules:
        if fragment in message:
            return IntentValidationDiagnostic(code, field, reason)

    if "unsupported " in message:
        enum_fields = (
            ("utterancecategory", "category"),
            ("intentactor", "steps[].actor"),
            ("intentmodality", "steps[].modality"),
            ("intentpolarity", "steps[].polarity"),
            ("playerreportedoutcome", "steps[].reported_outcome"),
            ("semanticobjectkind", "semantic_mentions[].kind_hint"),
            ("semanticargumentrole", "steps[].action_frame.arguments[].role"),
            ("semanticactionfamily", "steps[].action_frame.family"),
            ("semanticrelationfamily", "relation_claims[].relation_family"),
            ("semanticpolarity", "relation_claims[].polarity"),
            ("semanticmodality", "relation_claims[].modality"),
        )
        for enum_name, field in enum_fields:
            if enum_name in message:
                return IntentValidationDiagnostic(
                    "unsupported_enum_value", field, "unsupported_value"
                )
        return IntentValidationDiagnostic(
            "unsupported_enum_value", "intent_analysis", "unsupported_value"
        )

    if "missing or unexpected fields" in message:
        if "intent_analysis" in message:
            field = "intent_analysis"
        elif "intent step" in message:
            field = "steps[]"
        elif "action_frame" in message:
            field = "steps[].action_frame"
        elif "semantic argument" in message:
            field = "steps[].action_frame.arguments[]"
        elif "relation claim" in message:
            field = "relation_claims[]"
        elif "mention" in message:
            field = "semantic_mentions[]"
        else:
            field = "intent_analysis"
        return IntentValidationDiagnostic(
            "invalid_object_shape", field, "schema_shape"
        )

    if "bounded array" in message or "at most" in message:
        if "relation_claim" in message:
            field = "relation_claims"
        elif "target_mentions" in message:
            field = "steps[].target_mentions"
        elif "arguments" in message:
            field = "steps[].action_frame.arguments"
        elif "steps" in message:
            field = "steps"
        else:
            field = "intent_analysis"
        return IntentValidationDiagnostic(
            "collection_out_of_bounds", field, "bounds"
        )

    if "must be non-empty" in message:
        field = "intent_analysis"
        for token, path in (
            ("source_excerpt", "steps[].source_excerpt"),
            ("target mention", "steps[].target_mentions[]"),
            ("attributed_to", "steps[].attributed_to"),
            ("predicate", "semantic_predicate"),
            ("temporal_expression", "relation_claims[].temporal_expression"),
        ):
            if token in message:
                field = path
                break
        return IntentValidationDiagnostic(
            "empty_required_text", field, "text_constraint"
        )

    if "must not exceed" in message:
        return IntentValidationDiagnostic(
            "text_out_of_bounds", "intent_analysis", "bounds"
        )

    if "step indices must be contiguous and ordered" in message:
        return IntentValidationDiagnostic(
            "invalid_step_order", "steps[].index", "ordering"
        )
    if (
        "relation claim must reference an existing intent step" in message
        or "relation_claims must reference an existing intent step" in message
    ):
        return IntentValidationDiagnostic(
            "invalid_relation_reference",
            "relation_claims[].step_index",
            "reference",
        )
    if "relation step_index" in message:
        return IntentValidationDiagnostic(
            "invalid_relation_reference",
            "relation_claims[].step_index",
            "reference",
        )
    if "active_step_index" in message:
        return IntentValidationDiagnostic(
            "invalid_active_step", "active_step_index", "invariant"
        )
    if "active step cannot" in message or "future steps cannot" in message:
        return IntentValidationDiagnostic(
            "intent_step_invariant_violation", "steps[]", "invariant"
        )
    if "resolved reported outcome" in message:
        return IntentValidationDiagnostic(
            "intent_step_invariant_violation",
            "steps[].reported_outcome",
            "invariant",
        )
    if "only action or mixed utterances" in message:
        return IntentValidationDiagnostic(
            "category_active_step_mismatch", "category", "invariant"
        )
    if "v2 intent step requires an action_frame" in message:
        return IntentValidationDiagnostic(
            "missing_required_value", "steps[].action_frame", "missing_value"
        )
    if "not a tuple" in message or "must be a tuple" in message:
        return IntentValidationDiagnostic(
            "invalid_type", "intent_analysis", "type_mismatch"
        )
    if "must be a" in message or "must contain" in message or "must be an" in message:
        return IntentValidationDiagnostic(
            "invalid_type", "intent_analysis", "type_mismatch"
        )
    return IntentValidationDiagnostic(
        "invalid_semantic_contract", "intent_analysis", "invariant_or_value"
    )
