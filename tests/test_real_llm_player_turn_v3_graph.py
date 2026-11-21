"""Opt-in Ollama v3 graph holdout; diagnostic only, never production authority."""

from __future__ import annotations

import os
from time import perf_counter

import pytest

from tests.player_turn_interpretation_v3_shadow import (
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

pytestmark = pytest.mark.real_llm


def test_real_ollama_player_turn_v3_graph_holdout(record_property):
    """Run the expanded graph corpus only when explicitly enabled."""
    if os.getenv("CAMPAIGN_MANAGER_REAL_LLM_V3_GRAPH_ENABLE") != "1":
        pytest.skip(
            "set CAMPAIGN_MANAGER_REAL_LLM_V3_GRAPH_ENABLE=1 to run graph holdout"
        )

    scenarios = load_v3_graph_corpus()
    scenario_filter = os.getenv(
        "CAMPAIGN_MANAGER_REAL_LLM_V3_GRAPH_SCENARIO_ID"
    )
    if scenario_filter:
        scenarios = [item for item in scenarios if item["id"] == scenario_filter]
        if len(scenarios) != 1:
            raise ValueError(
                "CAMPAIGN_MANAGER_REAL_LLM_V3_GRAPH_SCENARIO_ID "
                "must match one graph holdout scenario"
            )

    interpreter, provider, _context_builder, usage_events = _live_intent_runtime()
    runner = PlayerTurnInterpretationV3ShadowRunner(interpreter)
    ledger = SemanticEvaluationLedger()
    comparisons: list[dict] = []
    started = perf_counter()
    provider_calls = 0

    for scenario in scenarios:
        comparison = runner.run(
            _context(scenario),
            scenario["input"],
            recent_turns=_recent_turns(scenario),
        )
        comparisons.append(
            score_v3_graph_scenario(
                scenario,
                comparison.v3_interpretation,
                ledger,
                interpretation_status=comparison.v3_status,
            )
        )
        provider_calls += int(comparison.v2_prompt_bytes is not None)
        provider_calls += int(comparison.v3_prompt_bytes is not None)

    elapsed = perf_counter() - started
    ledger.emit(record_property, prefix="player_turn_v3_graph")
    exact_critical = sum(
        item["graph_exact_match"]
        for item in comparisons
        if item["critical"]
    )
    critical_count = sum(item["critical"] for item in comparisons)
    record_property("player_turn_v3_graph_model", provider.model)
    record_property(
        "player_turn_v3_graph_model_digest",
        provider.get_model_digest() or "unavailable",
    )
    record_property(
        "player_turn_v3_graph_ollama_version",
        provider.get_server_version() or "unavailable",
    )
    record_property("player_turn_v3_graph_scenarios", len(scenarios))
    record_property("player_turn_v3_graph_provider_calls", provider_calls)
    record_property(
        "player_turn_v3_graph_critical_exact",
        f"{exact_critical}/{critical_count}",
    )
    record_property("player_turn_v3_graph_elapsed_seconds", round(elapsed, 3))

    report = build_live_evaluation_report(
        evaluation_name="player-turn-v3-graph-holdout",
        corpus_name="player-turn-v3-graph-corpus-v1",
        provider=provider,
        ledger=ledger,
        scenario_count=len(scenarios),
        provider_calls=provider_calls,
        elapsed_seconds=elapsed,
        usage_events=usage_events,
        scenario_filter=scenario_filter,
    )
    report["graph_comparisons"] = comparisons
    report["acceptance"] = {
        "mode": "diagnostic_baseline",
        "production_route": "v2",
        "v3_authority": "none",
        "live_thresholds_enforced": False,
        "graph_exact_threshold_approved": False,
    }
    report_path = os.getenv(
        "CAMPAIGN_MANAGER_REAL_LLM_V3_GRAPH_REPORT_PATH"
    )
    if report_path:
        written = write_live_evaluation_report(report, path=report_path)
        if written is not None:
            record_property("player_turn_v3_graph_report", written)

    print(ledger.render())
    print(
        "v3 graph exact scenarios: "
        f"{sum(item['graph_exact_match'] for item in comparisons)}"
        f"/{len(comparisons)}; critical={exact_critical}/{critical_count}"
    )
