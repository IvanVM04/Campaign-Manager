"""Predeclared acceptance gates and controlled ablations for player-turn v3.

This is evaluation-only code. It cannot change the production interpreter route
or grant v3 authority to select mechanics or persist world facts.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Any

from tests.player_turn_interpretation_v3_shadow import V3_SYSTEM_PROMPT

V3_ACCEPTANCE_CONTRACT_ID = "player-turn-v3-acceptance-2026-11-22-v1"
V3_ACCEPTANCE_MIN_REPETITIONS = 3

# These gates are fixed before the live run. They are deliberately per-dimension:
# a high aggregate score cannot hide a weak relation/evidence/fact dimension.
V3_ACCEPTANCE_THRESHOLDS: dict[str, float | int] = {
    "critical_structural_validity": 1.0,
    "critical_graph_exact_match": 0.80,
    "minimum_dimension_precision": 0.90,
    "minimum_dimension_recall": 0.80,
    "critical_fact_false_positives": 0,
    "repeat_stability_agreement": 0.95,
    "minimum_repetitions": V3_ACCEPTANCE_MIN_REPETITIONS,
}

_DIMENSIONS = (
    "acts",
    "events",
    "links",
    "facts",
    "clarifications",
    "event_sources",
    "fact_sources",
    "discourse_edges",
    "clarification_edges",
)
_SAFE_MODEL = re.compile(r"^[A-Za-z0-9_.:/@+-]{1,160}$")


@dataclass(frozen=True, slots=True)
class V3AcceptanceVariant:
    """One controlled condition; each named condition changes one factor."""

    name: str
    changed_factor: str
    model_override: str
    system_prompt: str
    generation_options: dict[str, int | float]

    def manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "changed_factor": self.changed_factor,
            "model": self.model_override,
            "generation_options": dict(self.generation_options),
        }


def _without_coverage_procedure() -> str:
    start_marker = "PROCEDIMIENTO DE COBERTURA — SIGUE ESTE ORDEN INTERNAMENTE"
    end_marker = "SEPARA LOS PLANOS SEMÁNTICOS"
    start = V3_SYSTEM_PROMPT.find(start_marker)
    end = V3_SYSTEM_PROMPT.find(end_marker, start + len(start_marker))
    if start < 0 or end <= start:
        raise RuntimeError("v3 prompt coverage section boundaries changed")
    return (
        V3_SYSTEM_PROMPT[:start]
        + "COBERTURA ABREVIADA (ABLATION CONTROLADA)\n"
        + "Representa las proposiciones explícitas del turno y conserva las "
        "distinciones de autoridad y evidencia descritas en las secciones "
        "restantes del prompt.\n\n"
        + V3_SYSTEM_PROMPT[end:]
    )


def build_v3_acceptance_variants(
    *,
    primary_model: str,
    candidate_model: str | None = None,
) -> tuple[V3AcceptanceVariant, ...]:
    """Return a deterministic one-factor-at-a-time ablation matrix."""
    if not isinstance(primary_model, str) or not _SAFE_MODEL.fullmatch(primary_model):
        raise ValueError("primary_model must be a bounded model identifier")
    variants = [
        V3AcceptanceVariant(
            name="baseline",
            changed_factor="none",
            model_override=primary_model,
            system_prompt=V3_SYSTEM_PROMPT,
            generation_options={},
        ),
        V3AcceptanceVariant(
            name="without_coverage_procedure",
            changed_factor="prompt",
            model_override=primary_model,
            system_prompt=_without_coverage_procedure(),
            generation_options={},
        ),
        V3AcceptanceVariant(
            name="fixed_sampling",
            changed_factor="generation_options",
            model_override=primary_model,
            system_prompt=V3_SYSTEM_PROMPT,
            generation_options={
                "temperature": 0.0,
                "top_p": 1.0,
                "seed": 1729,
            },
        ),
    ]
    if candidate_model is not None:
        if (
            not isinstance(candidate_model, str)
            or not _SAFE_MODEL.fullmatch(candidate_model)
        ):
            raise ValueError("candidate_model must be a bounded model identifier")
        if candidate_model.casefold() == primary_model.casefold():
            raise ValueError("candidate_model must differ from primary_model")
        variants.append(V3AcceptanceVariant(
            name="candidate_model",
            changed_factor="model",
            model_override=candidate_model,
            system_prompt=V3_SYSTEM_PROMPT,
            generation_options={},
        ))
    return tuple(variants)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator > 0 else None


def evaluate_v3_acceptance_variant(
    *,
    variant_name: str,
    scenario_ids: list[str],
    repetitions: int,
    results: list[dict[str, Any]],
    full_corpus: bool,
) -> dict[str, Any]:
    """Evaluate content-free per-run graph results against the frozen gates."""
    if not isinstance(variant_name, str) or not variant_name:
        raise ValueError("variant_name must be non-empty")
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    if (
        not scenario_ids
        or any(not isinstance(item, str) or not item for item in scenario_ids)
        or len(set(scenario_ids)) != len(scenario_ids)
    ):
        raise ValueError("scenario_ids must be unique non-empty identifiers")

    expected_keys = {
        (scenario_id, repeat)
        for scenario_id in scenario_ids
        for repeat in range(1, repetitions + 1)
    }
    observed_keys: list[tuple[str, int]] = []
    critical_results: list[dict[str, Any]] = []
    component_counts = {
        name: {"expected": 0, "predicted": 0, "matched": 0}
        for name in _DIMENSIONS
    }
    critical_fact_false_positives = 0
    elapsed_samples: list[float] = []

    for item in results:
        if not isinstance(item, dict):
            raise TypeError("acceptance result must be an object")
        scenario_id = item.get("scenario_id")
        repeat = item.get("repetition")
        if (
            not isinstance(scenario_id, str)
            or isinstance(repeat, bool)
            or not isinstance(repeat, int)
        ):
            raise TypeError("acceptance result has an invalid run key")
        observed_keys.append((scenario_id, repeat))
        if scenario_id not in scenario_ids or not 1 <= repeat <= repetitions:
            raise ValueError("acceptance result is outside the declared run matrix")
        if item.get("critical") is True:
            critical_results.append(item)
        elapsed = item.get("elapsed_ms")
        if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and elapsed >= 0:
            elapsed_samples.append(float(elapsed))

    duplicate_keys = len(observed_keys) != len(set(observed_keys))
    observed_set = set(observed_keys)
    missing_keys = expected_keys - observed_set
    complete = not duplicate_keys and not missing_keys and len(results) == len(expected_keys)

    for item in critical_results:
        components = item.get("components")
        if not isinstance(components, dict):
            continue
        for dimension in _DIMENSIONS:
            component = components.get(dimension)
            if not isinstance(component, dict):
                continue
            for metric in ("expected", "predicted", "matched"):
                value = component.get(metric)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    component_counts[dimension][metric] += value
        facts = components.get("facts")
        if isinstance(facts, dict):
            false_positives = facts.get("false_positives")
            if isinstance(false_positives, int) and not isinstance(false_positives, bool):
                critical_fact_false_positives += max(0, false_positives)

    dimension_metrics: dict[str, dict[str, int | float | None]] = {}
    for dimension, counts in component_counts.items():
        expected = counts["expected"]
        predicted = counts["predicted"]
        matched = counts["matched"]
        dimension_metrics[dimension] = {
            **counts,
            "precision": _ratio(matched, predicted),
            "recall": _ratio(matched, expected),
            "f1": (
                _ratio(2 * matched, expected + predicted)
                if expected + predicted > 0
                else None
            ),
        }

    validity_count = sum(item.get("v3_status") == "valid" for item in critical_results)
    critical_run_count = len(critical_results)
    structural_validity = _ratio(validity_count, critical_run_count)

    by_scenario: dict[str, list[bool]] = defaultdict(list)
    for item in critical_results:
        if isinstance(item.get("graph_exact_match"), bool):
            by_scenario[item["scenario_id"]].append(item["graph_exact_match"])

    majority_exact = 0
    agreement_numerator = 0
    agreement_denominator = 0
    for scenario_id, outcomes in by_scenario.items():
        if not outcomes:
            continue
        counts = Counter(outcomes)
        majority_exact += int(counts[True] > counts[False])
        agreement_numerator += max(counts.values())
        agreement_denominator += len(outcomes)

    critical_scenario_count = len(scenario_ids) if full_corpus else len(by_scenario)
    graph_exact_rate = _ratio(majority_exact, critical_scenario_count)
    stability = _ratio(agreement_numerator, agreement_denominator)

    precision_failures = [
        name for name, metric in dimension_metrics.items()
        if metric["precision"] is not None
        and metric["precision"] < float(V3_ACCEPTANCE_THRESHOLDS["minimum_dimension_precision"])
    ]
    recall_failures = [
        name for name, metric in dimension_metrics.items()
        if metric["recall"] is not None
        and metric["recall"] < float(V3_ACCEPTANCE_THRESHOLDS["minimum_dimension_recall"])
    ]

    gates = {
        "full_holdout_coverage": {
            "passed": bool(full_corpus and complete),
            "observed": complete and full_corpus,
            "required": True,
        },
        "critical_repetitions": {
            "passed": repetitions >= V3_ACCEPTANCE_MIN_REPETITIONS,
            "observed": repetitions,
            "required": V3_ACCEPTANCE_MIN_REPETITIONS,
        },
        "critical_structural_validity": {
            "passed": structural_validity == 1.0,
            "observed": structural_validity,
            "required": 1.0,
            "valid_runs": validity_count,
            "total_runs": critical_run_count,
        },
        "critical_graph_exact_match": {
            "passed": graph_exact_rate is not None
            and graph_exact_rate >= float(V3_ACCEPTANCE_THRESHOLDS["critical_graph_exact_match"]),
            "observed": graph_exact_rate,
            "required": V3_ACCEPTANCE_THRESHOLDS["critical_graph_exact_match"],
            "majority_exact_scenarios": majority_exact,
            "critical_scenarios": critical_scenario_count,
        },
        "dimension_precision": {
            "passed": not precision_failures,
            "observed": dimension_metrics,
            "required": V3_ACCEPTANCE_THRESHOLDS["minimum_dimension_precision"],
            "failing_dimensions": precision_failures,
        },
        "dimension_recall": {
            "passed": not recall_failures,
            "observed": dimension_metrics,
            "required": V3_ACCEPTANCE_THRESHOLDS["minimum_dimension_recall"],
            "failing_dimensions": recall_failures,
        },
        "critical_fact_false_positives": {
            "passed": critical_fact_false_positives == 0,
            "observed": critical_fact_false_positives,
            "required": 0,
        },
        "repeat_stability": {
            "passed": stability is not None
            and stability >= float(V3_ACCEPTANCE_THRESHOLDS["repeat_stability_agreement"]),
            "observed": stability,
            "required": V3_ACCEPTANCE_THRESHOLDS["repeat_stability_agreement"],
        },
    }
    eligible = all(item["passed"] for item in gates.values())
    mean_latency = round(mean(elapsed_samples), 3) if elapsed_samples else None
    recall_values = [
        metric["recall"] for metric in dimension_metrics.values()
        if metric["recall"] is not None
    ]
    macro_recall = round(mean(recall_values), 4) if recall_values else None
    return {
        "variant": variant_name,
        "mode": "acceptance" if repetitions >= V3_ACCEPTANCE_MIN_REPETITIONS and full_corpus else "diagnostic",
        "decision": (
            "eligible_for_manual_review_only"
            if eligible
            else "hold_v2"
        ),
        "eligible_for_manual_review": eligible,
        "run_matrix": {
            "scenario_count": len(scenario_ids),
            "repetitions": repetitions,
            "expected_runs": len(expected_keys),
            "observed_runs": len(results),
            "missing_runs": len(missing_keys),
            "duplicate_run_keys": duplicate_keys,
            "full_corpus": full_corpus,
        },
        "critical": {
            "run_count": critical_run_count,
            "structural_validity": structural_validity,
            "graph_exact_majority_rate": graph_exact_rate,
            "repeat_stability_agreement": stability,
            "fact_false_positives": critical_fact_false_positives,
        },
        "dimensions": dimension_metrics,
        "gates": gates,
        "summary": {
            "macro_dimension_recall": macro_recall,
            "mean_v3_latency_ms": mean_latency,
        },
    }


def build_v3_acceptance_matrix_report(
    *,
    contract_id: str,
    variant_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare ablations without selecting a production model or changing routes."""
    if contract_id != V3_ACCEPTANCE_CONTRACT_ID:
        raise ValueError("unknown v3 acceptance contract")
    baseline = next((item for item in variant_reports if item.get("variant") == "baseline"), None)
    eligible = [item for item in variant_reports if item.get("eligible_for_manual_review") is True]
    ranked = sorted(
        eligible,
        key=lambda item: (
            float(item.get("critical", {}).get("graph_exact_majority_rate") or 0),
            float(item.get("summary", {}).get("macro_dimension_recall") or 0),
            -float(item.get("summary", {}).get("mean_v3_latency_ms") or 0),
        ),
        reverse=True,
    )
    selected = ranked[0]["variant"] if ranked else None

    comparisons: list[dict[str, Any]] = []
    baseline_exact = (
        baseline.get("critical", {}).get("graph_exact_majority_rate")
        if baseline is not None else None
    )
    baseline_recall = (
        baseline.get("summary", {}).get("macro_dimension_recall")
        if baseline is not None else None
    )
    for item in variant_reports:
        exact = item.get("critical", {}).get("graph_exact_majority_rate")
        recall = item.get("summary", {}).get("macro_dimension_recall")
        comparisons.append({
            "variant": item.get("variant"),
            "decision": item.get("decision"),
            "graph_exact_delta_vs_baseline": (
                round(exact - baseline_exact, 4)
                if isinstance(exact, (int, float)) and isinstance(baseline_exact, (int, float))
                else None
            ),
            "macro_recall_delta_vs_baseline": (
                round(recall - baseline_recall, 4)
                if isinstance(recall, (int, float)) and isinstance(baseline_recall, (int, float))
                else None
            ),
        })

    return {
        "contract_id": contract_id,
        "production_route": "v2",
        "v3_authority": "none",
        "promotion_decision": (
            "eligible_for_manual_review_only"
            if selected is not None
            else "hold_v2"
        ),
        "selected_for_manual_review": selected,
        "automatic_cutover": False,
        "variants": variant_reports,
        "ablation_comparisons": comparisons,
    }
