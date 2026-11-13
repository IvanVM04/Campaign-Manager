"""Validation tests for evidence-bound corrections to pending intent only."""

import pytest

from models.pending_intent_correction import (
    PendingCorrectionSlot,
    PendingIntentCorrection,
)
from models.player_intent_analysis import PlayerIntentAnalysis
from models.semantic_frames import SemanticArgumentRole, SemanticObjectKind, SemanticMention


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
    assert updated.steps[0].action_frame == original.steps[0].action_frame


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
    args = updated.steps[0].action_frame.arguments
    assert args[0].mention.text == "la llave de hierro"
    assert args[1].role is SemanticArgumentRole.RECIPIENT
    assert args[1].mention.text == "Aldric"
    assert updated.steps[0].target_mentions[-1] == "Aldric"


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
            player_evidence_text=source,
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
