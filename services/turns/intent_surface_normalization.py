"""High-confidence, evidence-local normalization of common Spanish utterance patterns.

These rules repair only explicit surface constructions. They never invent entity
IDs, canonical names, permissions, action predicates or world consequences.
The model remains responsible for open-ended interpretation.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class IntentSurfaceNormalizationSummary:
    """Content-free rule identifiers for diagnostics and evaluation."""

    applied_rules: tuple[str, ...] = ()


_CONDITIONAL_FUTURE_RE = re.compile(
    r"^\s*(?:si|siempre\s+que|en\s+caso\s+de\s+que)\b"
    r"[\s\S]{1,180}?[,:;]\s*[\s\S]{0,100}?"
    r"\b[\wáéíóúüñ]+(?:ré|rás|rá|remos|réis|rán)\b",
    re.IGNORECASE,
)
_ATTEMPT_RE = re.compile(
    r"\b(?:intent\w*|prueb\w*|prob\w*|trat\w*\s+de|procur\w*)\b",
    re.IGNORECASE,
)
_FAILURE_RE = re.compile(
    r"\b(?:resbal\w*|no\s+alcanz\w*|no\s+gira|no\s+giró|"
    r"sigue\s+(?:cerrad\w*|bloquead\w*)|no\s+(?:lo|la|les|me)\s+"
    r"(?:consig\w*|logr\w*)|fracasa|fracasó|caigo|caí)\b",
    re.IGNORECASE,
)
_EXPLICIT_CORRECTION_RE = re.compile(
    r"^\s*(?:rectifico\b|me\s+he\s+equivocado(?:\s+de\s+\w+)?\s*:"
    r"|no\s+era\b[\s\S]{1,180}?\bsino\b"
    r"|no\s+me\s+refería\b[\s\S]{1,180}?\bsino\b"
    r"|quería\s+decir\b|quise\s+decir\b)",
    re.IGNORECASE,
)
_EPISTEMIC_UNCERTAINTY_RE = re.compile(
    r"\b(?:sospech\w*|sospechos\w*|no\s+tengo\s+pruebas|no\s+hay\s+pruebas|"
    r"no\s+dispongo\s+de\s+(?:pruebas|evidencias)|"
    r"no\s+sabe\s+si|no\s+sabes\s+si|no\s+sabemos\s+si|ignora\s+si|"
    r"no\s+estoy\s+segur\w*|no\s+estamos\s+segur\w*|"
    r"quizá|quizas|tal\s+vez|puede\s+que|es\s+posible\s+que|"
    r"al\s+parecer|rumor)\b",
    re.IGNORECASE,
)
_DIRECT_QUESTION_RE = re.compile(r"^\s*¿")
_PLAYER_DIALOGUE_PREFIX_RE = re.compile(
    r"^\s*(?:le\s+)?(?:digo|dije|pregunto|pregunté|cuento|conté|"
    r"respondo|respondí|contesto|contesté|aviso|avisé|susurro|susurré)"
    r"\s+(?:a|al)\b",
    re.IGNORECASE,
)
_PERCEPTION_PREDICATE_RE = re.compile(
    r"\b(?:examino|examinar|inspecciono|inspeccioné|inspeccionar|"
    r"observo|observé|observar|miro|miré|mirar|veo|vi|ver|"
    r"escucho|escuché|detecto|detecté|detectar)\b",
    re.IGNORECASE,
)
_FOLLOW_UP_ATTEMPT_RE = re.compile(
    r"\b(?:después|despues|luego|a\s+continuación)\s+"
    r"(?:intento|trato\s+de|pruebo|procuro)\b",
    re.IGNORECASE,
)
_REPORTED_SPEAKER_RE = re.compile(
    r"^\s*(?P<speaker>"
    r"(?:(?:un|una|el|la)\s+[\wáéíóúüñ-]+(?:\s+[\wáéíóúüñ-]+){0,2})"
    r"|(?-i:[A-ZÁÉÍÓÚÜÑ][\wáéíóúüñ-]*"
    r"(?:\s+[A-ZÁÉÍÓÚÜÑ][\wáéíóúüñ-]*)?)"
    r")\s+(?:me\s+)?(?:cuenta|cuentan|contó|contaron|dice|dijo|dicen|"
    r"afirman|afirma|afirmó|asegura|aseguró|relata|relató|comenta|comentó)"
    r"\s+que\b",
    re.IGNORECASE,
)


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _widen_excerpt(step: dict[str, Any], evidence: str) -> None:
    """Use the whole short utterance when it supplies omitted local context."""
    excerpt = evidence.strip()
    if excerpt and len(excerpt) <= 300:
        step["source_excerpt"] = excerpt


def normalize_intent_surface_payload(
    intent_payload: Any,
    *,
    evidence_text: str,
) -> tuple[Any, IntentSurfaceNormalizationSummary]:
    """Repair only high-confidence, literal constructions before domain validation.

    Patterns that imply splitting, entity resolution, or inferred outcomes
    without explicit lexical evidence are left to the model and validator.
    """
    if (
        not isinstance(intent_payload, dict)
        or intent_payload.get("schema_version") != 2
        or not isinstance(evidence_text, str)
        or not evidence_text.strip()
    ):
        return intent_payload, IntentSurfaceNormalizationSummary()

    raw_steps = intent_payload.get("steps")
    if (
        not isinstance(raw_steps, list)
        or not raw_steps
        or len(raw_steps) > 8
        or any(not isinstance(step, dict) for step in raw_steps)
    ):
        return intent_payload, IntentSurfaceNormalizationSummary()

    # Surface rules must never hide a malformed active-step pointer.
    # Preserve invalid values so PlayerIntentAnalysis remains the authority
    # that rejects them instead of silently turning them into null.
    active_step_index = intent_payload.get("active_step_index")
    if active_step_index is not None and (
        isinstance(active_step_index, bool)
        or not isinstance(active_step_index, int)
        or not 0 <= active_step_index < len(raw_steps)
    ):
        return intent_payload, IntentSurfaceNormalizationSummary()

    evidence = evidence_text.strip()
    normalized = dict(intent_payload)
    steps = [dict(step) for step in raw_steps]
    rules: list[str] = []

    # A direct interrogative addressed to the DM is a question, not a player
    # action. Fictional speech is handled separately by its explicit speaker.
    if (
        len(steps) == 1
        and _DIRECT_QUESTION_RE.search(evidence)
        and normalized.get("category") not in {"dialogue", "correction"}
    ):
        steps[0]["modality"] = "question"
        normalized["category"] = "question"
        normalized["active_step_index"] = None
        _widen_excerpt(steps[0], evidence)
        rules.append("explicit_direct_question")

    # A first-person speech verb with an explicit in-fiction recipient is
    # dialogue by the player, even when quoted content is imperative/question.
    if len(steps) == 1 and _PLAYER_DIALOGUE_PREFIX_RE.search(evidence):
        steps[0]["actor"] = "player"
        steps[0]["modality"] = "dialogue"
        normalized["category"] = "dialogue"
        normalized["active_step_index"] = None
        _widen_excerpt(steps[0], evidence)
        rules.append("explicit_player_dialogue")

    # Preserve an observed/perceptual first step before a later explicit
    # attempt. Only rewrite two already-separated steps with a literal
    # perception predicate and a clear sequence marker.
    if (
        len(steps) == 2
        and _PERCEPTION_PREDICATE_RE.search(steps[0].get("source_excerpt", ""))
        and _FOLLOW_UP_ATTEMPT_RE.search(evidence)
        and _ATTEMPT_RE.search(steps[1].get("source_excerpt", ""))
        and not normalized.get("relation_claims")
    ):
        steps[0]["actor"] = "player"
        steps[0]["modality"] = "observed"
        steps[0]["reported_outcome"] = "not_claimed"
        steps[1]["actor"] = "player"
        steps[1]["modality"] = "attempted"
        steps[1]["polarity"] = "positive"
        steps[1]["reported_outcome"] = "not_claimed"
        normalized["category"] = "mixed"
        normalized["active_step_index"] = 1
        rules.append("explicit_observation_before_attempt")

    # A conditional future is a plan, not an active attempt. Restrict this to
    # one-step utterances so a mixed action/plan sequence remains model-led.
    if (
        len(steps) == 1
        and _CONDITIONAL_FUTURE_RE.search(evidence)
        and normalized.get("category") not in {"question", "dialogue", "correction"}
    ):
        step = steps[0]
        step["modality"] = "conditional"
        step["reported_outcome"] = "not_claimed"
        _widen_excerpt(step, evidence)
        normalized["category"] = "plan"
        normalized["active_step_index"] = None
        rules.append("explicit_conditional_future")

    # A failed result clause following an explicit attempt resolves that
    # attempt. Collapse a two-step split only when step two is clearly the
    # lexical failure clause and there are no relation claims to re-index.
    if (
        _ATTEMPT_RE.search(evidence)
        and re.search(r"\bpero\b", evidence, re.IGNORECASE)
        and _FAILURE_RE.search(evidence)
        and normalized.get("category") not in {"question", "dialogue", "correction"}
    ):
        first = steps[0]
        first_is_player_attempt = (
            first.get("actor") == "player"
            and first.get("modality") in {"attempted", "completed", "reported", "observed"}
        )
        failure_is_second_step = (
            len(steps) == 2
            and first_is_player_attempt
            and isinstance(steps[1].get("source_excerpt"), str)
            and _FAILURE_RE.search(steps[1]["source_excerpt"]) is not None
            and not normalized.get("relation_claims")
        )
        if first_is_player_attempt and (len(steps) == 1 or failure_is_second_step):
            first["modality"] = "completed"
            first["polarity"] = "positive"
            first["reported_outcome"] = "failure"
            _widen_excerpt(first, evidence)
            steps = [first]
            normalized["category"] = "action"
            normalized["active_step_index"] = None
            rules.append("explicit_attempt_failure_outcome")

    # Explicit correction language is not a new attempt or an ordinary report.
    if len(steps) == 1 and _EXPLICIT_CORRECTION_RE.search(evidence):
        step = steps[0]
        step["modality"] = "correction"
        step["reported_outcome"] = "not_claimed"
        _widen_excerpt(step, evidence)
        normalized["category"] = "correction"
        normalized["active_step_index"] = None
        rules.append("explicit_surface_correction")

    # Attribute a report only when speaker and reporting predicate are a
    # literal prefix of current player-authored evidence.
    speaker_match = _REPORTED_SPEAKER_RE.search(evidence)
    if len(steps) == 1 and speaker_match is not None:
        step = steps[0]
        speaker = speaker_match.group("speaker").strip()
        indefinite = _fold(speaker).startswith(("un ", "una "))
        step["actor"] = "other" if indefinite else "npc"
        step["modality"] = "reported"
        step["attributed_to"] = speaker
        _widen_excerpt(step, evidence)
        normalized["category"] = "report"
        normalized["active_step_index"] = None
        rules.append("explicit_reported_speaker")

    # Epistemic markers express uncertainty, not positive world knowledge.
    if len(steps) == 1 and _EPISTEMIC_UNCERTAINTY_RE.search(evidence):
        step = steps[0]
        step["polarity"] = "uncertain"
        if normalized.get("category") not in {"question", "dialogue", "correction"}:
            normalized["category"] = "report"
            normalized["active_step_index"] = None
            if speaker_match is None:
                step["modality"] = "reported"
        _widen_excerpt(step, evidence)
        rules.append("explicit_epistemic_uncertainty")

    normalized["steps"] = steps
    return normalized, IntentSurfaceNormalizationSummary(tuple(dict.fromkeys(rules)))
