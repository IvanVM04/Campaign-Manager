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
    assert result.diagnostics.non_action_category == "question"
    assert result.diagnostics.discarded_active_step_index == 0


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
