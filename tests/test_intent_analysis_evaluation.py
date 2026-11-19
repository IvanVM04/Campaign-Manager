"""Offline contract tests for complete ordered intent evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from services.turns import IntentInterpreter
from tests.intent_analysis_evaluation import (
    load_language_step_count_gold,
    score_intent_analysis,
)
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

FIXTURES = Path(__file__).parent / "fixtures"


def _step(**fields):
    defaults = {
        "actor": "player",
        "modality": "attempted",
        "polarity": "positive",
        "reported_outcome": "not_claimed",
        "attributed_to": None,
    }
    defaults.update(fields)
    return SimpleNamespace(**defaults)


def _analysis(*, steps, active_step_index=1):
    return SimpleNamespace(
        category="mixed",
        active_step_index=active_step_index,
        requires_clarification=False,
        steps=tuple(steps),
    )


def _two_step_gold():
    return {
        "category": "mixed",
        "active_step_index": 1,
        "requires_clarification": False,
        "first_step": {
            "actor": "npc",
            "modality": "reported",
            "polarity": "positive",
            "attributed_to": "Mara",
        },
        "step": {
            "actor": "player",
            "modality": "attempted",
            "polarity": "positive",
        },
    }


def test_exact_ordered_intent_steps_score_all_gold_fields():
    ledger = SemanticEvaluationLedger()
    analysis = _analysis(
        steps=(
            _step(
                actor="npc",
                modality="reported",
                attributed_to="Mara",
            ),
            _step(),
        )
    )

    matched, expected, failures = score_intent_analysis(
        analysis,
        expected=_two_step_gold(),
        expected_step_count=2,
        family="reported_npc_then_action",
        ledger=ledger,
        elapsed_seconds=0.25,
    )

    assert failures == ()
    assert matched == expected
    summary = ledger.summary()
    assert summary["families"]["intent:reported_npc_then_action"]["case_accuracy"] == 1.0
    assert summary["semantic_slot_quality"][
        "intent_step_presence:reported_npc_then_action"
    ] == {
        "true_positive": 2,
        "false_positive": 0,
        "false_negative": 0,
        "gold_slots": 2,
        "predicted_slots": 2,
        "matched_slots": 2,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }


def test_extra_step_is_a_false_positive_and_fails_exact_case_accuracy():
    ledger = SemanticEvaluationLedger()
    analysis = _analysis(steps=(_step(actor="npc", modality="reported", attributed_to="Mara"), _step(), _step()))

    _matched, _expected, failures = score_intent_analysis(
        analysis,
        expected=_two_step_gold(),
        expected_step_count=2,
        family="reported_npc_then_action",
        ledger=ledger,
    )

    assert any(item.startswith("step_count:") for item in failures)
    presence = ledger.summary()["semantic_slot_quality"][
        "intent_step_presence:reported_npc_then_action"
    ]
    assert presence["true_positive"] == 2
    assert presence["false_positive"] == 1
    assert presence["false_negative"] == 0
    count = ledger.summary()["semantic_slot_quality"][
        "intent_step_count:reported_npc_then_action"
    ]
    assert count["false_positive"] == 1
    assert count["false_negative"] == 1
    assert ledger.summary()["families"]["intent:reported_npc_then_action"]["case_accuracy"] == 0.0


def test_missing_step_is_a_false_negative_for_presence_and_its_gold_slots():
    ledger = SemanticEvaluationLedger()
    analysis = _analysis(steps=(_step(actor="npc", modality="reported", attributed_to="Mara"),))

    _matched, _expected, failures = score_intent_analysis(
        analysis,
        expected=_two_step_gold(),
        expected_step_count=2,
        family="reported_npc_then_action",
        ledger=ledger,
    )

    assert any(item.startswith("step_count:") for item in failures)
    presence = ledger.summary()["semantic_slot_quality"][
        "intent_step_presence:reported_npc_then_action"
    ]
    assert presence["false_negative"] == 1
    actor = ledger.summary()["semantic_slot_quality"][
        "intent_step_actor:reported_npc_then_action"
    ]
    assert actor["false_negative"] == 1


def test_step_gold_uses_expected_active_index_not_model_selected_index():
    ledger = SemanticEvaluationLedger()
    analysis = _analysis(
        steps=(
            _step(actor="npc", modality="reported", attributed_to="Mara"),
            _step(),
        ),
        active_step_index=0,
    )

    matched, expected, failures = score_intent_analysis(
        analysis,
        expected=_two_step_gold(),
        expected_step_count=2,
        family="reported_npc_then_action",
        ledger=ledger,
    )

    assert len(failures) == 1
    assert failures[0].startswith("active_step_index:")
    assert matched == expected - 1
    assert ledger.summary()["semantic_slot_quality"][
        "intent_step_actor:reported_npc_then_action"
    ]["f1"] == 1.0


def test_missing_analysis_is_scored_as_misses_not_skipped():
    ledger = SemanticEvaluationLedger()
    expected = {
        "category": "action",
        "active_step_index": 0,
        "requires_clarification": False,
        "step": {
            "actor": "player",
            "modality": "attempted",
            "polarity": "positive",
            "reported_outcome": "not_claimed",
        },
    }

    matched, total, failures = score_intent_analysis(
        None,
        expected=expected,
        expected_step_count=1,
        family="provider_failure",
        ledger=ledger,
    )

    assert matched == 0
    assert total == 8
    assert len(failures) == total
    assert ledger.summary()["families"]["intent:provider_failure"]["failed_cases"] == 1
    assert ledger.summary()["semantic_slot_quality"][
        "intent_step_actor:provider_failure"
    ]["false_negative"] == 1


def test_language_step_count_sidecar_covers_holdout_without_copying_text():
    corpus = json.loads(
        (FIXTURES / "language_understanding_corpus_holdout_v1.json").read_text(
            encoding="utf-8"
        )
    )
    path = FIXTURES / "language_understanding_step_count_gold_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    gold = load_language_step_count_gold(corpus, path=path)

    assert payload["split"] == "held_out_annotations"
    assert payload["source_corpus"] == "language_understanding_corpus_holdout_v1.json"
    assert len(gold) == len(corpus["scenarios"]) == 35
    assert all(set(entry) == {"id", "step_count"} for entry in payload["scenarios"])
    assert all(1 <= count <= 8 for count in gold.values())
    for scenario in corpus["scenarios"]:
        expected = scenario["expected"]
        expected_count = 2 if "first_step" in expected or "later_step" in expected else 1
        assert gold[scenario["id"]] == expected_count

    prompt = IntentInterpreter.SYSTEM_PROMPT
    assert all(scenario["input"] not in prompt for scenario in corpus["scenarios"])
