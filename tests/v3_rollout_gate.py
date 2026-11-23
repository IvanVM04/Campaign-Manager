"""Conservative release gate for the v3 player-turn migration.

A semantic Ollama pass is necessary but not sufficient: compound execution must
be integrated into the durable lifecycle, and the real SillyTavern flow must be
manually accepted. This helper never changes the production route.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from tests.v3_acceptance import V3_ACCEPTANCE_CONTRACT_ID

V3_RUNTIME_REQUIRED_CHECKS = (
    "compound_orchestrator_wired_to_durable_service",
    "virtual_projection_applies_staged_prior_operations",
    "manual_roll_resumes_same_action_checkpoint",
    "clarification_resumes_same_action_checkpoint",
    "single_atomic_commit_for_action_and_fact_operations",
    "lease_fenced_cas_on_every_transition",
    "crash_recovery_and_idempotent_mechanics_replay",
    "stale_revision_rejected_without_writes",
    "negative_controls_produce_zero_unauthorized_writes",
    "legacy_v1_v2_records_remain_replayable",
)

V3_SILLYTAVERN_REQUIRED_CHECKS = (
    "v2_compatibility_when_flags_disabled",
    "action_shadow_does_not_change_player_facing_result",
    "independent_fact_survives_unrelated_mechanics_failure",
    "quoted_report_and_negative_controls_do_not_write",
    "ambiguous_callback_abstains_or_requests_clarification",
    "compound_dependency_success_and_failure",
    "manual_roll_resumes_same_action",
    "clarification_resumes_same_checkpoint",
    "duplicate_external_turn_delivery_is_idempotent",
    "crash_recovery_reuses_execution_key",
    "stale_revision_is_rejected_without_writes",
    "chat_isolation_is_preserved",
)

_ALLOWED_CHECK_STATES = frozenset({"pass", "fail", "blocked", "not_run"})
_V3_ACCEPTANCE_SCENARIO_COUNT = 20
_V3_ACCEPTANCE_REQUIRED_GATES = (
    "full_holdout_coverage",
    "critical_repetitions",
    "critical_structural_validity",
    "critical_graph_exact_match",
    "dimension_precision",
    "dimension_recall",
    "critical_fact_false_positives",
    "repeat_stability",
)


def _normalise_checks(
    evidence: Mapping[str, Any] | None,
    *,
    required: tuple[str, ...],
    evidence_name: str,
) -> dict[str, str]:
    if evidence is None:
        raw: dict[str, Any] = {}
    elif not isinstance(evidence, Mapping):
        raise TypeError(f"{evidence_name} must be a mapping of check IDs to states")
    else:
        raw = dict(evidence)

    unexpected = set(raw) - set(required)
    if unexpected:
        raise ValueError(
            f"{evidence_name} contains unknown check IDs: "
            + ", ".join(sorted(str(item) for item in unexpected))
        )

    result: dict[str, str] = {}
    for check_id in required:
        state = raw.get(check_id, "not_run")
        if not isinstance(state, str) or state not in _ALLOWED_CHECK_STATES:
            raise ValueError(
                f"{evidence_name}.{check_id} must be one of "
                + ", ".join(sorted(_ALLOWED_CHECK_STATES))
            )
        result[check_id] = state
    return result


def _semantic_acceptance_passed(report: Mapping[str, Any] | None) -> bool:
    """Validate the full frozen holdout manifest and the selected variant's gates."""
    if not isinstance(report, Mapping):
        return False
    manifest = report.get("run_manifest")
    matrix = report.get("acceptance_matrix")
    if (
        report.get("schema_version") != 1
        or report.get("evaluation") != "player-turn-v3-acceptance"
        or not isinstance(manifest, Mapping)
        or not isinstance(matrix, Mapping)
    ):
        return False

    commit = manifest.get("git_commit")
    repetitions = manifest.get("repetitions")
    scenario_count = manifest.get("scenario_count")
    variant_count = manifest.get("variant_count")
    provider_calls = manifest.get("provider_calls")
    variants = matrix.get("variants")
    selected_name = matrix.get("selected_for_manual_review")
    if (
        manifest.get("contract_id") != V3_ACCEPTANCE_CONTRACT_ID
        or manifest.get("corpus_id") != "player-turn-v3-graph-corpus-v1"
        or manifest.get("full_corpus") is not True
        or scenario_count != _V3_ACCEPTANCE_SCENARIO_COUNT
        or isinstance(repetitions, bool)
        or not isinstance(repetitions, int)
        or repetitions < 3
        or isinstance(variant_count, bool)
        or not isinstance(variant_count, int)
        or variant_count < 1
        or isinstance(provider_calls, bool)
        or not isinstance(provider_calls, int)
        or provider_calls < scenario_count * repetitions * 2 * variant_count
        or not isinstance(commit, str)
        or re.fullmatch(r"[0-9a-fA-F]{40}", commit) is None
        or not isinstance(variants, list)
        or len(variants) != variant_count
        or not isinstance(selected_name, str)
        or not selected_name.strip()
    ):
        return False

    variant_names = [
        item.get("variant") if isinstance(item, Mapping) else None
        for item in variants
    ]
    if (
        "baseline" not in variant_names
        or len(variant_names) != len(set(variant_names))
        or matrix.get("contract_id") != V3_ACCEPTANCE_CONTRACT_ID
        or matrix.get("promotion_decision") != "eligible_for_manual_review_only"
        or matrix.get("automatic_cutover") is not False
        or matrix.get("production_route") != "v2"
        or matrix.get("v3_authority") != "none"
    ):
        return False

    selected = next(
        (
            item for item in variants
            if isinstance(item, Mapping) and item.get("variant") == selected_name
        ),
        None,
    )
    gates = selected.get("gates") if isinstance(selected, Mapping) else None
    return (
        isinstance(selected, Mapping)
        and selected.get("decision") == "eligible_for_manual_review_only"
        and selected.get("eligible_for_manual_review") is True
        and isinstance(gates, Mapping)
        and all(
            isinstance(gates.get(gate_id), Mapping)
            and gates[gate_id].get("passed") is True
            for gate_id in _V3_ACCEPTANCE_REQUIRED_GATES
        )
    )


def build_v3_rollout_decision(
    *,
    acceptance_report: Mapping[str, Any] | None,
    runtime_checks: Mapping[str, Any] | None,
    sillytavern_checks: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a review-readiness decision while keeping v2 authoritative.

    A passing result means only that a human may review a controlled rollout
    proposal. It does not change feature flags, runtime routing or authority.
    """
    runtime = _normalise_checks(
        runtime_checks,
        required=V3_RUNTIME_REQUIRED_CHECKS,
        evidence_name="runtime_checks",
    )
    sillytavern = _normalise_checks(
        sillytavern_checks,
        required=V3_SILLYTAVERN_REQUIRED_CHECKS,
        evidence_name="sillytavern_checks",
    )
    semantic_passed = _semantic_acceptance_passed(acceptance_report)
    runtime_failures = [
        check_id for check_id, state in runtime.items() if state != "pass"
    ]
    sillytavern_failures = [
        check_id for check_id, state in sillytavern.items() if state != "pass"
    ]
    runtime_passed = not runtime_failures
    sillytavern_passed = not sillytavern_failures
    eligible = semantic_passed and runtime_passed and sillytavern_passed

    blockers: list[str] = []
    if not semantic_passed:
        blockers.append("semantic_acceptance")
    blockers.extend(f"runtime:{item}" for item in runtime_failures)
    blockers.extend(f"sillytavern:{item}" for item in sillytavern_failures)

    return {
        "schema_version": 1,
        "decision": (
            "eligible_for_controlled_rollout_review" if eligible else "hold_v2"
        ),
        "production_route": "v2",
        "v3_authority": "none",
        "automatic_cutover": False,
        "gates": {
            "semantic_acceptance": {
                "passed": semantic_passed,
                "required_contract": V3_ACCEPTANCE_CONTRACT_ID,
                "observed_decision": (
                    (
                        acceptance_report.get("acceptance_matrix", {}).get("promotion_decision")
                        if isinstance(acceptance_report, Mapping)
                        and isinstance(acceptance_report.get("acceptance_matrix"), Mapping)
                        else None
                    )
                    if isinstance(acceptance_report, Mapping)
                    else None
                ),
            },
            "durable_runtime_integration": {
                "passed": runtime_passed,
                "checks": runtime,
                "non_passing": runtime_failures,
            },
            "sillytavern_manual_acceptance": {
                "passed": sillytavern_passed,
                "checks": sillytavern,
                "non_passing": sillytavern_failures,
            },
        },
        "blockers": blockers,
    }
