import copy

import pytest

from tests.player_turn_interpretation_v3_shadow import V3_SYSTEM_PROMPT
from tests.player_turn_v3_graph_evaluation import load_v3_graph_corpus
from tests.v3_acceptance import (
    V3_ACCEPTANCE_CONTRACT_ID,
    build_v3_acceptance_matrix_report,
    build_v3_acceptance_variants,
    evaluate_v3_acceptance_variant,
)


def _perfect_results(scenario_ids, *, repetitions=3):
    dimensions = (
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
    components = {
        name: {
            "expected": 1,
            "predicted": 1,
            "matched": 1,
            "false_positives": 0,
            "false_negatives": 0,
        }
        for name in dimensions
    }
    return [
        {
            "scenario_id": scenario_id,
            "family": "test",
            "critical": True,
            "repetition": repetition,
            "v2_status": "valid",
            "v3_status": "valid",
            "graph_exact_match": True,
            "components": copy.deepcopy(components),
            "elapsed_ms": 100.0,
        }
        for scenario_id in scenario_ids
        for repetition in range(1, repetitions + 1)
    ]


def test_acceptance_variants_change_one_factor_at_a_time():
    variants = build_v3_acceptance_variants(
        primary_model="model-a:latest",
        candidate_model="model-b:latest",
    )
    by_name = {item.name: item for item in variants}

    assert set(by_name) == {
        "baseline",
        "without_coverage_procedure",
        "fixed_sampling",
        "candidate_model",
    }
    baseline = by_name["baseline"]
    prompt_ablation = by_name["without_coverage_procedure"]
    sampling_ablation = by_name["fixed_sampling"]
    model_ablation = by_name["candidate_model"]

    assert baseline.system_prompt == V3_SYSTEM_PROMPT
    assert prompt_ablation.model_override == baseline.model_override
    assert prompt_ablation.generation_options == baseline.generation_options
    assert "PROCEDIMIENTO DE COBERTURA" not in prompt_ablation.system_prompt
    assert "SEPARA LOS PLANOS SEMÁNTICOS" in prompt_ablation.system_prompt
    assert sampling_ablation.model_override == baseline.model_override
    assert sampling_ablation.system_prompt == baseline.system_prompt
    assert sampling_ablation.generation_options == {
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": 1729,
    }
    assert model_ablation.model_override == "model-b:latest"
    assert model_ablation.system_prompt == baseline.system_prompt
    assert model_ablation.generation_options == baseline.generation_options


@pytest.mark.parametrize(
    ("primary", "candidate"),
    [
        ("", None),
        ("bad model name", None),
        ("model-a", "model-a"),
        ("model-a", "another bad model"),
    ],
)
def test_acceptance_variants_reject_invalid_model_matrix(primary, candidate):
    with pytest.raises(ValueError):
        build_v3_acceptance_variants(
            primary_model=primary,
            candidate_model=candidate,
        )


def test_acceptance_gates_pass_only_with_full_repeated_critical_holdout():
    scenario_ids = [item["id"] for item in load_v3_graph_corpus()]
    results = _perfect_results(scenario_ids)

    report = evaluate_v3_acceptance_variant(
        variant_name="baseline",
        scenario_ids=scenario_ids,
        repetitions=3,
        results=results,
        full_corpus=True,
    )

    assert report["mode"] == "acceptance"
    assert report["decision"] == "eligible_for_manual_review_only"
    assert report["eligible_for_manual_review"] is True
    assert all(gate["passed"] for gate in report["gates"].values())
    assert report["critical"]["structural_validity"] == 1.0
    assert report["critical"]["graph_exact_majority_rate"] == 1.0
    assert report["critical"]["repeat_stability_agreement"] == 1.0
    assert report["critical"]["fact_false_positives"] == 0
    assert report["dimensions"]["events"]["precision"] == 1.0
    assert report["dimensions"]["events"]["recall"] == 1.0


def test_acceptance_gate_blocks_fact_false_positives_and_weak_dimensions():
    scenario_ids = ["case_01", "case_02"]
    results = _perfect_results(scenario_ids)
    for item in results:
        item["components"]["facts"] = {
            "expected": 1,
            "predicted": 2,
            "matched": 1,
            "false_positives": 1,
            "false_negatives": 0,
        }

    report = evaluate_v3_acceptance_variant(
        variant_name="baseline",
        scenario_ids=scenario_ids,
        repetitions=3,
        results=results,
        full_corpus=False,
    )

    assert report["decision"] == "hold_v2"
    assert report["gates"]["critical_fact_false_positives"]["passed"] is False
    assert report["gates"]["dimension_precision"]["passed"] is False
    assert report["critical"]["fact_false_positives"] == 6


def test_acceptance_gate_blocks_recall_even_when_precision_is_high():
    scenario_ids = ["case_01", "case_02"]
    results = _perfect_results(scenario_ids)
    for item in results:
        item["components"]["events"] = {
            "expected": 2,
            "predicted": 1,
            "matched": 1,
            "false_positives": 0,
            "false_negatives": 1,
        }

    report = evaluate_v3_acceptance_variant(
        variant_name="baseline",
        scenario_ids=scenario_ids,
        repetitions=3,
        results=results,
        full_corpus=False,
    )

    assert report["dimensions"]["events"]["precision"] == 1.0
    assert report["dimensions"]["events"]["recall"] == 0.5
    assert report["gates"]["dimension_precision"]["passed"] is True
    assert report["gates"]["dimension_recall"]["passed"] is False
    assert report["decision"] == "hold_v2"


def test_acceptance_gate_blocks_incomplete_and_under_repeated_runs():
    scenario_ids = [item["id"] for item in load_v3_graph_corpus()]
    results = _perfect_results(scenario_ids)
    incomplete = evaluate_v3_acceptance_variant(
        variant_name="baseline",
        scenario_ids=scenario_ids,
        repetitions=3,
        results=results[:-1],
        full_corpus=True,
    )
    under_repeated = evaluate_v3_acceptance_variant(
        variant_name="baseline",
        scenario_ids=scenario_ids,
        repetitions=2,
        results=_perfect_results(scenario_ids, repetitions=2),
        full_corpus=True,
    )
    filtered = evaluate_v3_acceptance_variant(
        variant_name="baseline",
        scenario_ids=["case_01"],
        repetitions=3,
        results=_perfect_results(["case_01"]),
        full_corpus=False,
    )

    assert incomplete["gates"]["full_holdout_coverage"]["passed"] is False
    assert under_repeated["gates"]["critical_repetitions"]["passed"] is False
    assert under_repeated["gates"]["full_holdout_coverage"]["passed"] is True
    assert filtered["gates"]["full_holdout_coverage"]["passed"] is False
    assert all(
        item["decision"] == "hold_v2"
        for item in (incomplete, under_repeated, filtered)
    )


def test_acceptance_gate_measures_repeat_stability_per_scenario():
    scenario_ids = ["case_01"]
    results = _perfect_results(scenario_ids)
    results[-1]["graph_exact_match"] = False

    report = evaluate_v3_acceptance_variant(
        variant_name="baseline",
        scenario_ids=scenario_ids,
        repetitions=3,
        results=results,
        full_corpus=False,
    )

    assert report["critical"]["repeat_stability_agreement"] == pytest.approx(2 / 3, abs=0.0001)
    assert report["gates"]["repeat_stability"]["passed"] is False


def test_acceptance_matrix_never_authorizes_automatic_cutover():
    scenario_ids = [item["id"] for item in load_v3_graph_corpus()]
    accepted = evaluate_v3_acceptance_variant(
        variant_name="baseline",
        scenario_ids=scenario_ids,
        repetitions=3,
        results=_perfect_results(scenario_ids),
        full_corpus=True,
    )
    matrix = build_v3_acceptance_matrix_report(
        contract_id=V3_ACCEPTANCE_CONTRACT_ID,
        variant_reports=[accepted],
    )

    assert matrix["promotion_decision"] == "eligible_for_manual_review_only"
    assert matrix["selected_for_manual_review"] == "baseline"
    assert matrix["automatic_cutover"] is False
    assert matrix["production_route"] == "v2"
    assert matrix["v3_authority"] == "none"


def test_acceptance_matrix_rejects_unknown_contract():
    with pytest.raises(ValueError, match="unknown v3 acceptance contract"):
        build_v3_acceptance_matrix_report(
            contract_id="unknown",
            variant_reports=[],
        )
