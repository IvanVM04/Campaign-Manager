"""Deterministic normalization boundary for untrusted player-intent payloads.

This module converts the provider's raw intent object into the one shared,
evidence-bound PlayerIntentAnalysis contract. It deliberately does not call an
LLM, resolve canonical entity IDs, authorize mechanics, or write campaign
state. Its output is a validated semantic interpretation plus content-free
diagnostics for the orchestration layer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any

from models.player_intent_analysis import (
    MAX_STEPS,
    IntentActor,
    IntentModality,
    IntentPolarity,
    PlayerIntentAnalysis,
    PlayerReportedOutcome,
    UtteranceCategory,
)
from models.semantic_frames import SemanticActionFamily
from services.discourse.speech_predicates import SPEECH_PREDICATE_ALTERNATION
from services.discourse_context import DiscourseContextBuilder

from .intent_surface_normalization import normalize_intent_surface_payload
from .semantic_surface_hints import (
    SurfaceNormalizationSummary,
    normalize_semantic_surface,
    normalize_untrusted_intent_payload,
)

_NON_ACTION_CATEGORIES = frozenset({
    "question",
    "dialogue",
    "report",
    "plan",
    "correction",
    "unknown",
})


def _normalize_step_indices(
    intent_payload: Any,
) -> tuple[dict[str, Any], tuple[int, ...]] | None:
    """Canonicalize integer step indexes to the ordered array positions.

    The JSON array is the authoritative sequence. Each step's index is only
    its zero-based position in that array; model-supplied integer indexes are
    redundant metadata and may be safely canonicalized. Malformed step
    objects and non-integer indexes are left to the strict domain validator.
    """
    if not isinstance(intent_payload, dict):
        return None
    steps = intent_payload.get("steps")
    if (
        not isinstance(steps, list)
        or not steps
        or len(steps) > MAX_STEPS
    ):
        return None

    reported_indices: list[int] = []
    normalized_steps: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            return None
        index = step.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            return None
        reported_indices.append(index)
        normalized_steps.append(dict(step))

    expected_indices = tuple(range(len(steps)))
    if tuple(reported_indices) == expected_indices:
        return None

    for position, step in enumerate(normalized_steps):
        step["index"] = position

    normalized = dict(intent_payload)
    normalized["steps"] = normalized_steps
    return normalized, tuple(reported_indices)


def _normalize_non_action_active_step(
    intent_payload: Any,
) -> tuple[dict[str, Any], str, int] | None:
    """Clear a valid active-step pointer when the utterance category forbids one.

    This is a conservative provider-boundary normalization: it removes
    mechanical authorization but never changes the category, step content,
    evidence, modality or outcome. Invalid indices and unknown categories are
    left untouched for the domain validator to reject.
    """
    if not isinstance(intent_payload, dict):
        return None
    category = intent_payload.get("category")
    active_step_index = intent_payload.get("active_step_index")
    steps = intent_payload.get("steps")
    if (
        not isinstance(category, str)
        or category not in _NON_ACTION_CATEGORIES
        or isinstance(active_step_index, bool)
        or not isinstance(active_step_index, int)
        or not isinstance(steps, list)
        or not 0 <= active_step_index < len(steps)
    ):
        return None

    normalized = dict(intent_payload)
    normalized["active_step_index"] = None
    return normalized, category, active_step_index


_PLAYER_DIALOGUE_PREFIX_RE = re.compile(
    r"^\s*(?:le\s+)?(?:digo|dije|pregunto|pregunté|cuento|conté|"
    r"respondo|respondí|contesto|contesté|aviso|avisé|susurro|susurré)"
    r"\s+(?:a|al)\b",
    re.IGNORECASE,
)
_FOLLOW_UP_PLAYER_ACTION_RE = re.compile(
    r"\b(?:y\s+)?(?:después|despues|luego|a\s+continuación)\s+"
    r"(?:intento|trato\s+de|pruebo|procuro|examino|examiné|"
    r"inspecciono|inspeccioné|observo|observé|miro|miré|"
    r"entro|salgo|abro|cierro|recojo|tomo|cruzo|subo|bajo)\b",
    re.IGNORECASE,
)
_UNVERIFIED_NAMED_SPEAKER_RE = re.compile(
    r"^\s*(?P<speaker>[A-ZÁÉÍÓÚÜÑ][\wáéíóúüñ-]*"
    r"(?:\s+[A-ZÁÉÍÓÚÜÑ][\wáéíóúüñ-]*)?)\s+"
    r"(?:(?:me|te|le|les|nos)\s+)?(?P<predicate>"
    + SPEECH_PREDICATE_ALTERNATION
    + r")\s*[:,]\s*"
    r"[«“\u201c\"].+?[»”\u201d\"]",
)


def _normalize_compound_player_dialogue_then_action(
    intent_payload: Any,
    evidence_text: str,
) -> tuple[dict[str, Any], bool] | None:
    """Keep an explicit player-to-NPC utterance before a later player action.

    This is a narrow two-step repair: both excerpts must be literal and ordered,
    the first clause must be explicit in-fiction speech, and the second must
    follow a written sequence marker plus an explicit player action verb.
    """
    if not isinstance(intent_payload, dict) or not isinstance(evidence_text, str):
        return None
    raw_steps = intent_payload.get("steps")
    if (
        not isinstance(raw_steps, list)
        or len(raw_steps) != 2
        or any(not isinstance(step, dict) for step in raw_steps)
        or intent_payload.get("relation_claims")
    ):
        return None
    first, second = (dict(step) for step in raw_steps)
    first_excerpt = first.get("source_excerpt")
    second_excerpt = second.get("source_excerpt")
    if (
        not isinstance(first_excerpt, str)
        or not isinstance(second_excerpt, str)
        or not first_excerpt.strip()
        or not second_excerpt.strip()
    ):
        return None

    def fold(value: str) -> str:
        return unicodedata.normalize("NFKC", value).casefold()

    folded_evidence = fold(evidence_text)
    first_folded = fold(first_excerpt)
    second_folded = fold(second_excerpt)
    first_start = folded_evidence.find(first_folded)
    if first_start < 0 or first_start > 2:
        return None
    first_end = first_start + len(first_folded)
    second_start = folded_evidence.find(second_folded, first_end)
    if second_start < first_end:
        return None
    if not _PLAYER_DIALOGUE_PREFIX_RE.match(first_excerpt):
        return None
    sequence_and_second_step = (
        evidence_text[first_end:second_start] + " " + second_excerpt
    )
    if not _FOLLOW_UP_PLAYER_ACTION_RE.search(sequence_and_second_step):
        return None
    if not re.search(
        r"\b(?:intento|trato\s+de|pruebo|procuro|examino|examiné|"
        r"inspecciono|inspeccioné|observo|observé|miro|miré|"
        r"entro|salgo|abro|cierro|recojo|tomo|cruzo|subo|bajo)\b",
        second_excerpt,
        re.IGNORECASE,
    ):
        return None
    if not all(
        fold(excerpt) in folded_evidence
        for excerpt in (first_excerpt, second_excerpt)
    ):
        return None

    first.update({
        "index": 0,
        "actor": "player",
        "modality": "dialogue",
        "polarity": "positive",
        "reported_outcome": "not_claimed",
    })
    second.update({
        "index": 1,
        "actor": "player",
        "modality": "attempted",
        "polarity": "positive",
        "reported_outcome": "not_claimed",
    })
    normalized = dict(intent_payload)
    normalized["steps"] = [first, second]
    normalized["category"] = "mixed"
    normalized["active_step_index"] = 1
    return normalized, True


def _normalize_unverified_named_speaker_dialogue(
    analysis: PlayerIntentAnalysis,
    evidence_text: str,
) -> PlayerIntentAnalysis | None:
    """Classify a literal named quoted speaker without asserting canonical identity.

    Names in player prose are not looked up or promoted to known NPC IDs. A
    unique syntactic speech construction is sufficient to keep the utterance
    as dialogue and to prevent quoted commands from becoming player intent.
    """
    if (
        not isinstance(evidence_text, str)
        or len(evidence_text) > 300
        or len(analysis.steps) > 2
        or analysis.category in {UtteranceCategory.QUESTION, UtteranceCategory.CORRECTION}
    ):
        return None
    match = _UNVERIFIED_NAMED_SPEAKER_RE.match(evidence_text.strip())
    if match is None:
        return None
    steps = list(analysis.steps)
    if not steps or not all(
        step.source_excerpt.strip()
        and fold_text(step.source_excerpt) in fold_text(evidence_text)
        for step in steps
    ):
        return None
    first = replace(
        steps[0],
        source_excerpt=evidence_text.strip(),
        actor=IntentActor.NPC,
        modality=IntentModality.DIALOGUE,
        polarity=IntentPolarity.POSITIVE,
        reported_outcome=PlayerReportedOutcome.NOT_CLAIMED,
        attributed_to=match.group("speaker").strip(),
    )
    steps[0] = first
    return replace(
        analysis,
        category=UtteranceCategory.DIALOGUE,
        steps=tuple(steps),
        active_step_index=None,
    )


def fold_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _normalize_ungrounded_step_attributions(
    intent_payload: Any,
    evidence_text: str,
) -> tuple[dict[str, Any], tuple[int, ...]] | None:
    """Clear step attributions not literally grounded in current player evidence.

    History and discourse context may help interpret a reference, but they are
    not words written by the player. An unsupported attribution is removed
    rather than allowed to invalidate an otherwise usable interpretation or
    authorize a non-player world proposal. Malformed values remain strict.
    """
    if not isinstance(intent_payload, dict) or not isinstance(evidence_text, str):
        return None
    steps = intent_payload.get("steps")
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        return None
    if any(not isinstance(step, dict) for step in steps):
        return None

    def normalize(value: str) -> str:
        return unicodedata.normalize("NFKC", value).casefold()

    normalized_evidence = normalize(evidence_text)
    schema_version = intent_payload.get("schema_version")
    normalized_steps = [dict(step) for step in steps]
    cleared_indices: list[int] = []

    for index, step in enumerate(steps):
        attribution = step.get("attributed_to")
        if (
            attribution is None
            or not isinstance(attribution, str)
            or not attribution.strip()
        ):
            continue

        normalized_attribution = normalize(attribution)
        grounded = normalized_attribution in normalized_evidence
        if schema_version == 2:
            excerpt = step.get("source_excerpt")
            if not isinstance(excerpt, str):
                continue
            grounded = grounded and normalized_attribution in normalize(excerpt)

        if not grounded:
            normalized_steps[index]["attributed_to"] = None
            cleared_indices.append(index)

    if not cleared_indices:
        return None

    normalized = dict(intent_payload)
    normalized["steps"] = normalized_steps
    return normalized, tuple(cleared_indices)


def _normalize_explicit_npc_speech_report(
    analysis: PlayerIntentAnalysis,
) -> PlayerIntentAnalysis | None:
    """Correct only a positive NPC speech event misclassified as a generic report.

    It requires one NPC step and a literal, unquoted third-person subject
    directly attached to a known speech predicate. Evidence, mentions, identity
    and authorization are left untouched.
    """
    if (
        analysis.category is not UtteranceCategory.REPORT
        or len(analysis.steps) != 1
        or analysis.active_step_index is not None
    ):
        return None
    step = analysis.steps[0]
    if (
        step.actor is not IntentActor.NPC
        or step.modality not in {IntentModality.OBSERVED, IntentModality.REPORTED}
        or step.polarity is not IntentPolarity.POSITIVE
        or not DiscourseContextBuilder.speech_predicate_signals(step.source_excerpt)
    ):
        return None
    action_frame = step.action_frame
    if (
        action_frame is not None
        and action_frame.family is not SemanticActionFamily.COMMUNICATION
    ):
        action_frame = replace(
            action_frame,
            family=SemanticActionFamily.COMMUNICATION,
        )
    corrected_step = replace(
        step,
        modality=IntentModality.DIALOGUE,
        action_frame=action_frame,
    )
    return replace(
        analysis,
        category=UtteranceCategory.DIALOGUE,
        steps=(corrected_step,),
        active_step_index=None,
    )


@dataclass(frozen=True, slots=True)
class IntentNormalizationDiagnostics:
    """Content-free results from each deterministic normalization stage."""

    canonicalized_step_indices: tuple[int, ...] = ()
    surface_sanitization: SurfaceNormalizationSummary = field(
        default_factory=SurfaceNormalizationSummary
    )
    intent_surface_rules: tuple[str, ...] = ()
    cleared_attribution_indices: tuple[int, ...] = ()
    non_action_category: str | None = None
    discarded_active_step_index: int | None = None
    explicit_npc_speech_normalized: bool = False
    npc_speech_signal_count: int = 0
    compound_dialogue_action_normalized: bool = False
    unverified_named_speaker_dialogue_normalized: bool = False
    semantic_action_rules: tuple[str, ...] = ()
    semantic_relation_rules: tuple[str, ...] = ()
    dropped_action_shadow_relation_claims: int = 0


@dataclass(frozen=True, slots=True)
class IntentNormalizationResult:
    """A validated interpretation and safe normalization diagnostics."""

    analysis: PlayerIntentAnalysis
    diagnostics: IntentNormalizationDiagnostics


class IntentNormalizationPipeline:
    """Run the ordered, deterministic trust-boundary stages for one intent.

    The order is part of the contract:
    1. Canonicalize redundant step positions without reordering steps.
    2. Remove only ungrounded optional surface fields.
    3. Apply explicit, evidence-local utterance normalization.
    4. Clear ungrounded speaker attribution.
    5. Remove a mechanically actionable pointer from non-action categories.
    6. Strictly decode the versioned PlayerIntentAnalysis contract.
    7. Normalize one narrowly recognized NPC speech-act construction.
    8. Add typed semantic surface hints without creating canonical identity.

    Any malformed or unsupported value not explicitly covered by a
    conservative normalization is left for the strict model decoder to reject.
    """

    def normalize(
        self,
        intent_payload: Any,
        *,
        player_input: str,
        evidence_text: str,
    ) -> IntentNormalizationResult:
        if not isinstance(player_input, str) or not player_input.strip():
            raise ValueError("player_input must be a non-empty string")
        if not isinstance(evidence_text, str) or not evidence_text.strip():
            raise ValueError("evidence_text must be a non-empty string")

        canonicalized_indices: tuple[int, ...] = ()
        step_normalization = _normalize_step_indices(intent_payload)
        if step_normalization is not None:
            intent_payload, canonicalized_indices = step_normalization

        intent_payload, surface_sanitization = normalize_untrusted_intent_payload(
            intent_payload,
            player_input=player_input,
            evidence_text=evidence_text,
        )
        intent_payload, intent_surface_summary = normalize_intent_surface_payload(
            intent_payload,
            evidence_text=evidence_text,
        )

        compound_dialogue_action_normalized = False
        compound_normalization = _normalize_compound_player_dialogue_then_action(
            intent_payload,
            evidence_text,
        )
        if compound_normalization is not None:
            intent_payload, compound_dialogue_action_normalized = compound_normalization

        cleared_attribution_indices: tuple[int, ...] = ()
        attribution_normalization = _normalize_ungrounded_step_attributions(
            intent_payload,
            evidence_text,
        )
        if attribution_normalization is not None:
            intent_payload, cleared_attribution_indices = attribution_normalization

        non_action_category: str | None = None
        discarded_active_step_index: int | None = None
        active_step_normalization = _normalize_non_action_active_step(intent_payload)
        if active_step_normalization is not None:
            (
                intent_payload,
                non_action_category,
                discarded_active_step_index,
            ) = active_step_normalization

        analysis = PlayerIntentAnalysis.from_payload(
            intent_payload,
            source_text=player_input,
            evidence_text=evidence_text,
        )

        speech_normalization = _normalize_explicit_npc_speech_report(analysis)
        speech_signal_count = 0
        if speech_normalization is not None:
            speech_signal_count = len(
                DiscourseContextBuilder.speech_predicate_signals(
                    analysis.steps[0].source_excerpt
                )
            )
            analysis = speech_normalization

        named_speaker_normalization = _normalize_unverified_named_speaker_dialogue(
            analysis,
            evidence_text,
        )
        if named_speaker_normalization is not None:
            analysis = named_speaker_normalization

        analysis, semantic_surface_summary = normalize_semantic_surface(analysis)

        diagnostics = IntentNormalizationDiagnostics(
            canonicalized_step_indices=canonicalized_indices,
            surface_sanitization=surface_sanitization,
            intent_surface_rules=intent_surface_summary.applied_rules,
            cleared_attribution_indices=cleared_attribution_indices,
            non_action_category=non_action_category,
            discarded_active_step_index=discarded_active_step_index,
            explicit_npc_speech_normalized=speech_normalization is not None,
            npc_speech_signal_count=speech_signal_count,
            compound_dialogue_action_normalized=compound_dialogue_action_normalized,
            unverified_named_speaker_dialogue_normalized=(
                named_speaker_normalization is not None
            ),
            semantic_action_rules=semantic_surface_summary.action_rules_applied,
            semantic_relation_rules=semantic_surface_summary.relation_rules_applied,
            dropped_action_shadow_relation_claims=(
                semantic_surface_summary.dropped_action_shadow_relation_claims
            ),
        )
        return IntentNormalizationResult(analysis=analysis, diagnostics=diagnostics)
