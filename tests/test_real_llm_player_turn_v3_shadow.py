"""Opt-in live Ollama comparison of the v2 and holistic v3 interpreters.

The v3 result is observational only: it is validated and scored but is never
passed to mechanics, world extraction, persistence or narration.
"""

from __future__ import annotations

import hashlib
import json
import os
from time import perf_counter

import pytest

from tests.player_turn_interpretation_v3_shadow import (
    V3_EVIDENCE_ALIGNMENT_VERSION,
    V3_PROMPT_VERSION,
    V3_RESPONSE_SCHEMA,
    V3_SYSTEM_PROMPT,
    PlayerTurnInterpretationV3ShadowRunner,
)
from tests.player_turn_v3_shadow_evaluation import (
    load_v3_shadow_corpus,
    score_shadow_comparison,
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

pytestmark = pytest.mark.real_llm


def test_real_ollama_player_turn_v3_shadow_holdout(record_property):
    """Record paired v2/v3 results; do not gate rollout on this first baseline."""
    scenarios = load_v3_shadow_corpus()
    scenario_filter = os.getenv(
        "CAMPAIGN_MANAGER_REAL_LLM_V3_SHADOW_SCENARIO_ID"
    )
    if scenario_filter:
        scenarios = [
            item for item in scenarios if item["id"] == scenario_filter
        ]
        if len(scenarios) != 1:
            raise ValueError(
                "CAMPAIGN_MANAGER_REAL_LLM_V3_SHADOW_SCENARIO_ID "
                "must match one held-out scenario"
            )

    interpreter, provider, _context_builder, usage_events = _live_intent_runtime()
    runner = PlayerTurnInterpretationV3ShadowRunner(interpreter)
    ledger = SemanticEvaluationLedger()
    comparisons: list[dict] = []
    started = perf_counter()
    provider_calls = 0
    evidence_spans_realigned: list[int] = []

    for scenario in scenarios:
        comparison = runner.run(
            _context(scenario),
            scenario["input"],
            recent_turns=_recent_turns(scenario),
        )
        comparisons.append(
            score_shadow_comparison(scenario, comparison, ledger)
        )
        evidence_spans_realigned.append(
            comparison.v3_evidence_spans_realigned
        )
        if comparison.v2_prompt_bytes is not None:
            provider_calls += 1
        if comparison.v3_prompt_bytes is not None:
            provider_calls += 1

    elapsed = perf_counter() - started
    ledger.emit(record_property, prefix="player_turn_v3_shadow")
    critical_cases = [item for item in comparisons if item["critical"]]
    critical_v3_valid = sum(
        item["v3_status"] == "valid" for item in critical_cases
    )
    record_property("player_turn_v3_shadow_model", provider.model)
    record_property(
        "player_turn_v3_shadow_model_digest",
        provider.get_model_digest() or "unavailable",
    )
    record_property(
        "player_turn_v3_shadow_ollama_version",
        provider.get_server_version() or "unavailable",
    )
    record_property("player_turn_v3_shadow_scenarios", len(scenarios))
    record_property("player_turn_v3_shadow_provider_calls", provider_calls)
    record_property(
        "player_turn_v3_shadow_evidence_spans_realigned",
        sum(evidence_spans_realigned),
    )
    record_property(
        "player_turn_v3_shadow_critical_v3_valid",
        f"{critical_v3_valid}/{len(critical_cases)}",
    )
    record_property(
        "player_turn_v3_shadow_elapsed_seconds",
        round(elapsed, 3),
    )

    report = build_live_evaluation_report(
        evaluation_name="player-turn-v3-shadow",
        corpus_name="player-turn-v3-shadow-corpus-v1",
        provider=provider,
        ledger=ledger,
        scenario_count=len(scenarios),
        provider_calls=provider_calls,
        elapsed_seconds=elapsed,
        usage_events=usage_events,
        scenario_filter=scenario_filter,
    )
    report["comparisons"] = comparisons
    report["evidence_alignment"] = {
        "algorithm": V3_EVIDENCE_ALIGNMENT_VERSION,
        "realigned_span_count": sum(evidence_spans_realigned),
        "scenarios_with_realignment": sum(
            count > 0 for count in evidence_spans_realigned
        ),
        "scenario_count": len(evidence_spans_realigned),
    }
    report["run_manifest"] = {
        "prompt_version": V3_PROMPT_VERSION,
        "prompt_sha256": hashlib.sha256(
            V3_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "schema_version": 3,
        "schema_sha256": hashlib.sha256(
            json.dumps(
                V3_RESPONSE_SCHEMA,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "evidence_alignment_version": V3_EVIDENCE_ALIGNMENT_VERSION,
        "production_route": "v2",
        "v3_authority": "none",
    }
    report["acceptance"] = {
        "mode": "diagnostic_baseline",
        "production_route": "v2",
        "v3_authority": "none",
        "live_thresholds_enforced": False,
    }
    report_path = os.getenv(
        "CAMPAIGN_MANAGER_REAL_LLM_V3_SHADOW_REPORT_PATH"
    )
    if report_path:
        written = write_live_evaluation_report(report, path=report_path)
        if written is not None:
            record_property("player_turn_v3_shadow_report", written)

    print(ledger.render())
    print(
        "v3 shadow contract validity: "
        f"{sum(item['v3_status'] == 'valid' for item in comparisons)}"
        f"/{len(comparisons)}; "
        f"critical={critical_v3_valid}/{len(critical_cases)}"
    )
