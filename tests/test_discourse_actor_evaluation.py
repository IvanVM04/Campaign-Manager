"""Tests for independent discourse actor gold and live report safety."""

import json
from pathlib import Path

from tests.discourse_evaluation import (
    DiscourseControlLedger,
    build_live_discourse_report,
    load_primary_actor_gold,
)
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

FIXTURES = Path(__file__).parent / "fixtures"


def test_primary_actor_gold_covers_every_non_correction_holdout_case_once():
    corpus = json.loads(
        (FIXTURES / "discourse_pipeline_corpus_holdout_v1.json").read_text(
            encoding="utf-8"
        )
    )
    gold = load_primary_actor_gold()
    eligible_ids = {
        item["id"]
        for item in corpus["scenarios"]
        if item["family"] != "multi_turn_correction"
    }

    assert corpus["split"] == "held_out"
    assert set(gold) == eligible_ids
    assert len(gold) == len(eligible_ids)
    assert set(gold.values()) == {"player", "npc"}


def test_primary_actor_ledger_penalizes_wrong_and_missing_actor_predictions():
    ledger = SemanticEvaluationLedger()
    ledger.record_semantic_slots(
        "intent_primary_actor",
        expected_slots=("actor:npc",),
        predicted_slots=("actor:player",),
    )
    ledger.record_semantic_slots(
        "intent_primary_actor",
        expected_slots=("actor:player",),
        predicted_slots=(),
    )

    values = ledger.summary()["semantic_slot_quality"]["intent_primary_actor"]
    assert values["true_positive"] == 0
    assert values["false_positive"] == 1
    assert values["false_negative"] == 2
    assert values["precision"] == 0.0
    assert values["recall"] == 0.0
    assert values["f1"] == 0.0


def test_discourse_control_ledger_reports_exact_accuracy_without_fabricating_empty_scores():
    ledger = DiscourseControlLedger()
    ledger.record("topic_shift", expected=True, observed=True)
    ledger.record("topic_shift", expected=False, observed=True)
    ledger.record("history_scope", expected=(10, 11), observed=(10, 11))

    summary = ledger.summary()
    assert summary["topic_shift"] == {
        "cases": 2,
        "exact_matches": 1,
        "exact_accuracy": 0.5,
    }
    assert summary["history_scope"]["exact_accuracy"] == 1.0
    assert summary["callback"]["exact_accuracy"] is None


def test_live_report_is_reproducible_and_contains_only_allowlisted_diagnostics():
    ledger = SemanticEvaluationLedger()
    ledger.record_semantic_slots(
        "intent_primary_actor",
        expected_slots=("actor:player",),
        predicted_slots=("actor:player",),
    )
    report = build_live_discourse_report(
        ledger_summary=ledger.summary(),
        control_summary=DiscourseControlLedger().summary(),
        prompt_observations={"callback:discourse_retained": 1},
        family_calls={"explicit_callback": 1},
        usage_events=[{
            "provider_role": "intent",
            "prompt_bytes": 4096,
            "eval_count": 120,
            "think": False,
            "prompt": "must not be persisted",
            "completion": "must not be persisted",
        }],
        model="gemma4:12b",
        model_digest="digest",
        ollama_version="0.40.16",
        timeout_seconds=300.0,
        think=False,
        git_commit="abc123",
        scenario_filter=None,
        scenario_count=1,
        provider_calls=1,
        elapsed_seconds=12.3456,
        critical_failure_count=0,
        observational_failure_count=0,
    )

    encoded = json.dumps(report, ensure_ascii=False)
    assert report["schema_version"] == 5
    assert report["metadata"]["git_commit"] == "abc123"
    assert report["metadata"]["model_digest"] == "digest"
    assert report["metadata"]["think"] is False
    assert report["run"]["elapsed_seconds"] == 12.346
    assert report["diagnostics"]["provider_usage_totals"] == {
        "event_count": 1,
        "prompt_bytes_total": 4096,
        "prompt_bytes_max": 4096,
        "prompt_eval_count_total": 0,
        "prompt_eval_count_max": 0,
        "eval_count_total": 120,
        "eval_count_max": 120,
        "load_duration_ms_total": 0,
        "load_duration_ms_max": 0,
        "prompt_eval_duration_ms_total": 0,
        "prompt_eval_duration_ms_max": 0,
        "eval_duration_ms_total": 0,
        "eval_duration_ms_max": 0,
        "total_duration_ms_total": 0,
        "total_duration_ms_max": 0,
        "duration_ms_total": 0,
        "duration_ms_max": 0,
    }
    assert "must not be persisted" not in encoded
    assert "completion" not in encoded
    assert "provider_model" not in encoded
    assert "request_status" not in encoded
    assert "player_input" not in encoded
    assert "source_excerpt" not in encoded
