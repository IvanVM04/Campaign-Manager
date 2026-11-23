import pytest

from tests.v3_acceptance import V3_ACCEPTANCE_CONTRACT_ID
from tests.v3_rollout_gate import (
    V3_RUNTIME_REQUIRED_CHECKS,
    V3_SILLYTAVERN_REQUIRED_CHECKS,
    build_v3_rollout_decision,
)


def _accepted_report():
    gate_ids = (
        "full_holdout_coverage",
        "critical_repetitions",
        "critical_structural_validity",
        "critical_graph_exact_match",
        "dimension_precision",
        "dimension_recall",
        "critical_fact_false_positives",
        "repeat_stability",
    )
    baseline = {
        "variant": "baseline",
        "mode": "acceptance",
        "decision": "eligible_for_manual_review_only",
        "eligible_for_manual_review": True,
        "run_matrix": {
            "scenario_count": 20,
            "repetitions": 3,
            "expected_runs": 60,
            "observed_runs": 60,
            "missing_runs": 0,
            "duplicate_run_keys": False,
            "full_corpus": True,
        },
        "gates": {gate_id: {"passed": True} for gate_id in gate_ids},
    }
    return {
        "schema_version": 1,
        "evaluation": "player-turn-v3-acceptance",
        "run_manifest": {
            "git_commit": "a" * 40,
            "contract_id": V3_ACCEPTANCE_CONTRACT_ID,
            "corpus_id": "player-turn-v3-graph-corpus-v1",
            "scenario_count": 20,
            "full_corpus": True,
            "repetitions": 3,
            "variant_count": 1,
            "provider_calls": 120,
        },
        "acceptance_matrix": {
            "contract_id": V3_ACCEPTANCE_CONTRACT_ID,
            "promotion_decision": "eligible_for_manual_review_only",
            "selected_for_manual_review": "baseline",
            "automatic_cutover": False,
            "production_route": "v2",
            "v3_authority": "none",
            "variants": [baseline],
        },
    }


def _passing_evidence(required):
    return {check_id: "pass" for check_id in required}


def test_rollout_gate_holds_v2_when_acceptance_or_manual_evidence_is_missing():
    decision = build_v3_rollout_decision(
        acceptance_report=None,
        runtime_checks=None,
        sillytavern_checks=None,
    )

    assert decision["decision"] == "hold_v2"
    assert decision["production_route"] == "v2"
    assert decision["v3_authority"] == "none"
    assert decision["automatic_cutover"] is False
    assert decision["gates"]["semantic_acceptance"]["passed"] is False
    assert all(
        state == "not_run"
        for state in decision["gates"]["durable_runtime_integration"]["checks"].values()
    )
    assert all(
        state == "not_run"
        for state in decision["gates"]["sillytavern_manual_acceptance"]["checks"].values()
    )


def test_ollama_semantic_acceptance_alone_cannot_authorize_v3_rollout():
    decision = build_v3_rollout_decision(
        acceptance_report=_accepted_report(),
        runtime_checks=None,
        sillytavern_checks=None,
    )

    assert decision["gates"]["semantic_acceptance"]["passed"] is True
    assert decision["decision"] == "hold_v2"
    assert "runtime:compound_orchestrator_wired_to_durable_service" in decision["blockers"]
    assert "sillytavern:v2_compatibility_when_flags_disabled" in decision["blockers"]


def test_runtime_integration_and_manual_acceptance_are_independent_gates():
    decision = build_v3_rollout_decision(
        acceptance_report=_accepted_report(),
        runtime_checks=_passing_evidence(V3_RUNTIME_REQUIRED_CHECKS),
        sillytavern_checks={
            **_passing_evidence(V3_SILLYTAVERN_REQUIRED_CHECKS),
            "crash_recovery_reuses_execution_key": "not_run",
        },
    )

    assert decision["gates"]["semantic_acceptance"]["passed"] is True
    assert decision["gates"]["durable_runtime_integration"]["passed"] is True
    assert decision["gates"]["sillytavern_manual_acceptance"]["passed"] is False
    assert decision["decision"] == "hold_v2"
    assert decision["blockers"] == [
        "sillytavern:crash_recovery_reuses_execution_key"
    ]


def test_all_three_gates_only_allow_manual_review_not_automatic_cutover():
    decision = build_v3_rollout_decision(
        acceptance_report=_accepted_report(),
        runtime_checks=_passing_evidence(V3_RUNTIME_REQUIRED_CHECKS),
        sillytavern_checks=_passing_evidence(V3_SILLYTAVERN_REQUIRED_CHECKS),
    )

    assert decision["decision"] == "eligible_for_controlled_rollout_review"
    assert decision["blockers"] == []
    assert decision["production_route"] == "v2"
    assert decision["v3_authority"] == "none"
    assert decision["automatic_cutover"] is False


@pytest.mark.parametrize(
    "matrix_overrides",
    [
        {"contract_id": "unknown-contract"},
        {"promotion_decision": "hold_v2"},
        {"production_route": "v3"},
        {"automatic_cutover": True},
    ],
)
def test_rollout_gate_rejects_non_qualifying_semantic_matrix(matrix_overrides):
    report = _accepted_report()
    report["acceptance_matrix"].update(matrix_overrides)
    decision = build_v3_rollout_decision(
        acceptance_report=report,
        runtime_checks=_passing_evidence(V3_RUNTIME_REQUIRED_CHECKS),
        sillytavern_checks=_passing_evidence(V3_SILLYTAVERN_REQUIRED_CHECKS),
    )

    assert decision["decision"] == "hold_v2"
    assert decision["blockers"][0] == "semantic_acceptance"


def test_semantic_gate_requires_complete_frozen_holdout_manifest():
    report = _accepted_report()
    report["run_manifest"]["full_corpus"] = False

    decision = build_v3_rollout_decision(
        acceptance_report=report,
        runtime_checks=_passing_evidence(V3_RUNTIME_REQUIRED_CHECKS),
        sillytavern_checks=_passing_evidence(V3_SILLYTAVERN_REQUIRED_CHECKS),
    )

    assert decision["decision"] == "hold_v2"
    assert decision["blockers"][0] == "semantic_acceptance"


def test_semantic_gate_rejects_selected_variant_with_missing_failed_gate():
    report = _accepted_report()
    report["acceptance_matrix"]["variants"][0]["gates"]["dimension_recall"]["passed"] = False

    decision = build_v3_rollout_decision(
        acceptance_report=report,
        runtime_checks=_passing_evidence(V3_RUNTIME_REQUIRED_CHECKS),
        sillytavern_checks=_passing_evidence(V3_SILLYTAVERN_REQUIRED_CHECKS),
    )

    assert decision["decision"] == "hold_v2"
    assert decision["blockers"][0] == "semantic_acceptance"


def test_semantic_gate_rejects_acceptance_report_without_baseline_variant():
    report = _accepted_report()
    report["acceptance_matrix"]["variants"][0]["variant"] = "fixed_sampling"
    report["acceptance_matrix"]["selected_for_manual_review"] = "fixed_sampling"

    decision = build_v3_rollout_decision(
        acceptance_report=report,
        runtime_checks=_passing_evidence(V3_RUNTIME_REQUIRED_CHECKS),
        sillytavern_checks=_passing_evidence(V3_SILLYTAVERN_REQUIRED_CHECKS),
    )

    assert decision["decision"] == "hold_v2"
    assert decision["blockers"][0] == "semantic_acceptance"


def test_semantic_gate_rejects_duplicate_run_keys_from_real_acceptance_shape():
    report = _accepted_report()
    report["acceptance_matrix"]["variants"][0]["run_matrix"]["duplicate_run_keys"] = True

    decision = build_v3_rollout_decision(
        acceptance_report=report,
        runtime_checks=_passing_evidence(V3_RUNTIME_REQUIRED_CHECKS),
        sillytavern_checks=_passing_evidence(V3_SILLYTAVERN_REQUIRED_CHECKS),
    )

    assert decision["decision"] == "hold_v2"
    assert decision["blockers"][0] == "semantic_acceptance"


def test_rollout_gate_rejects_unknown_evidence_check_ids():
    with pytest.raises(ValueError, match="unknown check IDs"):
        build_v3_rollout_decision(
            acceptance_report=_accepted_report(),
            runtime_checks={"pretend_everything_passed": "pass"},
            sillytavern_checks=_passing_evidence(V3_SILLYTAVERN_REQUIRED_CHECKS),
        )


@pytest.mark.parametrize("state", ["pending", "success", True, None])
def test_rollout_gate_rejects_unrecognised_evidence_states(state):
    with pytest.raises(ValueError, match="must be one of"):
        build_v3_rollout_decision(
            acceptance_report=_accepted_report(),
            runtime_checks={
                **_passing_evidence(V3_RUNTIME_REQUIRED_CHECKS),
                V3_RUNTIME_REQUIRED_CHECKS[0]: state,
            },
            sillytavern_checks=_passing_evidence(V3_SILLYTAVERN_REQUIRED_CHECKS),
        )


def test_rollout_gate_requires_mapping_inputs():
    with pytest.raises(TypeError, match="runtime_checks must be a mapping"):
        build_v3_rollout_decision(
            acceptance_report=_accepted_report(),
            runtime_checks=["pass"],
            sillytavern_checks=_passing_evidence(V3_SILLYTAVERN_REQUIRED_CHECKS),
        )
