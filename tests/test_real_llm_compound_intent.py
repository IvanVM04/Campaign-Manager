"""Opt-in Ollama evaluation for multi-step, multi-actor player messages."""

from __future__ import annotations

import json
import os
from pathlib import Path
from time import perf_counter

import pytest

from tests.compound_intent_evaluation import (
    build_compound_intent_report,
    load_compound_intent_corpus,
    score_compound_intent_analysis,
)
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger
from tests.test_real_llm_discourse_pipeline import (
    _context,
    _live_intent_runtime,
    _recent_turns,
)

pytestmark = pytest.mark.real_llm


def test_real_ollama_compound_intent_understanding_holdout(record_property):
    """Measure per-step actors, modalities, polarity and active-step selection."""
    scenarios, step_gold = load_compound_intent_corpus()
    scenario_filter = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_SCENARIO_ID")
    if scenario_filter:
        scenarios = [item for item in scenarios if item["id"] == scenario_filter]
        if len(scenarios) != 1:
            raise ValueError(
                "CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_SCENARIO_ID must match one held-out scenario"
            )

    interpreter, provider, _context_builder, usage_events = _live_intent_runtime()
    ledger = SemanticEvaluationLedger()
    critical_failures: list[str] = []
    observational_failures: list[str] = []
    calls = 0
    started = perf_counter()

    for scenario in scenarios:
        repetitions = 3 if scenario["critical"] and not scenario_filter else 1
        for repetition in range(repetitions):
            case_started = perf_counter()
            analysis = None
            provider_error = None
            try:
                analysis = interpreter.interpret(
                    _context(scenario),
                    scenario["input"],
                    recent_turns=_recent_turns(scenario),
                )
            except Exception as exc:  # noqa: BLE001 - failed model turn remains a scored miss
                provider_error = type(exc).__name__

            failures, _matched, _expected = score_compound_intent_analysis(
                analysis,
                expected=scenario["expected"],
                step_gold=step_gold[scenario["id"]],
                family=scenario["family"],
                ledger=ledger,
                elapsed_seconds=perf_counter() - case_started,
            )
            if provider_error is not None:
                failures = (*failures, f"provider_or_decoder_error:{provider_error}")
            calls += 1
            if failures:
                detail = (
                    f"{scenario['id']} repetition={repetition + 1}: "
                    + "; ".join(failures)
                )
                if scenario["critical"] or scenario_filter:
                    critical_failures.append(detail)
                else:
                    observational_failures.append(detail)

    elapsed = perf_counter() - started
    ledger.emit(record_property, prefix="compound_intent_holdout")
    summary = ledger.summary()
    report_path = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_REPORT_PATH")
    if report_path:
        output = Path(report_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        think_value = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_THINK")
        report = build_compound_intent_report(
            ledger_summary=summary,
            usage_events=usage_events,
            model=provider.model,
            model_digest=provider.get_model_digest(),
            ollama_version=provider.get_server_version(),
            timeout_seconds=provider.timeout,
            think=think_value,
            git_commit=os.getenv("CAMPAIGN_MANAGER_GIT_COMMIT"),
            scenario_filter=scenario_filter,
            scenario_count=len(scenarios),
            provider_calls=calls,
            elapsed_seconds=elapsed,
            critical_failure_count=len(critical_failures),
            observational_failure_count=len(observational_failures),
        )
        output.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )

    record_property("compound_intent_model", provider.model)
    record_property("compound_intent_model_digest", provider.get_model_digest() or "unavailable")
    record_property("compound_intent_ollama_version", provider.get_server_version() or "unavailable")
    record_property("compound_intent_provider_calls", calls)
    record_property("compound_intent_elapsed_seconds", round(elapsed, 3))
    if observational_failures:
        print("Observational compound-intent mismatches:\n" + "\n".join(observational_failures))
    print(ledger.render())
    assert not critical_failures, "\n".join(critical_failures) + "\n" + ledger.render()
