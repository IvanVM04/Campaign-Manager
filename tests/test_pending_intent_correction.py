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


def relation_analysis():
    source = "Mara protege a Bram durante la huida."
    payload = {
        "schema_version": 2,
        "category": "report",
        "steps": [{
            "index": 0,
            "source_excerpt": source,
            "actor": "player",
            "action": "Mara protege a Bram",
            "modality": "reported",
            "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": ["Mara", "Bram"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "protege",
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
            "predicate": "protege",
            "object": {"text": "Bram", "kind_hint": "character"},
            "relation_family": "protection",
            "polarity": "positive",
            "modality": "reported",
            "source_excerpt": source,
            "attributed_to": None,
            "temporal_expression": None,
        }],
    }
    return PlayerIntentAnalysis.from_payload(payload, source_text=source)


def test_compact_intent_payload_decodes_atomic_argument_and_relation_slots():
    action_pending = analysis()
    argument_correction = PendingIntentCorrection.from_intent_payload(
        {
            "step_index": 0,
            "slot": "action_argument:recipient",
            "previous_value": "Mara",
            "replacement": {
                "text": "Aldric",
                "kind_hint": "character",
            },
            "source_excerpt": "No, la destinataria es Aldric.",
        },
        evidence_text="No, la destinataria es Aldric.",
        pending_analysis=action_pending,
    )

    assert argument_correction.argument_role is SemanticArgumentRole.RECIPIENT
    assert argument_correction.relation_claim_index is None
    corrected_action = argument_correction.apply(
        action_pending,
        player_evidence_text="No, la destinataria es Aldric.",
        resolution_pending=True,
        committed=False,
    )
    assert corrected_action.steps[0].action_frame.arguments[1].mention.text == "Aldric"

    relation_pending = relation_analysis()
    relation_correction = PendingIntentCorrection.from_intent_payload(
        {
            "step_index": 0,
            "slot": "relation_object:0",
            "previous_value": "Bram",
            "replacement": {
                "text": "Aldric",
                "kind_hint": "character",
            },
            "source_excerpt": "No, Mara protege a Aldric.",
        },
        evidence_text="No, Mara protege a Aldric.",
        pending_analysis=relation_pending,
    )

    assert relation_correction.argument_role is None
    assert relation_correction.relation_claim_index == 0
    corrected_relation = relation_correction.apply(
        relation_pending,
        player_evidence_text="No, Mara protege a Aldric.",
        resolution_pending=True,
        committed=False,
    )
    assert corrected_relation.relation_claims[0].object.text == "Aldric"


def test_compact_intent_payload_uses_explicit_role_when_mention_repeats():
    pending_payload = analysis().to_dict()
    pending_payload["steps"][0]["action_frame"]["arguments"].append({
        "role": "agent",
        "mention": {
            "text": "Mara",
            "kind_hint": "character",
        },
    })
    pending = PlayerIntentAnalysis.from_payload(
        pending_payload,
        source_text="Entrego la llave de hierro a Mara.",
    )

    correction = PendingIntentCorrection.from_intent_payload(
        {
            "step_index": 0,
            "slot": "action_argument:recipient",
            "previous_value": "Mara",
            "replacement": {
                "text": "Aldric",
                "kind_hint": "character",
            },
            "source_excerpt": "No, la destinataria es Aldric.",
        },
        evidence_text="No, la destinataria es Aldric.",
        pending_analysis=pending,
    )
    updated = correction.apply(
        pending,
        player_evidence_text="No, la destinataria es Aldric.",
        resolution_pending=True,
        committed=False,
    )

    arguments = updated.steps[0].action_frame.arguments
    assert arguments[1].mention.text == "Aldric"
    assert arguments[2].mention.text == "Mara"


def test_compact_intent_payload_rejects_selector_that_does_not_match_pending_slot():
    with pytest.raises(ValueError, match="does not identify exactly one pending role"):
        PendingIntentCorrection.from_intent_payload(
            {
                "step_index": 0,
                "slot": "action_argument:patient",
                "previous_value": "Mara",
                "replacement": {
                    "text": "Aldric",
                    "kind_hint": "character",
                },
                "source_excerpt": "No, la destinataria es Aldric.",
            },
            evidence_text="No, la destinataria es Aldric.",
            pending_analysis=analysis(),
        )

    with pytest.raises(ValueError, match="missing pending claim"):
        PendingIntentCorrection.from_intent_payload(
            {
                "step_index": 0,
                "slot": "relation_object:1",
                "previous_value": "Bram",
                "replacement": {
                    "text": "Aldric",
                    "kind_hint": "character",
                },
                "source_excerpt": "No, Mara protege a Aldric.",
            },
            evidence_text="No, Mara protege a Aldric.",
            pending_analysis=relation_analysis(),
        )


def test_compact_intent_payload_rejects_legacy_selector_fields():
    payload = {
        "step_index": 0,
        "slot": "action_argument:recipient",
        "previous_value": "Mara",
        "replacement": {
            "text": "Aldric",
            "kind_hint": "character",
        },
        "source_excerpt": "No, la destinataria es Aldric.",
        "argument_role": "recipient",
        "relation_claim_index": None,
    }

    with pytest.raises(ValueError, match="missing or unexpected fields"):
        PendingIntentCorrection.from_intent_payload(
            payload,
            evidence_text="No, la destinataria es Aldric.",
            pending_analysis=analysis(),
        )


def test_relation_selector_diagnoses_opposite_endpoint():
    pending = relation_analysis()
    with pytest.raises(
        ValueError,
        match="relation selector points to opposite endpoint",
    ) as captured:
        PendingIntentCorrection.from_intent_payload(
            {
                "step_index": 0,
                "slot": "relation_subject:0",
                "previous_value": "Bram",
                "replacement": {
                    "text": "Aldric",
                    "kind_hint": "character",
                },
                "source_excerpt": "Quise decir que Mara protege a Aldric, no a Bram.",
            },
            evidence_text="Quise decir que Mara protege a Aldric, no a Bram.",
            pending_analysis=pending,
        )

    # Diagnostics classify the mismatch without echoing player/model values.
    assert "Bram" not in str(captured.value)
    assert "Mara" not in str(captured.value)


def test_compact_relation_selector_reports_unmatched_previous_value():
    pending = relation_analysis()
    with pytest.raises(
        ValueError,
        match="relation selector value matches neither pending endpoint",
    ) as captured:
        PendingIntentCorrection.from_intent_payload(
            {
                "step_index": 0,
                "slot": "relation_object:0",
                "previous_value": "Sable",
                "replacement": {
                    "text": "Aldric",
                    "kind_hint": "character",
                },
                "source_excerpt": "Quise decir que Mara protege a Aldric, no a Sable.",
            },
            evidence_text="Quise decir que Mara protege a Aldric, no a Sable.",
            pending_analysis=pending,
        )

    assert "Sable" not in str(captured.value)
    assert "Bram" not in str(captured.value)
