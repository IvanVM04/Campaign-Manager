"""Gold loading and privacy-safe scoring for the v2/v3 shadow benchmark."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from tests.player_turn_interpretation_v3_shadow import (
    V2V3ShadowComparison,
    comparison_shape,
)
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

_CORPUS_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "player_turn_v3_shadow_corpus_v1.json"
)

_V3_SEQUENCE_FIELDS = (
    "act_forces",
    "speaker_roles",
    "event_families",
    "polarities",
    "epistemic_statuses",
    "action_phases",
    "link_types",
    "fact_kinds",
    "relation_families",
    "fact_directions",
    "fact_polarities",
    "fact_epistemic_statuses",
    "fact_temporal_scopes",
    "fact_predicate_surfaces",
    "normalized_relation_types",
    "clarification_kinds",
    "link_source_ref_kinds",
    "link_target_ref_kinds",
    "callback_anchor_candidates",
)
_V3_COUNT_FIELDS = (
    "utterance_acts",
    "events",
    "discourse_links",
    "world_facts",
    "clarification_candidates",
    "evidence_spans",
    "quote_spans",
    "speaker_mentions",
    "addressee_mentions",
    "event_attributed_sources",
    "fact_attributed_sources",
)
_V2_FIELDS = ("category", "step_count", "active_step_index", "relation_count")
_V2_SEQUENCE_FIELDS = ("modalities", "actors")


def load_v3_shadow_corpus() -> list[dict[str, Any]]:
    """Load the frozen audit-derived holdout and validate its small contract."""
    corpus = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
    if (
        not isinstance(corpus, dict)
        or set(corpus) != {"schema_version", "split", "purpose", "scenarios"}
        or corpus["schema_version"] != 1
        or corpus["split"] != "held_out"
        or not isinstance(corpus["purpose"], str)
        or not isinstance(corpus["scenarios"], list)
    ):
        raise ValueError("unsupported v3 shadow corpus contract")

    scenarios = corpus["scenarios"]
    identifiers: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict) or set(scenario) != {
            "id", "family", "critical", "input", "recent_turns",
            "visible_entities", "expected_v2", "expected_v3",
        }:
            raise ValueError("v3 shadow scenario has an invalid shape")
        identifier = scenario["id"]
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("v3 shadow scenario ID must be non-empty")
        identifiers.append(identifier)
        if (
            not isinstance(scenario["family"], str)
            or not scenario["family"].strip()
            or not isinstance(scenario["critical"], bool)
            or not isinstance(scenario["input"], str)
            or not scenario["input"].strip()
            or not isinstance(scenario["recent_turns"], list)
            or not isinstance(scenario["visible_entities"], list)
        ):
            raise ValueError("v3 shadow scenario metadata is invalid")
        expected_v2 = scenario["expected_v2"]
        if not isinstance(expected_v2, dict) or set(expected_v2) != {
            *_V2_FIELDS, *_V2_SEQUENCE_FIELDS,
        }:
            raise ValueError("v2 shadow gold has an invalid shape")
        if (
            not isinstance(expected_v2["category"], str)
            or isinstance(expected_v2["step_count"], bool)
            or not isinstance(expected_v2["step_count"], int)
            or expected_v2["step_count"] < 0
            or any(
                isinstance(expected_v2[field], bool)
                or not isinstance(expected_v2[field], int)
                or expected_v2[field] < 0
                for field in ("step_count", "relation_count")
            )
            or (
                expected_v2["active_step_index"] is not None
                and (
                    isinstance(expected_v2["active_step_index"], bool)
                    or not isinstance(expected_v2["active_step_index"], int)
                    or expected_v2["active_step_index"] < 0
                )
            )
            or any(
                not isinstance(expected_v2[field], list)
                or any(not isinstance(value, str) or not value.strip() for value in expected_v2[field])
                for field in _V2_SEQUENCE_FIELDS
            )
        ):
            raise ValueError("v2 shadow gold values are invalid")
        expected_v3 = scenario["expected_v3"]
        if not isinstance(expected_v3, dict) or set(expected_v3) != {
            "counts", *_V3_SEQUENCE_FIELDS,
        }:
            raise ValueError("v3 shadow gold has an invalid shape")
        counts = expected_v3["counts"]
        if not isinstance(counts, dict) or set(counts) != set(_V3_COUNT_FIELDS):
            raise ValueError("v3 shadow count gold has an invalid shape")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts.values()
        ):
            raise ValueError("v3 shadow counts must be non-negative integers")
        for field in _V3_SEQUENCE_FIELDS:
            values = expected_v3[field]
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value.strip()
                for value in values
            ):
                raise ValueError(f"v3 shadow gold field {field} must be a string array")
    if len(identifiers) != len(set(identifiers)) or not scenarios:
        raise ValueError("v3 shadow corpus requires unique scenario IDs")
    return scenarios


def _signature(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise TypeError("shadow signatures must be scalar")
    return str(value)


def _score_sequence(
    ledger: SemanticEvaluationLedger,
    *,
    metric_family: str,
    expected: list[str],
    observed: list[str],
) -> bool:
    expected_values = tuple(f"value:{value}" for value in expected)
    observed_values = tuple(f"value:{value}" for value in observed)
    ledger.record_semantic_slots(
        metric_family,
        expected_slots=expected_values,
        predicted_slots=observed_values,
    )
    expected_counter = Counter(expected)
    observed_counter = Counter(observed)
    matched = sum((expected_counter & observed_counter).values())
    ledger.record_case(
        metric_family,
        expected_slots=len(expected),
        matched_slots=matched,
        elapsed_seconds=0,
        case_passed=expected_counter == observed_counter,
    )
    return expected_counter == observed_counter


def score_shadow_comparison(
    scenario: dict[str, Any],
    comparison: V2V3ShadowComparison,
    ledger: SemanticEvaluationLedger,
) -> dict[str, Any]:
    """Score exact structural labels and counts; return no utterance text."""
    if not isinstance(ledger, SemanticEvaluationLedger):
        raise TypeError("ledger must be a SemanticEvaluationLedger")
    shape = comparison_shape(comparison)
    expected_v2 = scenario["expected_v2"]
    expected_v3 = scenario["expected_v3"]
    mismatches_v2: list[str] = []
    mismatches_v3: list[str] = []

    observed_v2 = shape["v2"]
    for field in _V2_FIELDS:
        expected = _signature(expected_v2[field])
        observed = _signature(observed_v2[field])
        metric = f"v2_{field}:{scenario['family']}"
        _score_sequence(
            ledger,
            metric_family=metric,
            expected=[expected],
            observed=[observed],
        )
        if expected != observed:
            mismatches_v2.append(field)

    observed_v2 = shape["v2"]
    for field in _V2_SEQUENCE_FIELDS:
        expected_values = expected_v2[field]
        observed_values = observed_v2[field] if comparison.v2_status == "valid" else []
        metric = f"v2_{field}:{scenario['family']}"
        if not _score_sequence(
            ledger,
            metric_family=metric,
            expected=expected_values,
            observed=observed_values,
        ):
            mismatches_v2.append(field)

    v2_valid = comparison.v2_status == "valid"
    ledger.record_case(
        f"v2_contract_valid:{scenario['family']}",
        expected_slots=1,
        matched_slots=int(v2_valid),
        elapsed_seconds=0,
        case_passed=v2_valid,
    )
    if not v2_valid:
        mismatches_v2.append("contract_validity")

    v3_valid = comparison.v3_status == "valid"
    ledger.record_case(
        f"v3_contract_valid:{scenario['family']}",
        expected_slots=1,
        matched_slots=int(v3_valid),
        elapsed_seconds=0,
        case_passed=v3_valid,
    )
    if not v3_valid:
        mismatches_v3.append("contract_validity")

    observed_v3 = shape["v3"]
    for field in _V3_COUNT_FIELDS:
        expected_count = expected_v3["counts"][field]
        observed_count = observed_v3[
            "act_count" if field == "utterance_acts" else
            "event_count" if field == "events" else
            "link_count" if field == "discourse_links" else
            "fact_count" if field == "world_facts" else
            "clarification_count" if field == "clarification_candidates" else
            "evidence_span_count" if field == "evidence_spans" else
            "quote_span_count" if field == "quote_spans" else
            "speaker_mention_count" if field == "speaker_mentions" else
            "addressee_mention_count" if field == "addressee_mentions" else
            "event_attributed_source_count" if field == "event_attributed_sources" else
            "fact_attributed_source_count"
        ]
        metric = f"v3_count_{field}:{scenario['family']}"
        passed = expected_count == observed_count
        ledger.record_semantic_slots(
            metric,
            expected_slots=(f"count:{expected_count}",),
            predicted_slots=(
                () if observed_count is None else (f"count:{observed_count}",)
            ),
        )
        ledger.record_case(
            metric,
            expected_slots=1,
            matched_slots=int(passed),
            elapsed_seconds=0,
            case_passed=passed,
        )
        if not passed:
            mismatches_v3.append(f"counts.{field}")

    for field in _V3_SEQUENCE_FIELDS:
        expected_values = expected_v3[field]
        observed_values = observed_v3[field] if v3_valid else []
        metric = f"v3_{field}:{scenario['family']}"
        if not _score_sequence(
            ledger,
            metric_family=metric,
            expected=expected_values,
            observed=observed_values,
        ):
            mismatches_v3.append(field)

    return {
        "case_id": scenario["id"],
        "family": scenario["family"],
        "critical": scenario["critical"],
        "v2_status": comparison.v2_status,
        "v3_status": comparison.v3_status,
        "v2_mismatches": mismatches_v2,
        "v3_mismatches": mismatches_v3,
        "v2_duration_ms": comparison.v2_duration_ms,
        "v3_duration_ms": comparison.v3_duration_ms,
        "v2_prompt_bytes": comparison.v2_prompt_bytes,
        "v3_prompt_bytes": comparison.v3_prompt_bytes,
        "v3_error_code": comparison.v3_error_code,
        "v3_error_field": comparison.v3_error_field,
    }
