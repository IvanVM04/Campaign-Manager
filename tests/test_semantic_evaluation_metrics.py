"""Tests for semantic slot precision and recall, including unsupported output."""

import pytest

from tests.semantic_evaluation_metrics import SemanticEvaluationLedger


def test_semantic_slot_metrics_penalize_extra_arguments_and_relations():
    ledger = SemanticEvaluationLedger()
    ledger.record_semantic_slots(
        "action_roles",
        expected_slots=("argument:theme|llave|item_instance", "argument:recipient|mara|character"),
        predicted_slots=(
            "argument:theme|llave|item_instance",
            "argument:recipient|mara|character",
            "argument:agent|aldric|character",
        ),
    )

    result = ledger.summary()
    quality = result["semantic_slot_quality"]["action_roles"]
    assert quality["true_positive"] == 2
    assert quality["false_positive"] == 1
    assert quality["false_negative"] == 0
    assert quality["precision"] == 0.6667
    assert quality["recall"] == 1.0
    assert quality["f1"] == pytest.approx(0.8)
    assert result["semantic_slot_precision"] == 0.6667


def test_semantic_slot_metrics_account_for_duplicate_slots():
    ledger = SemanticEvaluationLedger()
    ledger.record_semantic_slots(
        "relations",
        expected_slots=("relation:mara|aliada|gremio",),
        predicted_slots=(
            "relation:mara|aliada|gremio",
            "relation:mara|aliada|gremio",
        ),
    )
    values = ledger.summary()["semantic_slot_quality"]["relations"]
    assert values["true_positive"] == 1
    assert values["false_positive"] == 1
    assert values["precision"] == 0.5
    assert values["recall"] == 1.0


def test_semantic_slot_metrics_reject_empty_family_and_signatures():
    ledger = SemanticEvaluationLedger()
    with pytest.raises(ValueError, match="family"):
        ledger.record_semantic_slots(
            " ",
            expected_slots=(),
            predicted_slots=(),
        )
    with pytest.raises(ValueError, match="non-empty"):
        ledger.record_semantic_slots(
            "intent",
            expected_slots=("",),
            predicted_slots=(),
        )


def test_semantic_slot_metrics_score_zero_f1_when_all_expected_slots_are_missing():
    ledger = SemanticEvaluationLedger()
    ledger.record_semantic_slots(
        "missed_action_predicate",
        expected_slots=("action:Camino",),
        predicted_slots=(),
    )

    values = ledger.summary()["semantic_slot_quality"]["missed_action_predicate"]
    assert values["true_positive"] == 0
    assert values["false_positive"] == 0
    assert values["false_negative"] == 1
    assert values["precision"] is None
    assert values["recall"] == 0.0
    assert values["f1"] == 0.0


def test_semantic_slot_metrics_report_unmeasured_families_without_inventing_scores():
    ledger = SemanticEvaluationLedger()
    ledger.record_semantic_slots(
        "negative_control",
        expected_slots=(),
        predicted_slots=("unsupported:relationship",),
    )
    values = ledger.summary()["semantic_slot_quality"]["negative_control"]
    assert values["precision"] == 0.0
    assert values["recall"] is None
    assert values["f1"] is None


def test_entity_group_resolution_scores_each_member_without_collapsing_group():
    ledger = SemanticEvaluationLedger()
    ledger.record_entity_group_resolution(
        expected_entity_ids=(11, 12),
        observed_entity_ids=(11, 12, 13),
    )

    result = ledger.summary()
    assert result["entity_link_precision"] == 0.6667
    assert result["entity_link_recall"] == 1.0


def test_entity_group_resolution_rejects_invalid_expected_and_observed_ids():
    ledger = SemanticEvaluationLedger()
    with pytest.raises(ValueError, match="expected entity group"):
        ledger.record_entity_group_resolution(
            expected_entity_ids=(11,),
            observed_entity_ids=(),
        )
    with pytest.raises(ValueError, match="positive integers"):
        ledger.record_entity_group_resolution(
            expected_entity_ids=(11, 12),
            observed_entity_ids=(True,),
        )
    with pytest.raises(ValueError, match="positive integers"):
        ledger.record_entity_group_resolution(
            expected_entity_ids=(True, 12),
            observed_entity_ids=(),
        )

