"""Validation tests for evidence-bound corrections to pending intent only."""

import pytest

from models.pending_intent_correction import (
    PendingCorrectionSlot,
    PendingIntentCorrection,
)
from models.player_intent_analysis import PlayerIntentAnalysis
from models.semantic_frames import (
    SemanticArgumentRole,
    SemanticMention,
    SemanticObjectKind,
 )


def analysis():
    source = "Entrego la llave de hierro a Mara."
    payload = {
        "schema_version": 2,
        "category": "action",
        "steps": [{
            "index": 0,
            "source_excerpt": source,
            "actor": "player",
            "action": "entregar la llave a Mara",
            "modality": "attempted",
            "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": ["la llave de hierro", "Mara"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "Entrego",
                "family": "transfer",
                "arguments": [
                    {
                        "role": "theme",
                        "mention": {
                            "text": "la llave de hierro",
                            "kind_hint": "item_instance",
                        },
                    },
                    {
                        "role": "recipient",
                        "mention": {"text": "Mara", "kind_hint": "character"},
                    },
                ],
            },
        }],
        "active_step_index": 0,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }
    return PlayerIntentAnalysis.from_payload(payload, source_text=source)


def replacement(name: str) -> SemanticMention:
    return SemanticMention(name, SemanticObjectKind.CHARACTER)


def test_target_correction_changes_only_the_selected_pending_step():
    original = analysis()
    correction = PendingIntentCorrection(
        step_index=0,
        slot=PendingCorrectionSlot.TARGET_MENTION,
        previous_value="Mara",
        replacement=replacement("Aldric"),
        source_excerpt="No, quería decir Aldric.",
    )
    updated = correction.apply(
        original,
        player_evidence_text="Entrego la llave de hierro a Mara. No, quería decir Aldric.",
        resolution_pending=True,
        committed=False,
    )
    assert updated.steps[0].target_mentions == ("la llave de hierro", "Aldric")
    assert original.steps[0].target_mentions[-1] == "Mara"
    frame = updated.steps[0].action_frame
    assert frame is not None
    assert frame.arguments[1].mention.text == "Aldric"
    assert "Aldric" in updated.steps[0].source_excerpt
    assert "Aldric" in updated.steps[0].action
    restored = PlayerIntentAnalysis.from_payload(
        updated.to_dict(),
        source_text="Entrego la llave de hierro a Mara.",
        evidence_text="Entrego la llave de hierro a Mara. No, quería decir Aldric.",
    )
    assert restored == updated


def test_argument_correction_updates_role_and_keeps_other_arguments():
    original = analysis()
    correction = PendingIntentCorrection(
        step_index=0,
        slot=PendingCorrectionSlot.ACTION_ARGUMENT,
        previous_value="Mara",
        replacement=replacement("Aldric"),
        source_excerpt="No, la destinataria es Aldric.",
        argument_role=SemanticArgumentRole.RECIPIENT,
    )
    updated = correction.apply(
        original,
        player_evidence_text=(
            "Entrego la llave de hierro a Mara. No, la destinataria es Aldric."
        ),
        resolution_pending=True,
        committed=False,
    )
    frame = updated.steps[0].action_frame
    assert frame is not None
    args = frame.arguments
    assert args[0].mention.text == "la llave de hierro"
    assert args[1].role is SemanticArgumentRole.RECIPIENT
    assert args[1].mention.text == "Aldric"
    assert updated.steps[0].target_mentions[-1] == "Aldric"
    assert "Aldric" in updated.steps[0].source_excerpt
    restored = PlayerIntentAnalysis.from_payload(
        updated.to_dict(),
        source_text="Entrego la llave de hierro a Mara.",
        evidence_text=(
            "Entrego la llave de hierro a Mara. "
            "No, la destinataria es Aldric."
        ),
    )
    assert restored == updated


def test_correction_is_rejected_after_commit_or_outside_pending_resolution():
    correction = PendingIntentCorrection(
        step_index=0,
        slot=PendingCorrectionSlot.TARGET_MENTION,
        previous_value="Mara",
        replacement=replacement("Aldric"),
        source_excerpt="No, quería decir Aldric.",
    )
    for pending, committed in ((False, False), (True, True)):
        with pytest.raises(ValueError, match="uncommitted pending"):
            correction.apply(
                analysis(),
                player_evidence_text="Entrego la llave de hierro a Mara. No, quería decir Aldric.",
                resolution_pending=pending,
                committed=committed,
            )


def test_correction_rejects_unmentioned_replacement_and_wrong_previous_slot():
    source = "Entrego la llave de hierro a Mara. No, quería decir Aldric."
    correction = PendingIntentCorrection(
        step_index=0,
        slot=PendingCorrectionSlot.ACTION_ARGUMENT,
        previous_value="Mara",
        replacement=replacement("Bram"),
        source_excerpt="No, quería decir Aldric.",
        argument_role=SemanticArgumentRole.RECIPIENT,
    )
    with pytest.raises(ValueError, match="not grounded"):
        correction.apply(
            analysis(),
            player_evidence_text=source,
            resolution_pending=True,
            committed=False,
        )

    wrong_slot_evidence = (
        "Entrego la llave de hierro a Mara. No, quería decir Aldric y Bram."
    )
    wrong_slot = PendingIntentCorrection(
        step_index=0,
        slot=PendingCorrectionSlot.ACTION_ARGUMENT,
        previous_value="Aldric",
        replacement=replacement("Bram"),
        source_excerpt="No, quería decir Aldric y Bram.",
        argument_role=SemanticArgumentRole.RECIPIENT,
    )
    with pytest.raises(ValueError, match="exactly one"):
        wrong_slot.apply(
            analysis(),
            player_evidence_text=wrong_slot_evidence,
            resolution_pending=True,
            committed=False,
        )


def test_correction_rejects_stale_step_and_ungrounded_excerpt():
    correction = PendingIntentCorrection(
        step_index=4,
        slot=PendingCorrectionSlot.TARGET_MENTION,
        previous_value="Mara",
        replacement=replacement("Aldric"),
        source_excerpt="No, quería decir Aldric.",
    )
    with pytest.raises(ValueError, match="missing intent step"):
        correction.apply(
            analysis(),
            player_evidence_text="Entrego la llave de hierro a Mara. No, quería decir Aldric.",
            resolution_pending=True,
            committed=False,
        )

def test_relation_endpoint_correction_updates_only_the_selected_claim():
    source = "Mara es dueña de la llave."
    payload = {
        "schema_version": 2,
        "category": "report",
        "steps": [{
            "index": 0,
            "source_excerpt": source,
            "actor": "player",
            "action": "afirmar propiedad",
            "modality": "observed",
            "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": ["Mara", "la llave"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "es",
                "family": "other",
                "arguments": [],
            },
        }],
        "active_step_index": None,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [{
            "step_index": 0,
            "subject": {"text": "Mara", "kind_hint": "character"},
            "predicate": "dueña",
            "object": {"text": "la llave", "kind_hint": "item_instance"},
            "relation_family": "ownership",
            "polarity": "positive",
            "modality": "observed",
            "source_excerpt": source,
            "attributed_to": None,
            "temporal_expression": None,
        }],
    }
    original = PlayerIntentAnalysis.from_payload(payload, source_text=source)
    correction = PendingIntentCorrection(
        step_index=0,
        slot=PendingCorrectionSlot.RELATION_SUBJECT,
        previous_value="Mara",
        replacement=replacement("Aldric"),
        source_excerpt="No, Aldric es el dueño de la llave.",
        relation_claim_index=0,
    )
    updated = correction.apply(
        original,
        player_evidence_text=source + " No, Aldric es el dueño de la llave.",
        resolution_pending=True,
        committed=False,
    )
    assert updated.relation_claims[0].subject.text == "Aldric"
    assert updated.relation_claims[0].object.text == "la llave"
    assert "Aldric" in updated.steps[0].target_mentions
    assert "Aldric" in updated.steps[0].source_excerpt
    assert "Aldric" in updated.relation_claims[0].source_excerpt
    assert original.relation_claims[0].subject.text == "Mara"
    restored = PlayerIntentAnalysis.from_payload(
        updated.to_dict(),
        source_text=source,
        evidence_text=source + " No, Aldric es el dueño de la llave.",
    )
    assert restored == updated
