"""Opt-in paired v2/v3 acceptance run with predeclared one-factor ablations.

This runner is intentionally expensive and evaluation-only. It never feeds a
v3 interpretation into mechanics, world proposals, persistence or narration.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from time import perf_counter

import pytest

from tests.player_turn_interpretation_v3_shadow import (
    V3_EVIDENCE_ALIGNMENT_VERSION,
    V3_PROMPT_VERSION,
    V3_RESPONSE_SCHEMA,
    PlayerTurnInterpretationV3ShadowRunner,
)
from tests.player_turn_v3_graph_evaluation import (
    load_v3_graph_corpus,
    score_v3_graph_scenario,
)
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger
from tests.semantic_evaluation_report import (
    build_live_evaluation_report,
    write_live_evaluation_report,
)
from tests.test_real_llm_discourse_pipeline import (
    _context,
    _live_intent_runtime,
    _recent_turns,
)
from tests.v3_acceptance import (
    V3_ACCEPTANCE_CONTRACT_ID,
    V3_ACCEPTANCE_THRESHOLDS,
    build_v3_acceptance_matrix_report,
    build_v3_acceptance_variants,
    evaluate_v3_acceptance_variant,
)

pytestmark = pytest.mark.real_llm


def _positive_integer_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _selected_variants(raw: str | None, available: tuple[str, ...]) -> tuple[str, ...]:
    selected = available if raw is None or not raw.strip() else tuple(
        item.strip() for item in raw.split(",") if item.strip()
    )
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("acceptance variants must be a non-empty unique list")
    unknown = sorted(set(selected) - set(available))
    if unknown:
        raise ValueError("unknown v3 acceptance variant name")
    if "baseline" not in selected:
        raise ValueError("acceptance matrix must include the baseline variant")
    return selected


def test_real_ollama_player_turn_v3_acceptance(record_property):
    """Execute the frozen acceptance holdout and one-factor ablation matrix."""
    if os.getenv("CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_ENABLE") != "1":
        pytest.skip(
            "set CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_ENABLE=1 to run acceptance"
        )

    all_scenarios = load_v3_graph_corpus()
    corpus_sha256 = hashlib.sha256(
        json.dumps(
            all_scenarios,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
    ).hexdigest()
    scenario_filter = os.getenv(
        "CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_SCENARIO_ID"
    )
    scenarios = all_scenarios
    if scenario_filter:
        scenarios = [item for item in all_scenarios if item["id"] == scenario_filter]
        if len(scenarios) != 1:
            raise ValueError(
                "CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_SCENARIO_ID "
                "must match one graph holdout scenario"
            )
    full_corpus = scenario_filter is None

    repetitions = _positive_integer_env(
        "CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_REPETITIONS", 3
    )
    _probe_interpreter, probe_provider, _context_builder, _probe_usage = (
        _live_intent_runtime()
    )
    primary_model = probe_provider.model
    if not isinstance(primary_model, str) or not primary_model.strip():
        raise RuntimeError("the configured intent model is unavailable")
    candidate_model = os.getenv(
        "CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_CANDIDATE_MODEL"
    )
    all_variants = build_v3_acceptance_variants(
        primary_model=primary_model,
        candidate_model=candidate_model,
    )
    available_names = tuple(item.name for item in all_variants)
    selected_names = _selected_variants(
        os.getenv("CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_VARIANTS"),
        available_names,
    )
    variants = [item for item in all_variants if item.name in selected_names]

    variant_reports: list[dict] = []
    provider_calls_total = 0
    run_started = perf_counter()
    reported_commit = (
        os.getenv("CAMPAIGN_MANAGER_GIT_COMMIT")
        or os.getenv("GITHUB_SHA")
        or ""
    )
    safe_commit = (
        reported_commit
        if re.fullmatch(r"[0-9a-fA-F]{40}", reported_commit)
        else "unavailable"
    )
    schema_sha256 = hashlib.sha256(
        json.dumps(
            V3_RESPONSE_SCHEMA,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    for variant in variants:
        interpreter, provider, _builder, usage_events = _live_intent_runtime(
            intent_model=variant.model_override,
            generation_options=variant.generation_options or None,
        )
        runner = PlayerTurnInterpretationV3ShadowRunner(interpreter)
        ledger = SemanticEvaluationLedger()
        case_results: list[dict] = []
        evidence_realigned = 0
        variant_started = perf_counter()
        provider_calls = 0
        v2_valid_runs = 0
        v3_valid_runs = 0

        for repetition in range(1, repetitions + 1):
            for scenario in scenarios:
                comparison = runner.run(
                    _context(scenario),
                    scenario["input"],
                    recent_turns=_recent_turns(scenario),
                    v3_system_prompt=variant.system_prompt,
                )
                graph_result = score_v3_graph_scenario(
                    scenario,
                    comparison.v3_interpretation,
                    ledger,
                    interpretation_status=comparison.v3_status,
                )
                case_results.append({
                    "scenario_id": scenario["id"],
                    "family": scenario["family"],
                    "critical": scenario["critical"],
                    "repetition": repetition,
                    "v2_status": comparison.v2_status,
                    "v3_status": comparison.v3_status,
                    "validation_error_code": comparison.v3_error_code,
                    "validation_error_field": comparison.v3_error_field,
                    "graph_exact_match": graph_result["graph_exact_match"],
                    "mismatch_components": graph_result["mismatch_components"],
                    "components": graph_result["components"],
                    "elapsed_ms": round(comparison.v3_duration_ms, 3),
                    "v2_elapsed_ms": round(comparison.v2_duration_ms, 3),
                })
                evidence_realigned += comparison.v3_evidence_spans_realigned
                v2_valid_runs += int(comparison.v2_status == "valid")
                v3_valid_runs += int(comparison.v3_status == "valid")
                provider_calls += int(comparison.v2_prompt_bytes is not None)
                provider_calls += int(comparison.v3_prompt_bytes is not None)

        variant_elapsed = perf_counter() - variant_started
        provider_calls_total += provider_calls
        acceptance = evaluate_v3_acceptance_variant(
            variant_name=variant.name,
            scenario_ids=[item["id"] for item in scenarios],
            repetitions=repetitions,
            results=case_results,
            full_corpus=full_corpus,
        )
        prompt_sha256 = hashlib.sha256(
            variant.system_prompt.encode("utf-8")
        ).hexdigest()
        report = build_live_evaluation_report(
            evaluation_name=f"player-turn-v3-acceptance-{variant.name}",
            corpus_name="player-turn-v3-graph-corpus-v1",
            provider=provider,
            ledger=ledger,
            scenario_count=len(scenarios),
            provider_calls=provider_calls,
            elapsed_seconds=variant_elapsed,
            usage_events=usage_events,
            scenario_filter=scenario_filter,
        )
        report["run_manifest"] = {
            "git_commit": safe_commit,
            "contract_id": V3_ACCEPTANCE_CONTRACT_ID,
            "corpus_id": "player-turn-v3-graph-corpus-v1",
            "corpus_schema_version": 1,
            "corpus_sha256": corpus_sha256,
            "scenario_count": len(scenarios),
            "repetitions": repetitions,
            "model": provider.model,
            "model_digest": report["metadata"]["model_digest"],
            "ollama_version": report["metadata"]["ollama_version"],
            "thinking": report["metadata"]["think"],
            "timeout_seconds": report["metadata"]["timeout_seconds"],
            "generation_options": report["metadata"]["generation_options"],
            "changed_factor": variant.changed_factor,
            "variant": variant.name,
            "prompt_version": (
                V3_PROMPT_VERSION
                if variant.name != "without_coverage_procedure"
                else "player-turn-v3-without-coverage-procedure-ablation-v1"
            ),
            "prompt_sha256": prompt_sha256,
            "evidence_alignment_version": V3_EVIDENCE_ALIGNMENT_VERSION,
            "schema_version": 3,
            "schema_sha256": schema_sha256,
            "production_route": "v2",
            "v3_authority": "none",
        }
        report["paired_status"] = {
            "v2_valid_runs": v2_valid_runs,
            "v3_valid_runs": v3_valid_runs,
            "provider_calls": provider_calls,
            "evidence_spans_realigned": evidence_realigned,
        }
        report["case_results"] = case_results
        report["acceptance"] = acceptance
        report["acceptance"]["thresholds"] = dict(V3_ACCEPTANCE_THRESHOLDS)
        variant_reports.append({
            "variant": variant.name,
            "changed_factor": variant.changed_factor,
            "acceptance": acceptance,
            "run_manifest": report["run_manifest"],
            "report": report,
        })
        record_property(
            f"v3_acceptance_{variant.name}_decision",
            acceptance["decision"],
        )
        record_property(
            f"v3_acceptance_{variant.name}_critical_exact",
            acceptance["critical"]["graph_exact_majority_rate"],
        )
        record_property(
            f"v3_acceptance_{variant.name}_structural_validity",
            acceptance["critical"]["structural_validity"],
        )
        print(
            f"v3 acceptance {variant.name}: "
            f"{acceptance['decision']}; "
            f"graph_exact={acceptance['critical']['graph_exact_majority_rate']}; "
            f"validity={acceptance['critical']['structural_validity']}"
        )

    matrix = build_v3_acceptance_matrix_report(
        contract_id=V3_ACCEPTANCE_CONTRACT_ID,
        variant_reports=[item["acceptance"] for item in variant_reports],
    )
    report = {
        "schema_version": 1,
        "evaluation": "player-turn-v3-acceptance",
        "run_manifest": {
            "git_commit": safe_commit,
            "contract_id": V3_ACCEPTANCE_CONTRACT_ID,
            "corpus_id": "player-turn-v3-graph-corpus-v1",
            "corpus_schema_version": 1,
            "corpus_sha256": corpus_sha256,
            "scenario_count": len(scenarios),
            "full_corpus": full_corpus,
            "repetitions": repetitions,
            "variant_count": len(variant_reports),
            "provider_calls": provider_calls_total,
            "elapsed_seconds": round(perf_counter() - run_started, 3),
            "production_route": "v2",
            "v3_authority": "none",
        },
        "acceptance_matrix": matrix,
        "variant_reports": variant_reports,
        "thresholds": dict(V3_ACCEPTANCE_THRESHOLDS),
    }
    report_path = os.getenv(
        "CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_REPORT_PATH"
    )
    if report_path:
        written = write_live_evaluation_report(report, path=report_path)
        if written is not None:
            record_property("v3_acceptance_report", written)

    record_property("v3_acceptance_contract_id", V3_ACCEPTANCE_CONTRACT_ID)
    record_property("v3_acceptance_promotion_decision", matrix["promotion_decision"])
    record_property("v3_acceptance_full_corpus", full_corpus)
    record_property("v3_acceptance_repetitions", repetitions)
    print(
        "v3 acceptance matrix decision: "
        f"{matrix['promotion_decision']}; "
        f"selected_for_manual_review={matrix['selected_for_manual_review']}"
    )
