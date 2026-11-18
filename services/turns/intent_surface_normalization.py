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
    r"\b(?:resbal\w*|no\s+alcanz\w*|no\s+logr\w*|"
    r"no\s+pued\w*\s+(?:abrir|entrar|cruzar|subir|bajar|alcanzar)|"
    r"me\s+resulta\s+imposible|no\s+gira|no\s+giró|"
    r"sigue\s+(?:cerrad\w*|bloquead\w*)|no\s+(?:lo|la|les|me)\s+"
    r"(?:consig\w*|logr\w*)|no\s+consig\w*|no\s+funcion\w*|"
    r"no\s+se\s+(?:abre|desbloquea|enciende)|fracasa|fracasó|caigo|caí)\b",
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
    r"no\s+sabe\s+si|no\s+sabes\s+si|no\s+sabemos\s+si|"
    r"no\s+recuerda\s+si|no\s+está\s+claro\s+si|"
    r"no\s+queda\s+claro\s+si|no\s+se\s+sabe\s+si|"
    r"nadie\s+sabe\s+si|no\s+sé\s+si|no\s+se\s+si|"
    r"ignora\s+si|desconoce\s+si|duda\s+(?:de\s+que|si)|"
    r"no\s+estoy\s+segur\w*|no\s+estamos\s+segur\w*|"
    r"no\s+está\s+segur\w*|no\s+están\s+segur\w*|"
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
_SEQUENCE_LINKER_RE = re.compile(
    r"\b(?:y\s+)?(?:después|despues|luego|a\s+continuación)\b",
    re.IGNORECASE,
)
_PLAYER_OBSERVATION_RE = re.compile(
    r"^\s*(?:(?:yo)\s+)?(?:observo|observé|veo|vi|miro|miré|examino|"
    r"examiné|inspecciono|inspeccioné|escucho|escuché|oigo|oí|"
    r"detecto|detecté|noto|noté|percibo|percibí|distingo|distinguí)\b",
    re.IGNORECASE,
)
_FIRST_PERSON_PRESENT_RE = re.compile(
    r"^\s*(?:(?:yo)\s+)?(?:(?:me|lo|la|le|les|nos)\s+)?"
    r"(?:abro|cierro|desbloqueo|recojo|tomo|cojo|guardo|saco|coloco|"
    r"entrego|recibo|enciendo|apago|rompo|muevo|levanto|agarro|cruzo|"
    r"activo|desato|sujeto|trep\w*|escalo|camino|corro|entro|salgo|"
    r"subo|bajo|salto|nado|viajo|me\s+acerco|me\s+dirijo|me\s+muevo)\b",
    re.IGNORECASE,
)
_FIRST_PERSON_ACTIVE_CLAUSE_RE = re.compile(
    r"^\s*(?:(?:y|pero|entonces|después|despues|luego)\s+)?"
    r"(?:(?:yo)\s+)?(?:intento|trato\s+de|pruebo|procuro)\b",
    re.IGNORECASE,
)
_INDEPENDENT_PLAYER_ACTION_AFTER_REPORT_RE = re.compile(
    r"\b(?:(?:y\s+)?(?:después|despues|luego|a\s+continuación)|"
    r"(?:y|pero|entonces))\s+(?:(?:yo)\s+)?"
    r"(?:intento|trato\s+de|pruebo|procuro|decido|he\s+decidido|"
    r"prefiero|opto\s+por|no\s+quiero|no\s+voy\s+a|me\s+niego\s+a|"
    r"me\s+abstengo\s+de|abro|cierro|desbloqueo|recojo|tomo|cojo|"
    r"guardo|saco|coloco|entrego|recibo|enciendo|apago|rompo|muevo|"
    r"levanto|agarro|cruzo|activo|desato|sujeto|me\s+acerco|"
    r"me\s+dirijo|me\s+muevo)\b",
    re.IGNORECASE,
)
_FIRST_PERSON_FUTURE_RE = re.compile(
    r"\b[\wáéíóúüñ]+(?:ré|remos)\b",
    re.IGNORECASE,
)
_NEGATED_ATTEMPT_RE = re.compile(
    r"\b(?:no\s+(?:(?:quiero|quisiera|pienso|pretendo|voy\s+a)\s+)?"
    r"(?:(?:lo|la|les|me)\s+)?(?:intent\w*|prueb\w*|prob\w*|procur\w*)|"
    r"(?:decid\w*|quiero|quisiera|pienso|pretendo)\s+no\s+intent\w*|"
    r"me\s+niego\s+a\s+intent\w*)\b",
    re.IGNORECASE,
)
_ATTEMPT_NEGATES_ACTION_RE = re.compile(
    r"\b(?:intent\w*|prueb\w*|prob\w*|procur\w*|trat\w*\s+de)"
    r"\s+no\s+[\wáéíóúüñ]+\b",
    re.IGNORECASE,
)
_EXPLICIT_SUCCESS_RE = re.compile(
    r"\b(?:lo\s+consig\w*|consig\w*\s+(?:abrir|abrirlo|"
    r"desbloquear|desbloquearlo|encender|encenderla|salir|escapar)|"
    r"logr\w*\s+\w+|se\s+(?:abre|desbloquea|enciende)|"
    r"queda\s+(?:abiert\w*|desbloquead\w*|encendid\w*)|"
    r"funciona|con\s+éxito|exitosamente)\b",
    re.IGNORECASE,
)
_CORRECTION_PREDICATE_RE = re.compile(
    r"\b(?:no\s+(?P<era>era)|no\s+me\s+(?P<referia>refería)|"
    r"(?P<queria>quería\s+decir)|(?P<quise>quise\s+decir)|"
    r"(?P<rectifico>rectifico))\b",
    re.IGNORECASE,
)
_REPORTED_SPEAKER_RE = re.compile(
    r"^\s*(?P<speaker>"
    r"(?:(?:un|una|el|la|mi|mis|nuestro|nuestra|nuestros|nuestras)\s+"
    r"[\wáéíóúüñ-]+(?:\s+[\wáéíóúüñ-]+){0,2})"
    r"|(?-i:[A-ZÁÉÍÓÚÜÑ][\wáéíóúüñ-]*"
    r"(?:\s+[A-ZÁÉÍÓÚÜÑ][\wáéíóúüñ-]*)?)"
    r")\s+(?:me\s+)?(?:cuenta|cuentan|contó|contaron|dice|dijo|dicen|"
    r"afirman|afirma|afirmó|asegura|aseguró|asevera|aseveró|relata|relató|"
    r"comenta|comentó|explica|explicó|advierte|advirtió|indica|indicó|"
    r"revela|reveló|informa|informó|sostiene|sostuvo|confirma|confirmó)"
    r"\s+que\b",
    re.IGNORECASE,
)
_EXPLICIT_DECISION_NOT_TO_ACT_RE = re.compile(
    r"(?:^\s*|[.;]\s*|\b(?:y|pero|entonces|después|despues|luego)\s+)"
    r"(?:(?:(?:yo\s+)?(?:decid(?:o|í|imos)|he\s+decidido|"
    r"hemos\s+decidido|prefiero|preferiría|opto\s+por)\s+no)|"
    r"(?:no\s+(?:quiero|voy\s+a|pienso|pretendo))|"
    r"(?:me\s+niego\s+a|me\s+abstengo\s+de|desisto\s+de|"
    r"renuncio\s+a)|"
    r"(?:cancelo\s+(?:el|mi)\s+intento\s+de|"
    r"abandono\s+la\s+idea\s+de))"
    r"\s+(?P<verb>[\wáéíóúüñ]+?(?:ar|er|ir))\b",
    re.IGNORECASE,
)
_ABSTENTION_STATE_RE = re.compile(
    r"\b(?:y\s+)?(?:permanezco|me\s+quedo|me\s+mantengo|sigo)\s+"
    r"(?:fuera|afuera|al\s+exterior|en\s+el\s+exterior|"
    r"al\s+otro\s+lado|en\s+esta\s+orilla)\b[.,;]?",
    re.IGNORECASE,
)
_ATTEMPT_OUTCOME_UNCERTAINTY_RE = re.compile(
    r"\b(?:no\s+(?:sé|se|estoy\s+segur[oa]|tengo\s+claro)|"
    r"ignoro|desconozco)\s+"
    r"(?:si\s+(?:(?:lo|la)\s+)?(?:consig\w*|logr\w*|"
    r"pued\w*|podr\w*|lleg\w*\s+a)|"
    r"(?:de\s+)?(?:poder\s+)?(?:conseguirlo|lograrlo|abrirlo))"
    r"\b",
    re.IGNORECASE,
)
_IMPLICIT_ATTEMPT_FAILURE_RE = re.compile(
    r"\b(?:no\s+(?:consig\w*|logr\w*|pued\w*)\s+"
    r"(?:abrir|entrar|cruzar|subir|bajar|alcanzar|forzar|activar|"
    r"desbloquear)|me\s+resulta\s+imposible\s+"
    r"(?:abrir|entrar|cruzar|subir|bajar|alcanzar))\b",
    re.IGNORECASE,
)


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _widen_excerpt(step: dict[str, Any], evidence: str) -> None:
    """Use the whole short utterance when it supplies omitted local context."""
    excerpt = evidence.strip()
    if excerpt and len(excerpt) <= 300:
        step["source_excerpt"] = excerpt


def _widen_report_excerpt(
    step: dict[str, Any],
    evidence: str,
    literal_end: int,
) -> None:
    """Include the literal speaker prefix without absorbing later player clauses."""
    if 0 < literal_end <= 300:
        end = literal_end
        if end < len(evidence) and evidence[end] in ".!?":
            end += 1
        excerpt = evidence[:end].strip()
        if excerpt:
            step["source_excerpt"] = excerpt


def _step_evidence(step: dict[str, Any], evidence: str) -> str:
    """Scope semantic signals to this step when its excerpt is evidence-bound."""
    excerpt = step.get("source_excerpt")
    if (
        isinstance(excerpt, str)
        and excerpt.strip()
        and _fold(excerpt) in _fold(evidence)
    ):
        return excerpt
    return evidence


def _attempt_outcome_evidence(
    step: dict[str, Any],
    evidence: str,
) -> str:
    """Include only a directly attached, explicit uncertainty about attempt result."""
    excerpt = step.get("source_excerpt")
    if (
        not isinstance(excerpt, str)
        or not excerpt.strip()
        or _fold(excerpt) not in _fold(evidence)
    ):
        return evidence
    start = _fold(evidence).find(_fold(excerpt))
    end = start + len(excerpt)
    tail = evidence[end:]
    if _ATTEMPT_OUTCOME_UNCERTAINTY_RE.search(excerpt) is not None:
        return excerpt
    marker = _ATTEMPT_OUTCOME_UNCERTAINTY_RE.search(tail[:180])
    if marker is None:
        return excerpt
    connector = tail[:marker.start()]
    if re.fullmatch(
        r"[\s,.;:—-]*(?:(?:pero|aunque|y|aun así|aún así)\s*)?",
        connector,
        re.IGNORECASE,
    ) is None:
        return excerpt
    return evidence[start : end + marker.end()]


def _steps_follow_explicit_sequence(
    evidence: str,
    first_step: dict[str, Any],
    second_step: dict[str, Any],
) -> bool:
    """Require both step excerpts and their ordering to be literal in the utterance."""
    first_excerpt = first_step.get("source_excerpt")
    second_excerpt = second_step.get("source_excerpt")
    if not isinstance(first_excerpt, str) or not isinstance(second_excerpt, str):
        return False
    folded = evidence.casefold()
    first_folded = first_excerpt.casefold()
    second_folded = second_excerpt.casefold()
    first_start = folded.find(first_folded)
    if first_start < 0:
        return False
    first_end = first_start + len(first_folded)
    second_start = folded.find(second_folded, first_end)
    if second_start < 0:
        return False
    second_excerpt_start = second_excerpt.lstrip()
    connector_in_second = _SEQUENCE_LINKER_RE.match(second_excerpt_start) is not None
    connector_in_gap = _SEQUENCE_LINKER_RE.search(
        evidence[first_end:second_start]
    ) is not None
    connector_in_first = _SEQUENCE_LINKER_RE.search(first_excerpt) is not None
    return connector_in_gap or connector_in_second or connector_in_first


def _correction_predicate(evidence: str) -> str | None:
    """Return only a literal predicate from an explicit correction construction."""
    match = _CORRECTION_PREDICATE_RE.search(evidence)
    if match is None:
        return None
    for group in ("era", "referia", "queria", "quise", "rectifico"):
        value = match.group(group)
        if value is not None:
            return value
    return None


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
        and _steps_follow_explicit_sequence(evidence, steps[0], steps[1])
        and not normalized.get("relation_claims")
    ):
        steps[0]["actor"] = "player"
        steps[0]["modality"] = "observed"
        steps[0]["polarity"] = "positive"
        steps[0]["reported_outcome"] = "not_claimed"
        steps[1]["actor"] = "player"
        steps[1]["modality"] = "attempted"
        steps[1]["polarity"] = "positive"
        steps[1]["reported_outcome"] = "not_claimed"
        normalized["category"] = "mixed"
        normalized["active_step_index"] = 1
        rules.append("explicit_observation_before_attempt")


    # A first-person decision not to perform an infinitive is an explicit
    # negation even when the model split its supporting state description into
    # a second step. Fold only a literal abstention continuation; preserve any
    # genuinely distinct later player action as a separate step.
    decision_match = _EXPLICIT_DECISION_NOT_TO_ACT_RE.search(evidence)
    decision_is_dialogue_or_report = (
        _PLAYER_DIALOGUE_PREFIX_RE.search(evidence) is not None
        or _REPORTED_SPEAKER_RE.search(evidence) is not None
    )
    if (
        decision_match is not None
        and not decision_is_dialogue_or_report
        and not normalized.get("relation_claims")
    ):
        folded_evidence = evidence.casefold()
        decision_index = None
        for index, step in enumerate(steps):
            excerpt = step.get("source_excerpt")
            if not isinstance(excerpt, str) or not excerpt.strip():
                continue
            start = folded_evidence.find(excerpt.casefold())
            if start < 0:
                continue
            end = start + len(excerpt)
            verb_start, _ = decision_match.span("verb")
            if start <= verb_start < end:
                decision_index = index
                break
        if decision_index is None and len(steps) == 1:
            decision_index = 0

        if decision_index is not None:
            decision_step = steps[decision_index]
            decision_step["actor"] = "player"
            decision_step["modality"] = "negated"
            decision_step["polarity"] = "negative"
            decision_step["reported_outcome"] = "not_claimed"
            _widen_excerpt(decision_step, evidence)
            rules.append("explicit_decision_not_to_act")
            if (
                _NEGATED_ATTEMPT_RE.search(evidence)
                or _ATTEMPT_NEGATES_ACTION_RE.search(evidence)
            ):
                rules.append("explicit_negated_attempt")

            verb_end = decision_match.end("verb")
            continuation_spans = [
                match.span()
                for match in _ABSTENTION_STATE_RE.finditer(evidence)
                if match.start() >= verb_end
                and len(evidence[verb_end : match.start()]) <= 120
                and not re.search(
                    r"[.!?;]|\b(?:después|despues|luego|sin embargo)\b",
                    evidence[verb_end : match.start()],
                    re.IGNORECASE,
                )
            ]
            continuation_indices: set[int] = set()
            for index, step in enumerate(steps):
                if index == decision_index:
                    continue
                excerpt = step.get("source_excerpt")
                if not isinstance(excerpt, str) or not excerpt.strip():
                    continue
                start = folded_evidence.find(excerpt.casefold())
                if start < 0:
                    continue
                end = start + len(excerpt)
                if any(
                    start >= span_start and end <= span_end
                    for span_start, span_end in continuation_spans
                ):
                    continuation_indices.add(index)

            other_indices = set(range(len(steps))) - {decision_index}
            if (
                len(steps) > 1
                and continuation_indices == other_indices
                and continuation_spans
            ):
                decision_step["index"] = 0
                steps = [decision_step]
                normalized["category"] = "action"
                normalized["active_step_index"] = None
                rules.append("explicit_abstention_state_collapsed")
            else:
                distinct_attempt_indices = [
                    index
                    for index, step in enumerate(steps)
                    if index != decision_index
                    and step.get("actor") == "player"
                    and step.get("modality") == "attempted"
                    and step.get("polarity") == "positive"
                ]
                active_index = normalized.get("active_step_index")
                if active_index == decision_index or (
                    isinstance(active_index, int)
                    and (
                        active_index >= len(steps)
                        or steps[active_index].get("actor") != "player"
                        or steps[active_index].get("modality") != "attempted"
                        or steps[active_index].get("polarity") != "positive"
                    )
                ):
                    normalized["active_step_index"] = (
                        distinct_attempt_indices[0]
                        if distinct_attempt_indices
                        else None
                    )
                if distinct_attempt_indices:
                    normalized["category"] = "mixed"
                elif len(steps) == 1:
                    normalized["category"] = "action"
                    normalized["active_step_index"] = None

    # Existing refusal constructions remain supported, but must not reprocess
    # the broader explicit-decision pattern handled above.
    if (
        len(steps) == 1
        and decision_match is None
        and (
            _NEGATED_ATTEMPT_RE.search(evidence)
            or _ATTEMPT_NEGATES_ACTION_RE.search(evidence)
        )
    ):
        step = steps[0]
        step["actor"] = "player"
        step["modality"] = "negated"
        step["polarity"] = "negative"
        step["reported_outcome"] = "not_claimed"
        normalized["category"] = "action"
        normalized["active_step_index"] = None
        _widen_excerpt(step, evidence)
        rules.append("explicit_negated_attempt")

    # A first-person perception report is an observation, not an unresolved
    # mechanical action. The conjugation itself identifies the player as actor.
    if (
        len(steps) == 1
        and _PLAYER_OBSERVATION_RE.search(evidence)
        and normalized.get("category") not in {"question", "dialogue", "correction"}
    ):
        step = steps[0]
        step["actor"] = "player"
        step["modality"] = "observed"
        step["polarity"] = "positive"
        step["reported_outcome"] = "not_claimed"
        normalized["category"] = "report"
        normalized["active_step_index"] = None
        _widen_excerpt(step, evidence)
        rules.append("explicit_player_observation")

    # A completed first-person present action followed by a separate attempt
    # has a resolved first step and a single actionable second step.
    if (
        len(steps) == 2
        and _FIRST_PERSON_PRESENT_RE.search(steps[0].get("source_excerpt", ""))
        and not _NEGATED_ATTEMPT_RE.search(steps[0].get("source_excerpt", ""))
        and _FOLLOW_UP_ATTEMPT_RE.search(evidence)
        and _ATTEMPT_RE.search(steps[1].get("source_excerpt", ""))
        and _steps_follow_explicit_sequence(evidence, steps[0], steps[1])
        and not normalized.get("relation_claims")
        and normalized.get("category") not in {"question", "dialogue", "correction"}
    ):
        steps[0]["actor"] = "player"
        steps[0]["modality"] = "completed"
        steps[0]["polarity"] = "positive"
        steps[0]["reported_outcome"] = "success"
        steps[1]["actor"] = "player"
        steps[1]["modality"] = "attempted"
        steps[1]["polarity"] = "positive"
        steps[1]["reported_outcome"] = "not_claimed"
        normalized["category"] = "mixed"
        normalized["active_step_index"] = 1
        rules.append("explicit_completed_action_before_attempt")

    # An active attempt cannot carry an inferred outcome. Explicit epistemic
    # uncertainty and literal success/failure evidence remain distinguishable.
    if len(steps) == 1 and normalized.get("category") in {"action", "mixed"}:
        step = steps[0]
        step_evidence = _step_evidence(step, evidence)
        attempt_evidence = _attempt_outcome_evidence(step, evidence)
        explicitly_uncertain = _ATTEMPT_OUTCOME_UNCERTAINTY_RE.search(
            attempt_evidence
        )
        explicitly_failed = _FAILURE_RE.search(step_evidence)
        explicitly_succeeded = _EXPLICIT_SUCCESS_RE.search(step_evidence)
        if (
            step.get("actor") == "player"
            and step.get("modality") == "attempted"
            and step.get("polarity") == "positive"
            and not _NEGATED_ATTEMPT_RE.search(step_evidence)
            and not _ATTEMPT_NEGATES_ACTION_RE.search(step_evidence)
        ):
            if explicitly_uncertain:
                if not explicitly_failed:
                    step["reported_outcome"] = "uncertain"
            elif explicitly_failed and (
                _ATTEMPT_RE.search(step_evidence)
                or _IMPLICIT_ATTEMPT_FAILURE_RE.search(step_evidence)
            ):
                step["modality"] = "completed"
                step["polarity"] = "positive"
                step["reported_outcome"] = "failure"
                normalized["active_step_index"] = None
                rules.append("explicit_attempt_failure_outcome")
            elif explicitly_succeeded and _ATTEMPT_RE.search(step_evidence):
                step["modality"] = "completed"
                step["polarity"] = "positive"
                step["reported_outcome"] = "success"
                normalized["active_step_index"] = None
                rules.append("explicit_attempt_success_outcome")
            elif (
                not explicitly_failed
                and not explicitly_succeeded
                and step.get("reported_outcome") != "not_claimed"
            ):
                step["reported_outcome"] = "not_claimed"
                rules.append("unreported_attempt_outcome")

    # A conditional future is a plan, not an active attempt. Restrict this to
    # one-step utterances so a mixed action/plan sequence remains model-led.
    if (
        len(steps) == 1
        and _CONDITIONAL_FUTURE_RE.search(evidence)
        and normalized.get("category") not in {"question", "dialogue", "correction"}
    ):
        step = steps[0]
        step["actor"] = "player"
        step["modality"] = "conditional"
        step["polarity"] = "positive"
        step["reported_outcome"] = "not_claimed"
        _widen_excerpt(step, evidence)
        normalized["category"] = "plan"
        normalized["active_step_index"] = None
        rules.append("explicit_conditional_future")


    # First-person affirmative futures are plans unless an explicit si clause
    # made them conditional above. Negative/uncertain futures are not promoted.
    if (
        len(steps) == 1
        and _FIRST_PERSON_FUTURE_RE.search(evidence)
        and not _CONDITIONAL_FUTURE_RE.search(evidence)
        and not re.search(
            r"\bno\s+(?:(?:me|te|lo|la|le|les|nos|os)\s+)?"
            r"[\wáéíóúüñ]+(?:ré|remos)\b",
            evidence,
            re.IGNORECASE,
        )
        and _EPISTEMIC_UNCERTAINTY_RE.search(
            _step_evidence(steps[0], evidence)
        ) is None
        and normalized.get("category") not in {"question", "dialogue", "correction"}
        and _REPORTED_SPEAKER_RE.search(evidence) is None
    ):
        step = steps[0]
        step["actor"] = "player"
        step["modality"] = "planned"
        step["polarity"] = "positive"
        step["reported_outcome"] = "not_claimed"
        normalized["category"] = "plan"
        normalized["active_step_index"] = None
        rules.append("explicit_first_person_future_plan")

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
        correction_predicate = _correction_predicate(evidence)
        action_frame = step.get("action_frame")
        if correction_predicate is not None and isinstance(action_frame, dict):
            current_predicate = action_frame.get("predicate")
            excerpt = step.get("source_excerpt", "")
            if (
                not isinstance(current_predicate, str)
                or _fold(current_predicate) != _fold(correction_predicate)
                or _fold(current_predicate) not in _fold(evidence)
                or not isinstance(excerpt, str)
                or _fold(current_predicate) not in _fold(excerpt)
            ):
                corrected_frame = dict(action_frame)
                corrected_frame["predicate"] = correction_predicate
                step["action_frame"] = corrected_frame
                rules.append("literal_correction_predicate_repaired")
        rules.append("explicit_surface_correction")

    # Attribute every step inside one literal reported clause, not just
    # single-step model responses. A same-sentence epistemic caveat scopes over
    # the reported proposition even when the model emitted it as a separate
    # step. A later sentence remains independent.
    speaker_match = _REPORTED_SPEAKER_RE.search(evidence)
    if speaker_match is not None:
        speaker = speaker_match.group("speaker").strip()
        indefinite = _fold(speaker).startswith(("un ", "una "))
        body_start = speaker_match.end()
        sentence_end_match = re.search(r"[.!?](?=\s|$)", evidence[body_start:])
        scope_end = (
            body_start + sentence_end_match.start() + 1
            if sentence_end_match is not None
            else len(evidence)
        )
        folded_evidence = evidence.casefold()
        independent_action_match = _INDEPENDENT_PLAYER_ACTION_AFTER_REPORT_RE.search(
            evidence[body_start:scope_end]
        )
        reported_scope_end = (
            body_start + independent_action_match.start()
            if independent_action_match is not None
            else scope_end
        )
        reported_indices: list[int] = []
        reported_excerpt_ends: dict[int, int] = {}
        collapsed_report_action_indices: list[int] = []
        for index, step in enumerate(steps):
            excerpt = step.get("source_excerpt")
            if not isinstance(excerpt, str) or not excerpt.strip():
                continue
            start = folded_evidence.find(excerpt.casefold())
            if start < 0:
                continue
            end = start + len(excerpt)
            if (
                independent_action_match is not None
                and start < reported_scope_end
                and end > reported_scope_end
            ):
                collapsed_report_action_indices.append(index)
            preceding_report_text = evidence[body_start:start]
            follows_independent_linker = re.search(
                r"\b(?:y|pero|entonces|después|despues|luego)\s*$",
                preceding_report_text,
                re.IGNORECASE,
            ) is not None
            begins_player_action = (
                _FIRST_PERSON_ACTIVE_CLAUSE_RE.match(excerpt) is not None
                or _FIRST_PERSON_PRESENT_RE.match(excerpt) is not None
            )
            excerpt_starts_player_clause = re.match(
                r"^\s*(?:y|pero|entonces|después|despues|luego)\s+",
                excerpt,
                re.IGNORECASE,
            ) is not None
            if (
                begins_player_action
                and (follows_independent_linker or excerpt_starts_player_clause)
            ):
                continue
            if (
                start < scope_end
                and end > body_start
                and end <= reported_scope_end
                and (len(evidence) <= 300 or _fold(speaker) in _fold(excerpt))
            ):
                reported_indices.append(index)
                reported_excerpt_ends[index] = end

        if (
            collapsed_report_action_indices
            and independent_action_match is not None
            and normalized.get("category") in {"action", "mixed", "report"}
        ):
            normalized["category"] = "unknown"
            normalized["active_step_index"] = None
            normalized["requires_clarification"] = True
            normalized["clarification_question"] = (
                "He detectado una afirmación referida y una acción dentro del "
                "mismo paso. ¿Puedes separar qué te han contado de lo que "
                "quieres hacer?"
            )
            rules.append("reported_action_not_split_requires_clarification")
            reported_indices.clear()
            reported_excerpt_ends.clear()

        if reported_indices:
            reported_scope = evidence[body_start:reported_scope_end]
            scope_is_uncertain = (
                _EPISTEMIC_UNCERTAINTY_RE.search(reported_scope) is not None
            )
            for index in reported_indices:
                step = steps[index]
                step["actor"] = "other" if indefinite else "npc"
                step["modality"] = "reported"
                step["attributed_to"] = speaker
                if scope_is_uncertain:
                    step["polarity"] = "uncertain"
                _widen_report_excerpt(
                    step,
                    evidence,
                    reported_excerpt_ends[index],
                )
            rules.append("explicit_reported_speaker")
            if scope_is_uncertain:
                rules.append("explicit_reported_clause_uncertainty")
                rules.append("explicit_epistemic_uncertainty")

            if len(reported_indices) == len(steps):
                normalized["category"] = "report"
                normalized["active_step_index"] = None
            elif normalized.get("category") == "action":
                normalized["category"] = "mixed"
                if normalized.get("active_step_index") in reported_indices:
                    normalized["active_step_index"] = next(
                        (
                            index
                            for index, step in enumerate(steps)
                            if index not in reported_indices
                            and step.get("actor") == "player"
                            and step.get("modality") == "attempted"
                            and step.get("polarity") == "positive"
                        ),
                        None,
                    )

    # Epistemic markers express uncertainty, not positive world knowledge.
    step_evidence = (
        _step_evidence(steps[0], evidence)
        if len(steps) == 1
        else ""
    )
    has_explicit_player_action_surface = (
        len(steps) == 1
        and (
            _ATTEMPT_RE.search(step_evidence) is not None
            or _FIRST_PERSON_PRESENT_RE.search(step_evidence) is not None
        )
    )
    if (
        len(steps) == 1
        and not normalized.get("requires_clarification")
        and _EPISTEMIC_UNCERTAINTY_RE.search(step_evidence)
        and not (
            steps[0].get("actor") == "player"
            and steps[0].get("modality") == "attempted"
            and steps[0].get("polarity") == "positive"
            and has_explicit_player_action_surface
        )
    ):
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
