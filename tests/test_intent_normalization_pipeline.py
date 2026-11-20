"""Contract tests for the deterministic player-intent normalization boundary."""

from __future__ import annotations

import pytest

from models.intent_validation_diagnostics import IntentAnalysisValidationError
from services.turns.intent_normalization_pipeline import (
    IntentNormalizationPipeline,
)


def _payload(
    *,
    source: str = "Abro la puerta.",
    category: str = "action",
    modality: str = "attempted",
    actor: str = "player",
    polarity: str = "positive",
    index: int = 0,
    active_step_index: int | None = 0,
    attributed_to: str | None = None,
) -> dict:
    return {
        "schema_version": 2,
        "category": category,
        "steps": [
            {
                "index": index,
                "source_excerpt": source,
                "actor": actor,
                "action": "abrir la puerta",
                "modality": modality,
                "polarity": polarity,
                "reported_outcome": "not_claimed",
                "target_mentions": ["la puerta"] if "puerta" in source else [],
                "attributed_to": attributed_to,
                "action_frame": {
                    "predicate": source.split()[0].strip("¿¡"),
                    "family": "interaction",
                    "arguments": (
                        [
                            {
                                "role": "theme",
                                "mention": {
                                    "text": "la puerta",
                                    "kind_hint": "world_entity",
                                },
                            }
                        ]
                        if "puerta" in source
                        else []
                    ),
                },
            }
        ],
        "active_step_index": active_step_index,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }


def test_pipeline_canonicalizes_redundant_step_indices_without_reordering():
    source = "Abro la puerta."
    payload = _payload(source=source, index=9)

    result = IntentNormalizationPipeline().normalize(
        payload,
        player_input=source,
        evidence_text=source,
    )

    assert result.analysis.steps[0].index == 0
    assert result.analysis.steps[0].source_excerpt == source
    assert result.analysis.active_step_index == 0
    assert result.diagnostics.canonicalized_step_indices == (9,)


def test_pipeline_removes_active_mechanics_pointer_from_non_action_category():
    source = "¿Dónde está Mara?"
    payload = _payload(
        source=source,
        category="question",
        modality="question",
        active_step_index=0,
    )
    payload["steps"][0]["target_mentions"] = []
    payload["steps"][0]["action_frame"]["arguments"] = []

    result = IntentNormalizationPipeline().normalize(
        payload,
        player_input=source,
        evidence_text=source,
    )

    assert result.analysis.category.value == "question"
    assert result.analysis.active_step_index is None
    assert result.analysis.is_actionable is False


def test_pipeline_keeps_invalid_step_indices_for_strict_contract_rejection():
    source = "Abro la puerta."
    payload = _payload(source=source, index=True)

    with pytest.raises(IntentAnalysisValidationError):
        IntentNormalizationPipeline().normalize(
            payload,
            player_input=source,
            evidence_text=source,
        )


def test_pipeline_does_not_accept_evidence_outside_the_current_player_message():
    source = "Abro la puerta."
    payload = _payload(source=source)
    payload["steps"][0]["source_excerpt"] = "Mara abre la puerta."
    payload["steps"][0]["action_frame"]["predicate"] = "Mara"

    with pytest.raises(IntentAnalysisValidationError):
        IntentNormalizationPipeline().normalize(
            payload,
            player_input=source,
            evidence_text=source,
        )


def test_pipeline_rejects_blank_evidence_before_running_normalizers():
    source = "Abro la puerta."

    with pytest.raises(ValueError, match="evidence_text"):
        IntentNormalizationPipeline().normalize(
            _payload(source=source),
            player_input=source,
            evidence_text="   ",
        )


def test_normalization_diagnostics_are_content_free():
    source = "Abro la puerta."
    payload = _payload(source=source, index=6)

    result = IntentNormalizationPipeline().normalize(
        payload,
        player_input=source,
        evidence_text=source,
    )

    diagnostic_text = repr(result.diagnostics)
    assert source not in diagnostic_text
    assert "puerta" not in diagnostic_text
    assert result.diagnostics.canonicalized_step_indices == (6,)


def test_pipeline_removes_explicit_callback_preamble_and_reindexes_action_steps():
    source = (
        "Retomando lo de la pared lisa de piedra, intento escalarla usando "
        "Atletismo. Si alcanzo la cornisa, entro en la torre."
    )
    callback = "Retomando lo de la pared lisa de piedra"
    action = "intento escalarla usando Atletismo"
    conditional = "Si alcanzo la cornisa, entro en la torre."
    payload = {
        "schema_version": 2,
        "category": "mixed",
        "steps": [
            {
                "index": 0,
                "source_excerpt": callback,
                "actor": "player",
                "action": "retomar el tema de la pared",
                "modality": "observed",
                "polarity": "positive",
                "reported_outcome": "success",
                "target_mentions": ["la pared lisa de piedra"],
                "attributed_to": None,
                "action_frame": {
                    "predicate": "Retomando",
                    "family": "other",
                    "arguments": [],
                },
            },
            {
                "index": 1,
                "source_excerpt": action,
                "actor": "player",
                "action": "intentar escalar la pared",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["Atletismo"],
                "attributed_to": None,
                "action_frame": {
                    "predicate": "escalarla",
                    "family": "movement",
                    "arguments": [],
                },
            },
            {
                "index": 2,
                "source_excerpt": conditional,
                "actor": "player",
                "action": "entrar en la torre si alcanza la cornisa",
                "modality": "conditional",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["la cornisa", "la torre"],
                "attributed_to": None,
                "action_frame": {
                    "predicate": "entro",
                    "family": "movement",
                    "arguments": [],
                },
            },
        ],
        "active_step_index": 1,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [{
            "step_index": 0,
            "subject": {"text": "la pared lisa de piedra", "kind_hint": "location"},
            "predicate": "Retomando",
            "object": {"text": "lo", "kind_hint": "world_entity"},
            "relation_family": "other",
            "polarity": "positive",
            "modality": "observed",
            "source_excerpt": callback,
            "attributed_to": None,
            "temporal_expression": None,
        }],
    }

    result = IntentNormalizationPipeline().normalize(
        payload,
        player_input=source,
        evidence_text=source,
    )

    assert len(result.analysis.steps) == 2
    assert result.analysis.steps[0].source_excerpt == (
        "Retomando lo de la pared lisa de piedra, " + action
    )
    assert result.analysis.steps[0].index == 0
    assert result.analysis.steps[1].source_excerpt == conditional
    assert result.analysis.steps[1].index == 1
    assert result.analysis.active_step_index == 0
    assert result.analysis.is_actionable is True
    assert result.analysis.relation_claims == ()
    assert "explicit_callback_preamble_removed" in result.diagnostics.intent_surface_rules


def test_pipeline_classifies_an_unverified_named_quoted_speaker_as_dialogue():
    source = "Mara susurra: «cambiando de tema» y después se ríe."
    payload = _payload(
        source=source,
        category="report",
        actor="npc",
        modality="reported",
        active_step_index=None,
    )
    payload["steps"][0]["action_frame"]["predicate"] = "susurra"
    payload["steps"][0]["action_frame"]["family"] = "interaction"

    result = IntentNormalizationPipeline().normalize(
        payload,
        player_input=source,
        evidence_text=source,
    )

    assert result.analysis.category.value == "dialogue"
    assert result.analysis.active_step_index is None
    assert result.analysis.steps[0].actor.value == "npc"
    assert result.analysis.steps[0].modality.value == "dialogue"
    assert result.analysis.steps[0].attributed_to == "Mara"
    assert result.analysis.steps[0].action_frame.family.value == "communication"
    assert result.diagnostics.unverified_named_speaker_dialogue_normalized is True



def test_pipeline_classifies_named_npc_warning_with_clitic_as_dialogue():
    source = "Aldric me advierte: «No abras la puerta del sótano»."
    payload = _payload(
        source=source,
        category="report",
        actor="npc",
        modality="reported",
        active_step_index=None,
    )
    payload["steps"][0]["action_frame"]["predicate"] = "advierte"
    payload["steps"][0]["action_frame"]["family"] = "interaction"

    result = IntentNormalizationPipeline().normalize(
        payload,
        player_input=source,
        evidence_text=source,
    )

    assert result.analysis.category.value == "dialogue"
    assert result.analysis.active_step_index is None
    assert result.analysis.steps[0].actor.value == "npc"
    assert result.analysis.steps[0].modality.value == "dialogue"
    assert result.analysis.steps[0].attributed_to == "Aldric"
    assert result.analysis.steps[0].action_frame.family.value == "communication"
    assert result.diagnostics.unverified_named_speaker_dialogue_normalized is True


def test_pipeline_keeps_explicit_player_dialogue_before_follow_up_investigation():
    source = "Le pregunto a Mara por la llave y después examino el escritorio."
    payload = {
        "schema_version": 2,
        "category": "action",
        "steps": [
            {
                "index": 0,
                "source_excerpt": "Le pregunto a Mara por la llave",
                "actor": "other",
                "action": "preguntar a Mara por la llave",
                "modality": "reported",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["Mara", "la llave"],
                "attributed_to": None,
                "action_frame": {
                    "predicate": "pregunto",
                    "family": "communication",
                    "arguments": [],
                },
            },
            {
                "index": 1,
                "source_excerpt": "después examino el escritorio",
                "actor": "other",
                "action": "examinar el escritorio",
                "modality": "observed",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["el escritorio"],
                "attributed_to": None,
                "action_frame": {
                    "predicate": "examino",
                    "family": "perception",
                    "arguments": [],
                },
            },
        ],
        "active_step_index": 0,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }

    result = IntentNormalizationPipeline().normalize(
        payload,
        player_input=source,
        evidence_text=source,
    )

    assert result.analysis.category.value == "mixed"
    assert len(result.analysis.steps) == 2
    assert result.analysis.steps[0].actor.value == "player"
    assert result.analysis.steps[0].modality.value == "dialogue"
    assert result.analysis.steps[1].actor.value == "player"
    assert result.analysis.steps[1].modality.value == "attempted"
    assert result.analysis.active_step_index == 1
    assert result.diagnostics.compound_dialogue_action_normalized is True

def test_compound_normalizer_does_not_turn_a_following_npc_reply_into_player_action():
    from services.turns.intent_normalization_pipeline import (
        _normalize_compound_player_dialogue_then_action,
    )

    source = (
        "Le pregunto a Mara por la llave y después el guardia me responde."
    )
    payload = {
        "schema_version": 2,
        "category": "mixed",
        "steps": [
            {"index": 0, "source_excerpt": "Le pregunto a Mara por la llave"},
            {"index": 1, "source_excerpt": "el guardia me responde"},
        ],
        "relation_claims": [],
    }

    assert (
        _normalize_compound_player_dialogue_then_action(payload, source)
        is None
    )
