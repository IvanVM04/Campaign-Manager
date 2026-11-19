"""Opt-in A/B comparison: current Intent model vs model plus Stanza hints.

This test is excluded from deterministic CI by the real_llm marker and needs
CAMPAIGN_MANAGER_NLP_PILOT_LIVE=1 as an additional explicit opt-in.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any, cast

import pytest

from services.nlp_pilot.probes import nearest_rank_percentile
from services.nlp_pilot.stanza_adapter import StanzaParserAdapter
from services.turns.intent_interpreter import IntentInterpreter
from tests.intent_analysis_evaluation import (
    load_language_step_count_gold,
    score_intent_analysis,
)
from tests.nlp_pilot_support import ParserHintingProvider
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger
from tests.semantic_evaluation_report import (
    build_live_evaluation_report,
    write_live_evaluation_report,
)
from tests.test_real_llm_semantic_holdout import _make_context, _make_interpreter

pytestmark = [pytest.mark.real_llm, pytest.mark.nlp_pilot]
FIXTURES = Path(__file__).parent / "fixtures"


def _score_variant(
    interpreter: IntentInterpreter,
    scenario: dict,
    expected_step_count: int,
    family: str,
    ledger: SemanticEvaluationLedger,
    usage_events: list[dict],
) -> tuple[bool, str | None]:
    started = perf_counter()
    analysis = None
    error_type: str | None = None
    provider = interpreter.provider
    inner_provider = (
        provider.inner if isinstance(provider, ParserHintingProvider) else provider
    )
    original_callback = getattr(inner_provider, "metrics_callback", None)
    has_metrics_callback = hasattr(inner_provider, "metrics_callback")
    mutable_provider = cast(Any, inner_provider)
    if has_metrics_callback:
        mutable_provider.metrics_callback = usage_events.append
    try:
        try:
            analysis = interpreter.interpret(_make_context(), scenario["input"])
        except Exception as exc:  # noqa: BLE001 - provider errors remain scored misses
            error_type = type(exc).__name__
    finally:
        if has_metrics_callback:
            mutable_provider.metrics_callback = original_callback
    elapsed = perf_counter() - started
    _matched, _total, failures = score_intent_analysis(
        analysis,
        expected=scenario["expected"],
        expected_step_count=expected_step_count,
        family=family,
        ledger=ledger,
        elapsed_seconds=elapsed,
    )
    return not failures, error_type


def test_real_ollama_compares_intent_with_and_without_stanza_hints(record_property):
    """Use identical utterances/gold to compare the unchanged model and hinted model."""
    if os.getenv("CAMPAIGN_MANAGER_NLP_PILOT_LIVE") != "1":
        pytest.skip(
            "set CAMPAIGN_MANAGER_NLP_PILOT_LIVE=1 to opt into the extra Ollama A/B calls"
        )

    corpus = json.loads(
        (FIXTURES / "language_understanding_corpus_holdout_v1.json").read_text(
            encoding="utf-8"
        )
    )
    if corpus.get("split") != "held_out":
        raise ValueError("NLP pilot requires the frozen language holdout corpus")
    step_gold = load_language_step_count_gold(corpus)

    scenario_filter = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID")
    scenarios = corpus["scenarios"]
    if scenario_filter:
        scenarios = [item for item in scenarios if item["id"] == scenario_filter]
        if len(scenarios) != 1:
            raise ValueError(
                "CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID must match one language holdout scenario"
            )

    model_only_usage: list[dict] = []
    hinted_usage: list[dict] = []
    model_only_interpreter = _make_interpreter(model_only_usage)
    base_provider = model_only_interpreter.provider
    hint_provider = ParserHintingProvider(base_provider)
    hinted_interpreter = IntentInterpreter(provider=hint_provider)

    model_dir = os.getenv("CAMPAIGN_MANAGER_NLP_PILOT_MODEL_DIR")
    parser = StanzaParserAdapter(
        model_dir=model_dir,
        language="es",
        model_package="default",
    )
    model_only_ledger = SemanticEvaluationLedger()
    hinted_ledger = SemanticEvaluationLedger()
    parser_errors: Counter[str] = Counter()
    model_only_errors: Counter[str] = Counter()
    hinted_errors: Counter[str] = Counter()
    parser_latencies: list[float] = []
    prompt_hint_bytes: list[int] = []
    parse_successes = 0
    model_only_passes = 0
    hinted_passes = 0
    provider_calls = 0
    started = perf_counter()

    for scenario_index, scenario in enumerate(scenarios):
        try:
            parse_started = perf_counter()
            parsed_document = parser.parse(scenario["input"])
            parser_latencies.append((perf_counter() - parse_started) * 1000)
            parse_successes += 1
        except Exception as exc:  # noqa: BLE001 - record the type only
            parsed_document = None
            parser_errors[type(exc).__name__] += 1

        hint_provider.set_parser_hints(parsed_document)
        repetitions = 3 if scenario["critical"] else 1
        for repetition in range(repetitions):
            variants = (
                ("model_only", model_only_interpreter, model_only_ledger, model_only_usage),
                ("model_plus_stanza_hints", hinted_interpreter, hinted_ledger, hinted_usage),
            )
            # Alternate call order to reduce systematic warm-up/order bias.
            if (scenario_index + repetition) % 2:
                variants = tuple(reversed(variants))
            for variant_name, interpreter, ledger, usage in variants:
                passed, error_type = _score_variant(
                    interpreter,
                    scenario,
                    step_gold[scenario["id"]],
                    scenario["family"],
                    ledger,
                    usage,
                )
                provider_calls += 1
                if variant_name == "model_only":
                    model_only_passes += int(passed)
                    if error_type is not None:
                        model_only_errors[error_type] += 1
                else:
                    hinted_passes += int(passed)
                    if error_type is not None:
                        hinted_errors[error_type] += 1
                if variant_name == "model_plus_stanza_hints":
                    prompt_hint_bytes.append(hint_provider.hint_bytes)

    elapsed = perf_counter() - started
    report = build_live_evaluation_report(
        evaluation_name="intent_model_vs_stanza_hints",
        corpus_name="language_understanding_corpus_holdout_v1.json",
        provider=hint_provider,
        ledger=model_only_ledger,
        scenario_count=len(scenarios),
        provider_calls=provider_calls,
        elapsed_seconds=elapsed,
        usage_events=model_only_usage + hinted_usage,
        scenario_filter=scenario_filter,
    )
    report.pop("metrics", None)
    report["comparison"] = {
        "model_only": {
            "passed_cases": model_only_passes,
            "scored_cases": sum(
                item["cases"]
                for item in model_only_ledger.summary()["families"].values()
            ),
            "provider_error_types": dict(sorted(model_only_errors.items())),
            "metrics": model_only_ledger.summary(),
        },
        "model_plus_stanza_hints": {
            "passed_cases": hinted_passes,
            "scored_cases": sum(
                item["cases"]
                for item in hinted_ledger.summary()["families"].values()
            ),
            "provider_error_types": dict(sorted(hinted_errors.items())),
            "metrics": hinted_ledger.summary(),
        },
    }
    report["parser"] = {
        "adapter": "stanza",
        "library_version": parser.library_version,
        "model_package": parser.model_package,
        "language": parser.language,
        "attempted_parses": len(scenarios),
        "successful_parses": parse_successes,
        "failed_parses": len(scenarios) - parse_successes,
        "parse_error_types": dict(sorted(parser_errors.items())),
        "latency_p50_ms": nearest_rank_percentile(parser_latencies, 0.50),
        "latency_p95_ms": nearest_rank_percentile(parser_latencies, 0.95),
        "prompt_hint_bytes_mean": (
            round(sum(prompt_hint_bytes) / len(prompt_hint_bytes), 1)
            if prompt_hint_bytes else 0
        ),
    }
    report["experiment"] = {
        "baseline": "unchanged Intent prompt and schema",
        "variant": "evaluation-only Stanza hints appended by a provider decorator",
        "production_prompt_changed": False,
        "production_dependency_added": False,
        "held_out_text_persisted": False,
        "raw_parser_output_persisted": False,
        "no_quality_improvement_assumed": True,
        "generation_settings_shared": True,
    }
    report_path = write_live_evaluation_report(
        report,
        path=os.getenv("CAMPAIGN_MANAGER_NLP_PILOT_REPORT_PATH"),
    )
    model_only_ledger.emit(record_property, prefix="nlp_pilot_model_only")
    hinted_ledger.emit(record_property, prefix="nlp_pilot_model_plus_stanza_hints")
    record_property("nlp_pilot_scenario_count", len(scenarios))
    record_property("nlp_pilot_provider_calls", provider_calls)
    record_property("nlp_pilot_model_only_passes", model_only_passes)
    record_property("nlp_pilot_hint_variant_passes", hinted_passes)
    record_property("nlp_pilot_parser_successes", parse_successes)
    record_property("nlp_pilot_elapsed_seconds", round(elapsed, 3))
    record_property("nlp_pilot_report", report_path or "not_configured")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
