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

from services.discourse.speech_predicates import SPEECH_PREDICATE_ALTERNATION
from services.discourse.topic_history_selector import DiscourseTopicHistorySelector


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
    r"^\s*(?:(?:yo)\s+)?(?:observo|observé|veo|vi|miro|miré|escucho|"
    r"escuché|oigo|oí|detecto|detecté|noto|noté|percibo|percibí|"
    r"distingo|distinguí)\b",
    re.IGNORECASE,
)
_NAMED_NPC_SPEECH_STEP_RE = re.compile(
    r"^\s*(?P<speaker>(?:el|la)\s+[\wáéíóúüñ-]+(?:\s+[\wáéíóúüñ-]+)?"
    r"|[A-ZÁÉÍÓÚÜÑ][\wáéíóúüñ-]*)\s+"
    r"(?:(?:me|te|le|les|nos)\s+)?(?P<predicate>"
    + SPEECH_PREDICATE_ALTERNATION
    + r")\b",
    re.IGNORECASE,
)
_PLAYER_SPEECH_STEP_RE = re.compile(
    r"^\s*(?:(?:yo)\s+)?(?:(?:me|te|le|les|nos)\s+)?(?:"
    + SPEECH_PREDICATE_ALTERNATION
    + r")\b",
    re.IGNORECASE,
)
_PRONOUN_NPC_SPEECH_STEP_RE = re.compile(
    r"^\s*(?P<pronoun>él|ella|ellos|ellas)\s+"
    r"(?:(?:vuelve|volvió|volvia|volvía|empieza|empezó|continúa|continua|sigue)"
    r"\s+a\s+)?(?:habl\w*|convers\w*|pregunt\w*|respond\w*|contest\w*|"
    r"avis\w*|susurr\w*|grit\w*|cuent\w*)\b",
    re.IGNORECASE,
)
_PLAN_DESIRE_RE = re.compile(
    r"\b(?:quiero|quisiera|me gustaría|me gustaria|pretendo|planeo|pienso)\s+"
    r"(?:continuar|seguir|retomar|reanudar|volver\s+a|proseguir|"
    r"terminar|acabar|empezar|comenzar|ir\s+a)\b",
    re.IGNORECASE,
)
_INDEPENDENT_UNCERTAINTY_PREFIX_RE = re.compile(
    r"^\s*(?:quizá|quizas|tal\s+vez|puede\s+que|es\s+posible\s+que)\b",
    re.IGNORECASE,
)
_OBSERVED_THIRD_PARTY_ACTION_RE = re.compile(
    r"^\s*(?:veo|vi|observo|observé|miro|miré|escucho|escuché)\s+a\s+"
    r"(?P<speaker>[A-ZÁÉÍÓÚÜÑ][\wáéíóúüñ-]*)\s+"
    r"(?P<predicate>dejar|dejando|entregar|entregando|entrar|entrando|"
    r"salir|saliendo|señalar|señala|señalando|mover|moviendo|"
    r"guardar|guardando|mostrar|muestra|mostrando)\b",
    re.IGNORECASE,
)
_NPC_PHYSICAL_EVENT_STEP_RE = re.compile(
    r"^\s*(?P<speaker>(?:el|la)\s+[\wáéíóúüñ-]+(?:\s+[\wáéíóúüñ-]+)?"
    r"|[A-ZÁÉÍÓÚÜÑ][\wáéíóúüñ-]*)\s+"
    r"(?:(?:me|te|le|les|nos)\s+)?"
    r"(?:entreg\w*|devolv\w*|recib\w*|entr\w*|sal\w*|"
    r"señal\w*|muestr\w*|mostr\w*|guard\w*|mov\w*|"
    r"golpe\w*|atac\w*|proteg\w*)\b",
    re.IGNORECASE,
)
_NEGATED_FIRST_PERSON_ACTION_RE = re.compile(
    r"^\s*no\s+(?:(?:yo)\s+)?(?:abro|cierro|desbloqueo|recojo|tomo|"
    r"cojo|guardo|saco|coloco|entrego|recibo|enciendo|apago|rompo|muevo|"
    r"levanto|agarro|cruzo|activo|desato|sujeto|trepo|escalo|camino|"
    r"corro|entro|salgo|subo|bajo|salto|nado|viajo)\b",
    re.IGNORECASE,
)
_PLAYER_INVESTIGATION_ATTEMPT_RE = re.compile(
    r"^\s*(?:(?:yo)\s+)?(?:examino|examiné|inspecciono|inspeccioné)\b",
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
    r"me\s+abstengo\s+de|desisto\s+de|renuncio\s+a|"
    r"cancelo\s+(?:el|mi)\s+intento\s+de|abandono\s+la\s+idea\s+de|"
    r"no\s+pienso|no\s+pretendo|abro|cierro|desbloqueo|recojo|tomo|cojo|"
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
    r")\s+(?:(?:me|te|le|les|nos)\s+)?(?:"
    + SPEECH_PREDICATE_ALTERNATION
    + r")\s+que\b",
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
_REPORTED_CLAIM_IDENTITY_UNCERTAINTY_RE = re.compile(
    r"\b(?:no\s+(?:sé|se|sabe|saben|sabemos|recuerda|recuerdan)|"
    r"ignora|desconoce|duda)\s+si\s+"
    r"(?:era|es|fue)\s+(?:real|ciert\w*|verdad)\b",
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


def _strip_explicit_callback_prefix(
    payload: dict[str, Any],
    steps: list[dict[str, Any]],
    evidence: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """Remove a callback-only leading clause misrepresented as a world event.

    This is intentionally narrow: the callback must be an explicit, anchored
    first clause, the model must have emitted it as the first separate step,
    and at least one later step must remain. Callback history stays in discourse
    context; this does not synthesize an action or resolve the referenced topic.
    """
    if len(steps) < 2:
        return None
    delimiter = re.search(r"[,;]", evidence)
    if delimiter is None:
        return None
    prefix = evidence[:delimiter.start()].strip()
    selector = DiscourseTopicHistorySelector
    if (
        not selector.reactivates_prior_topic(prefix)
        or not selector._callback_anchor_sequence(prefix)
    ):
        return None

    first_excerpt = steps[0].get("source_excerpt")
    if not isinstance(first_excerpt, str) or not first_excerpt.strip():
        return None
    clean = lambda value: _fold(value).strip(" \t\r\n.,;:!?¡¿")
    if clean(first_excerpt) != clean(prefix):
        return None

    normalized = dict(payload)
    retained_steps = [dict(step) for step in steps[1:]]
    old_to_new = {old: old - 1 for old in range(1, len(steps))}
    first_retained_excerpt = retained_steps[0].get("source_excerpt")
    if isinstance(first_retained_excerpt, str) and first_retained_excerpt.strip():
        # Keep the literal callback anchor in the first actionable step's
        # evidence span. Otherwise later validation drops it and the resolver
        # sees only an ungrounded pronoun.
        excerpt_start = evidence.find(first_retained_excerpt)
        if excerpt_start >= 0:
            excerpt_end = excerpt_start + len(first_retained_excerpt)
            retained_steps[0]["source_excerpt"] = evidence[:excerpt_end].strip()
    for index, step in enumerate(retained_steps):
        step["index"] = index
    old_active = payload.get("active_step_index")
    if isinstance(old_active, int) and not isinstance(old_active, bool):
        normalized["active_step_index"] = old_to_new.get(old_active)
    else:
        normalized["active_step_index"] = old_active

    raw_claims = payload.get("relation_claims")
    if isinstance(raw_claims, list):
        claims: list[Any] = []
        for claim in raw_claims:
            if not isinstance(claim, dict):
                claims.append(claim)
                continue
            old_index = claim.get("step_index")
            if isinstance(old_index, int) and not isinstance(old_index, bool):
                if old_index not in old_to_new:
                    continue
                claim = dict(claim)
                claim["step_index"] = old_to_new[old_index]
            claims.append(claim)
        normalized["relation_claims"] = claims

    normalized["steps"] = retained_steps
    return normalized, retained_steps


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


def _collapse_split_attempt_outcome(
    steps: list[dict[str, Any]],
    evidence: str,
    normalized: dict[str, Any],
    rules: list[str],
) -> list[dict[str, Any]]:
    """Join a directly attached result clause split by the model into step two.

    Only a two-step, literal, contiguous player attempt followed by a single
    uncertainty/failure continuation is collapsed. Independent later actions,
    relation claims, reordered excerpts and additional steps remain untouched.
    """
    if (
        len(steps) != 2
        or len(evidence) > 300
        or normalized.get("relation_claims")
        # Reported speech and its epistemic caveat are handled by the
        # speaker-scoping rule below; they are not player-attempt outcomes.
        or _REPORTED_SPEAKER_RE.search(evidence) is not None
    ):
        return steps
    first, second = steps
    if (
        first.get("actor") != "player"
        or first.get("modality") != "attempted"
        or first.get("polarity") != "positive"
        or not isinstance(first.get("source_excerpt"), str)
        or not isinstance(second.get("source_excerpt"), str)
    ):
        return steps

    first_excerpt = first["source_excerpt"].strip()
    second_excerpt = second["source_excerpt"].strip()
    folded = _fold(evidence)
    first_folded = _fold(first_excerpt)
    second_folded = _fold(second_excerpt)
    first_start = folded.find(first_folded)
    if first_start < 0 or not first_folded:
        return steps
    first_end = first_start + len(first_folded)
    second_start = folded.find(second_folded, first_end)
    if second_start < first_end or not second_folded:
        return steps
    second_end = second_start + len(second_folded)
    if re.search(r"\w", evidence[second_end:]):
        return steps

    connective = evidence[first_end:second_start]
    connective_is_only_linker = re.fullmatch(
        r"[\s,;:—-]*(?:(?:pero|aunque|y|aun así|aún así)\s*)?",
        connective,
        re.IGNORECASE,
    ) is not None
    # A short failure phrase may itself be separated into the connector gap
    # (e.g. "pero no gira") while the model puts only "el cofre sigue cerrado"
    # in step two. Permit that only when the gap is itself explicit result text.
    connector_contains_result = (
        _ATTEMPT_OUTCOME_UNCERTAINTY_RE.search(connective) is not None
        or _FAILURE_RE.search(connective) is not None
    )
    if not connective_is_only_linker and not connector_contains_result:
        return steps

    trailing_evidence = evidence[first_end:second_end]
    uncertainty = _ATTEMPT_OUTCOME_UNCERTAINTY_RE.search(trailing_evidence)
    failure = _FAILURE_RE.search(trailing_evidence)
    if uncertainty is None and failure is None:
        uncertainty = _ATTEMPT_OUTCOME_UNCERTAINTY_RE.search(connective)
        failure = _FAILURE_RE.search(connective)
    if uncertainty is None and failure is None:
        return steps
    if uncertainty is not None and failure is not None:
        return steps

    first["source_excerpt"] = evidence.strip()
    steps = [first]
    normalized["steps"] = steps
    normalized["category"] = "action"
    normalized["active_step_index"] = 0
    rules.append(
        "split_attempt_uncertainty_collapsed"
        if uncertainty is not None
        else "split_attempt_failure_collapsed"
    )
    return steps


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


def _normalize_explicit_actor_modalities(
    normalized: dict[str, Any],
    steps: list[dict[str, Any]],
    evidence: str,
    rules: list[str],
) -> None:
    """Repair literal speaker/modality cues in already-separated steps."""
    if not steps:
        return

    dialogue_indices: list[int] = []
    observed_npc_indices: list[int] = []

    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        excerpt = step.get("source_excerpt")
        if not isinstance(excerpt, str) or not excerpt.strip():
            continue
        if _fold(excerpt) not in _fold(evidence):
            continue
        # A reported proposition ("Mara afirma que...") keeps its attributed
        # report semantics; it is not rewritten as a direct speech event.
        if _REPORTED_SPEAKER_RE.search(excerpt):
            continue

        named_speech = _NAMED_NPC_SPEECH_STEP_RE.match(excerpt)
        if named_speech is not None:
            speaker = named_speech.group("speaker").strip()
            step["actor"] = "npc"
            step["modality"] = "dialogue"
            step["polarity"] = "positive"
            step["reported_outcome"] = "not_claimed"
            step["attributed_to"] = speaker
            dialogue_indices.append(index)
            rules.append("explicit_npc_dialogue_step")
            continue

        if _PLAYER_SPEECH_STEP_RE.match(excerpt):
            step["actor"] = "player"
            step["modality"] = "dialogue"
            step["polarity"] = "positive"
            step["reported_outcome"] = "not_claimed"
            dialogue_indices.append(index)
            rules.append("explicit_player_dialogue_step")
            continue

        pronoun_speech = _PRONOUN_NPC_SPEECH_STEP_RE.match(excerpt)
        if pronoun_speech is not None:
            step["actor"] = "npc"
            step["modality"] = "dialogue"
            step["polarity"] = "positive"
            step["reported_outcome"] = "not_claimed"
            # The grammatical pronoun establishes the speaker role, not a
            # canonical identity. Keep attribution empty for later resolution.
            step["attributed_to"] = None
            dialogue_indices.append(index)
            rules.append("explicit_pronoun_npc_dialogue_step")
            continue

        observed = _OBSERVED_THIRD_PARTY_ACTION_RE.match(excerpt)
        if observed is not None and len(steps) == 1:
            speaker = observed.group("speaker").strip()
            step["actor"] = "npc"
            step["modality"] = "observed"
            step["polarity"] = "positive"
            step["reported_outcome"] = "not_claimed"
            step["attributed_to"] = speaker
            step["source_excerpt"] = evidence.strip()
            observed_npc_indices.append(index)
            rules.append("explicit_observed_npc_action")
            continue

        physical_event = _NPC_PHYSICAL_EVENT_STEP_RE.match(excerpt)
        if physical_event is not None:
            speaker = _fold(physical_event.group("speaker").strip())
            if speaker not in {"el jugador", "la jugadora"}:
                step["actor"] = "npc"
                step["modality"] = "observed"
                step["polarity"] = "positive"
                step["reported_outcome"] = "not_claimed"
                observed_npc_indices.append(index)
                rules.append("explicit_observed_npc_event_step")

    # A plainly negated first-person action followed by a separate positive
    # attempt remains one action sequence, not a mixed report/dialogue category.
    if len(steps) >= 2:
        first_excerpt = steps[0].get("source_excerpt")
        second_excerpt = steps[1].get("source_excerpt")
        if (
            isinstance(first_excerpt, str)
            and isinstance(second_excerpt, str)
            and _NEGATED_FIRST_PERSON_ACTION_RE.match(first_excerpt)
            and _fold(first_excerpt) in _fold(evidence)
            and _fold(second_excerpt) in _fold(evidence)
        ):
            steps[0]["actor"] = "player"
            steps[0]["modality"] = "negated"
            steps[0]["polarity"] = "negative"
            steps[0]["reported_outcome"] = "not_claimed"
            active = next(
                (
                    i for i, step in enumerate(steps[1:], start=1)
                    if isinstance(step, dict)
                    and step.get("actor") == "player"
                    and step.get("modality") == "attempted"
                    and step.get("polarity") == "positive"
                ),
                None,
            )
            if active is not None:
                normalized["category"] = "action"
                normalized["active_step_index"] = active
                rules.append("explicit_negated_then_positive_player_action")

    if dialogue_indices:
        if len(dialogue_indices) == len(steps):
            normalized["category"] = "dialogue"
            normalized["active_step_index"] = None
        elif len(steps) > 1:
            normalized["category"] = "mixed"
            active = normalized.get("active_step_index")
            if (
                isinstance(active, int)
                and (
                    active >= len(steps)
                    or steps[active].get("modality") == "dialogue"
                )
            ):
                normalized["active_step_index"] = next(
                    (
                        i for i, step in enumerate(steps)
                        if isinstance(step, dict)
                        and step.get("actor") == "player"
                        and step.get("modality") == "attempted"
                        and step.get("polarity") == "positive"
                    ),
                    None,
                )

    if observed_npc_indices and len(steps) == 1:
        normalized["category"] = "report"
        normalized["active_step_index"] = None


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
    reported_speaker_prefix = _REPORTED_SPEAKER_RE.search(evidence)
    decision_starts_independent_clause = (
        decision_match is not None
        and re.match(
            r"^\s*(?:y|pero|entonces|después|despues|luego)\s+"
            r"(?:(?:yo)\s+)?(?:decid(?:o|í|imos)|he\s+decidido|"
            r"hemos\s+decidido|prefiero|preferiría|opto\s+por|"
            r"no\s+quiero|no\s+voy\s+a|no\s+pienso|no\s+pretendo|"
            r"me\s+niego\s+a|me\s+abstengo\s+de|desisto\s+de|"
            r"renuncio\s+a)",
            decision_match.group(0),
            re.IGNORECASE,
        ) is not None
    )
    decision_is_dialogue_or_report = (
        _PLAYER_DIALOGUE_PREFIX_RE.search(evidence) is not None
        or (
            reported_speaker_prefix is not None
            and not decision_starts_independent_clause
        )
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
            # Keep a later player decision's evidence separate from an
            # earlier reported NPC clause.
            if reported_speaker_prefix is None:
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

            previous_active_index = normalized.get("active_step_index")
            if continuation_indices and continuation_spans:
                # Remove only literal state-confirmation steps, even when the
                # same utterance also contains a separate NPC report or action.
                retained_steps: list[dict[str, Any]] = []
                old_to_new_index: dict[int, int] = {}
                for old_index, step in enumerate(steps):
                    if old_index in continuation_indices:
                        continue
                    new_index = len(retained_steps)
                    step["index"] = new_index
                    retained_steps.append(step)
                    old_to_new_index[old_index] = new_index
                steps = retained_steps
                decision_index = old_to_new_index[decision_index]
                if (
                    isinstance(previous_active_index, int)
                    and previous_active_index in old_to_new_index
                ):
                    normalized["active_step_index"] = old_to_new_index[
                        previous_active_index
                    ]
                else:
                    normalized["active_step_index"] = None
                rules.append("explicit_abstention_state_collapsed")
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
            elif len(steps) > 1:
                normalized["category"] = "mixed"

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

    # Investigation verbs such as "examino" and "inspecciono" represent an
    # intentional player attempt; reserve passive report normalization for
    # observe/see/hear constructions.
    if (
        len(steps) == 1
        and _PLAYER_INVESTIGATION_ATTEMPT_RE.search(evidence)
        and normalized.get("category") not in {"question", "dialogue", "correction"}
    ):
        step = steps[0]
        step["actor"] = "player"
        step["modality"] = "attempted"
        step["polarity"] = "positive"
        step["reported_outcome"] = "not_claimed"
        normalized["category"] = "action"
        normalized["active_step_index"] = 0
        _widen_excerpt(step, evidence)
        rules.append("explicit_player_investigation_attempt")

    # A first-person perception report is an observation, not an unresolved
    # mechanical action. The conjugation itself identifies the player as actor.
    if (
        len(steps) == 1
        and _PLAYER_OBSERVATION_RE.search(evidence)
        and not _PLAYER_INVESTIGATION_ATTEMPT_RE.search(evidence)
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

    # Some models split "Intento X, pero no sé si lo consigo" or a clearly
    # failed result into two steps. Collapse only a directly attached,
    # literal result clause; never merge an independent later action.
    if normalized.get("category") in {"action", "mixed"}:
        steps = _collapse_split_attempt_outcome(
            steps,
            evidence,
            normalized,
            rules,
        )

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
                or _EXPLICIT_DECISION_NOT_TO_ACT_RE.match(excerpt) is not None
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

            if (
                scope_is_uncertain
                and len(reported_indices) == len(steps)
                and len(steps) > 1
                and len(evidence) <= 300
                and _REPORTED_CLAIM_IDENTITY_UNCERTAINTY_RE.search(
                    reported_scope
                ) is not None
            ):
                # A reported proposition plus its epistemic caveat is one
                # attributed claim, not two independent world events.
                retained = dict(steps[reported_indices[0]])
                retained["index"] = 0
                retained["source_excerpt"] = evidence[:scope_end].strip()
                retained["actor"] = "other" if indefinite else "npc"
                retained["modality"] = "reported"
                retained["polarity"] = "uncertain"
                retained["attributed_to"] = speaker
                steps = [retained]
                normalized["steps"] = steps
                normalized["category"] = "report"
                normalized["active_step_index"] = None
                reported_indices = [0]
                rules.append("reported_uncertainty_steps_collapsed")

            if len(reported_indices) == len(steps):
                normalized["category"] = "report"
                normalized["active_step_index"] = None
            elif normalized.get("category") in {"action", "mixed"}:
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

    _normalize_explicit_actor_modalities(normalized, steps, evidence, rules)

    callback_normalization = _strip_explicit_callback_prefix(
        normalized,
        steps,
        evidence,
    )
    if callback_normalization is not None:
        normalized, steps = callback_normalization
        rules.append("explicit_callback_preamble_removed")

    normalized["steps"] = steps
    return normalized, IntentSurfaceNormalizationSummary(tuple(dict.fromkeys(rules)))
