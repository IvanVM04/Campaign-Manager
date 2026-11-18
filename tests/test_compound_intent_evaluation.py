"""Contract tests for compound-message corpus, scoring and report privacy."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from services.turns import IntentInterpreter
from tests.compound_intent_evaluation import (
    build_compound_intent_report,
    load_compound_intent_corpus,
    score_compound_intent_analysis,
)
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

FIXTURES = Path(__file__).parent / "fixtures"
EXISTING_HELD_OUT = (
    "language_understanding_corpus_holdout_v1.json",
    "semantic_frame_corpus_holdout_v1.json",
    "conversation_understanding_corpus_holdout_v1.json",
    "discourse_pipeline_corpus_holdout_v1.json",
)


def test_compound_corpus_and_per_step_gold_are_complete_and_text_separated():
    scenarios, gold = load_compound_intent_corpus()

    assert len(scenarios) == 14
    assert len(gold) == len(scenarios)
    assert sum(item["critical"] for item in scenarios) == 9
    for scenario in scenarios:
        labels = gold[scenario["id"]]
        assert len(labels) == scenario["expected"]["step_count"]
        assert set(labels[0]) == {"actor", "modality", "polarity"}


def test_compound_corpus_does_not_duplicate_existing_held_out_inputs():
    scenarios, _gold = load_compound_intent_corpus()
    existing_inputs: set[str] = set()
    for filename in EXISTING_HELD_OUT:
        payload = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
        for scenario in payload["scenarios"]:
            utterance = scenario.get("input") or scenario.get("utterance")
            if isinstance(utterance, str):
                existing_inputs.add(" ".join(utterance.casefold().split()))

    observed = [" ".join(item["input"].casefold().split()) for item in scenarios]
    assert len(observed) == len(set(observed))
    assert not set(observed) & existing_inputs


def test_compound_gold_sidecar_contains_no_player_text_or_entity_identity():
    _scenarios, gold = load_compound_intent_corpus()
    sidecar = json.loads(
        (FIXTURES / "compound_intent_step_gold_v1.json").read_text(encoding="utf-8")
    )
    assert set(sidecar) == {"schema_version", "split", "description", "scenarios"}
    assert all(set(entry) == {"id", "steps"} for entry in sidecar["scenarios"])
    assert all(
        set(step) == {"actor", "modality", "polarity"}
        for entry in sidecar["scenarios"]
        for step in entry["steps"]
    )
    assert set(gold) == {entry["id"] for entry in sidecar["scenarios"]}


def test_compound_examples_are_not_embedded_in_intent_prompt():
    scenarios, _gold = load_compound_intent_corpus()
    prompt = IntentInterpreter.SYSTEM_PROMPT
    assert all(item["input"] not in prompt for item in scenarios)


def test_compound_evaluator_scores_all_steps_and_counts_missing_and_extra_steps():
    scenarios, gold = load_compound_intent_corpus()
    scenario = scenarios[0]
    labels = gold[scenario["id"]]
    fake = SimpleNamespace(
        category=SimpleNamespace(value="mixed"),
        active_step_index=1,
        steps=(
            SimpleNamespace(
                actor=SimpleNamespace(value="player"),
                modality=SimpleNamespace(value="completed"),
                polarity=SimpleNamespace(value="positive"),
            ),
            SimpleNamespace(
                actor=SimpleNamespace(value="player"),
                modality=SimpleNamespace(value="attempted"),
                polarity=SimpleNamespace(value="positive"),
            ),
        ),
    )
    ledger = SemanticEvaluationLedger()
    failures, matched, expected = score_compound_intent_analysis(
        fake,
        expected=scenario["expected"],
        step_gold=labels,
        family=scenario["family"],
        ledger=ledger,
    )
    assert failures == ()
    assert matched == expected

    missing = SimpleNamespace(
        category=fake.category,
        active_step_index=1,
        steps=fake.steps[:1],
    )
    missing_failures, _matched, _expected = score_compound_intent_analysis(
        missing,
        expected=scenario["expected"],
        step_gold=labels,
        family=scenario["family"],
        ledger=ledger,
    )
    assert "intent.step_1_actor_missing" in missing_failures
    assert "intent.step_1_modality_missing" in missing_failures
    assert "intent.step_1_polarity_missing" in missing_failures


def test_compound_report_persists_aggregate_numbers_only():
    ledger = SemanticEvaluationLedger()
    ledger.record_semantic_slots(
        "compound_step_actor:sample",
        expected_slots=("step:0:actor:player",),
        predicted_slots=("step:0:actor:player",),
    )
    ledger.record_secret_visibility(
        "the hidden token is ABC123",
        ("ABC123",),
    )
    report = build_compound_intent_report(
        ledger_summary=ledger.summary(),
        usage_events=[{
            "prompt": "PLAYER PRIVATE TEXT",
            "completion": "SECRET COMPLETION",
            "provider_model": "untrusted provider supplied text",
            "prompt_eval_count": 42,
            "eval_count": 21,
        }],
        model="gemma4:26b",
        model_digest="digest",
        ollama_version="0.40.16",
        timeout_seconds=120,
        think=False,
        git_commit="a" * 40,
        scenario_filter=None,
        scenario_count=14,
        provider_calls=14,
        elapsed_seconds=12.5,
        critical_failure_count=0,
        observational_failure_count=0,
    )
    serialized = json.dumps(report, sort_keys=True)

    assert report["schema_version"] == 1
    assert "secret_leaks" not in report["metrics"]
    assert "PLAYER PRIVATE TEXT" not in serialized
    assert "SECRET COMPLETION" not in serialized
    assert "untrusted provider supplied text" not in serialized
    assert report["provider_usage_totals"]["prompt_eval_count_total"] == 42
