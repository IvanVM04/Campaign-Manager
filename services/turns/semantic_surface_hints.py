"""High-confidence Spanish surface rules for semantic-frame normalization.

This module is deliberately conservative. It only repairs typed semantic hints
when a local grammatical construction is explicit in the already-validated
player evidence. It never resolves canonical IDs or authorizes world changes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Any

from models.player_intent_analysis import IntentStep, PlayerIntentAnalysis
from models.semantic_frames import (
    MAX_RELATION_CLAIMS,
    SemanticActionFamily,
    SemanticActionFrame,
    SemanticArgument,
    SemanticArgumentRole,
    SemanticMention,
    SemanticModality,
    SemanticObjectKind,
    SemanticPolarity,
    SemanticRelationClaim,
    SemanticRelationFamily,
)

_END_PUNCTUATION = " \t\r\n.,;:!?¡¿'\"“”«»"
_ORGANIZATION_WORDS = {
    "asociacion",
    "asociación",
    "banda",
    "clan",
    "compania",
    "compañía",
    "consejo",
    "ejercito",
    "ejército",
    "equipo",
    "faccion",
    "facción",
    "gremio",
    "guardia",
    "iglesia",
    "orden",
    "secta",
    "tripulacion",
    "tripulación",
}
_CREATURE_WORDS = {
    "araña",
    "bestia",
    "dragon",
    "dragón",
    "esqueleto",
    "goblin",
    "lobo",
    "ogro",
    "orco",
    "oso",
    "trol",
    "vampiro",
}
_ITEM_WORDS = {
    "anillo",
    "armadura",
    "arco",
    "baston",
    "bastón",
    "carta",
    "cofre",
    "dagas",
    "espada",
    "gema",
    "herramienta",
    "llave",
    "mapa",
    "martillo",
    "mochila",
    "moneda",
    "pergamino",
    "pocion",
    "poción",
    "reliquia",
    "tesoro",
    "lupa",
}
_PERSON_WORDS = {
    "amigo",
    "amiga",
    "capitan",
    "capitán",
    "capitana",
    "caballero",
    "dama",
    "guerrero",
    "guerrera",
    "maga",
    "mago",
    "mercader",
    "monje",
    "monja",
    "reina",
    "rey",
    "soldado",
    "compañero",
    "compañera",
    "aprendiz",
}
_LOCATION_WORDS = {
    "aldea",
    "bosque",
    "calle",
    "camino",
    "castillo",
    "cueva",
    "dormitorio",
    "fortaleza",
    "molino",
    "montaña",
    "montana",
    "muelle",
    "pasillo",
    "puente",
    "puerta",
    "puerto",
    "sendero",
    "templo",
    "torre",
    "torreón",
    "torreon",
}

_COMBAT_VERB_RE = re.compile(
    r"\b(?:golpe\w*|atac\w*|hiere|hieren|herí|heriste|herimos|hirió|"
    r"hirieron|herir|herido|apuñal\w*|dispar\w*|acuchill\w*)\b",
    re.IGNORECASE,
)
_MOVEMENT_VERB_RE = re.compile(
    r"\b(?:camin\w*|acompañ\w*|viaj\w*|"
    r"entr(?:ar|o|as|a|amos|an|é|ó|aron|aba|aban)|"
    r"sal(?:ir|go|es|e|imos|en|í|ió|ieron)|"
    r"desplaz\w*|recorr\w*|sig(?:o|ues|ue|uimos|uen|uir))\b",
    re.IGNORECASE,
)
_PERCEPTION_VERB_RE = re.compile(
    r"\b(?:observ\w*|mir\w*|veo|ves|ve|vemos|ven|vi|ver|"
    r"escuch\w*|oigo|oyes|oye|oyen|detect\w*|examin\w*|percib\w*)\b",
    re.IGNORECASE,
)
_COMMUNICATION_VERB_RE = re.compile(
    r"\b(?:habl\w*|digo|dice|dicen|decir|dije|dijo|"
    r"afirm\w*|asegur\w*|declar\w*|sostuv\w*|"
    r"cuent\w*|cont(?:ar|o|as|a|amos|an|é|ó|aron|aba|aban|ado|ando)|"
    r"pregunt\w*|respond\w*|susurr\w*|avis\w*)\b",
    re.IGNORECASE,
)
_TRANSFER_VERB_RE = re.compile(
    r"\b(?:entreg\w*|devolv\w*|recib\w*|"
    r"guard(?:o|as|a|amos|an|é|ó|aron|aba|aban|ar|ando|ado)|"
    r"deposit\w*|coloc\w*|met(?:o|es|e|emos|en|í|ió|ieron|er|iendo)|"
    r"sac(?:o|as|a|amos|an|é|ó|aron|ar|ando)|"
    r"retir\w*|recog\w*|doy|das|da|damos|dan|dar|di|dio|dieron)\b",
    re.IGNORECASE,
)
_ITEM_USE_VERB_RE = re.compile(
    r"\b(?:abr\w*|desbloque\w*|cort\w*|forz\w*|"
    r"encend\w*|repar\w*|afloj\w*|ilumin\w*)\b",
    re.IGNORECASE,
)
_HIDE_VERB_RE = re.compile(r"\b(?:escond\w*|ocult\w*)\b", re.IGNORECASE)
_INSTRUMENT_RE = re.compile(
    r"\b(?:utilizando|usando|con\s+ayuda\s+de|mediante|con)\s+"
    r"(?P<instrument>.+)$",
    re.IGNORECASE,
)
_TEMPORAL_PREFIX_RE = re.compile(
    r"^\s*(?P<temporal>(?:desde|a\s+partir\s+de|durante)\s+[^,;]+),\s*"
    r"(?P<clause>.+)$",
    re.IGNORECASE,
)
_REPORTED_PREFIX_RE = re.compile(
    r"^\s*(?P<speaker>[^,.;:!?]+?)\s+"
    r"(?:afirma|afirmó|dice|dijo|asegura|aseguró|sostiene|sostuvo|declara|declaró)"
    r"\s+que\s+(?P<clause>.+)$",
    re.IGNORECASE,
)

_RELATION_PATTERNS: tuple[
    tuple[str, re.Pattern[str], SemanticRelationFamily], ...
] = (
    (
        "relation_employment_para",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>trabaj\w*)\s+"
            r"para\s+(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.EMPLOYMENT,
    ),
    (
        "relation_belongs_to",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?"
            r"(?P<predicate>pertenec\w*)\s+(?:a|al)\s+(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.UNKNOWN,
    ),
    (
        "relation_ownership_dueno",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>es\s+dueñ[oa])\s+"
            r"de\s+(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.OWNERSHIP,
    ),
    (
        "relation_ownership_poseer",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>pose\w*)\s+"
            r"(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.OWNERSHIP,
    ),
    (
        "relation_possession_tener",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>tien\w*)\s+"
            r"(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.POSSESSION,
    ),
    (
        "relation_kinship",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>es\s+(?:herman[oa]|"
            r"madre|padre|hij[oa]|prim[oa]|t[ií][oa]))\s+"
            r"de\s+(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.KINSHIP,
    ),
    (
        "relation_service",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>sirv\w*)\s+"
            r"a\s+(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.SERVICE,
    ),
    (
        "relation_knowledge",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>conoc\w*)\s+"
            r"a\s+(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.KNOWLEDGE,
    ),
    (
        "relation_containment",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>está|esta)\s+"
            r"dentro\s+de\s+(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.CONTAINMENT,
    ),
    (
        "relation_allegiance",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>jur\w*\s+lealtad)\s+"
            r"a\s+(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.ALLEGIANCE,
    ),
    (
        "relation_protection",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>proteg\w*)\s+"
            r"a\s+(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.PROTECTION,
    ),
    (
        "relation_hostility",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>odi\w*|detest\w*)\s+"
            r"a(?:l)?\s+(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.HOSTILITY,
    ),
    (
        "relation_friendship",
        re.compile(
            r"^(?P<subject>.+?)\s+y\s+(?P<object>.+?)\s+(?P<negative>no\s+)?"
            r"(?P<predicate>son\s+amig(?:o|a)s?)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.FRIENDSHIP,
    ),
    (
        "relation_part_of",
        re.compile(
            r"^(?P<subject>.+?)\s+(?P<negative>no\s+)?(?P<predicate>form\w*\s+parte)\s+"
            r"(?:de\s+el|de\s+la|de\s+los|de\s+las|del|de)\s+"
            r"(?P<object>.+)$",
            re.IGNORECASE,
        ),
        SemanticRelationFamily.PART_OF,
    ),
)


@dataclass(frozen=True, slots=True)
class SurfaceNormalizationSummary:
    """Content-free counters for safe logging and live evaluation."""

    dropped_ungrounded_target_mentions: int = 0
    dropped_ungrounded_action_arguments: int = 0
    dropped_ungrounded_relation_claims: int = 0
    widened_relation_evidence_spans: int = 0
    action_rules_applied: tuple[str, ...] = ()
    relation_rules_applied: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _RelationSurface:
    rule_id: str
    subject: str
    predicate: str
    object: str
    family: SemanticRelationFamily
    negative: bool
    attributed_to: str | None
    temporal_expression: str | None


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _is_literal(source: str, value: str) -> bool:
    return bool(value.strip()) and _fold(value) in _fold(source)


def _trim_surface(value: str) -> str:
    return value.strip(_END_PUNCTUATION)


def _normalize_kind_word(value: str) -> str:
    return _fold(value).strip(" \t\r\n.,;:!?¡¿'\"“”«»")


def _guess_kind(value: str, role: SemanticArgumentRole | None = None) -> SemanticObjectKind:
    folded = _normalize_kind_word(value)
    tokens = set(re.findall(r"[^\W_]+", folded, flags=re.UNICODE))
    if tokens & _CREATURE_WORDS:
        return SemanticObjectKind.CREATURE
    if tokens & _LOCATION_WORDS:
        return SemanticObjectKind.LOCATION
    if tokens & _ORGANIZATION_WORDS:
        return SemanticObjectKind.FACTION
    if tokens & _ITEM_WORDS:
        if "cofre" in tokens:
            return SemanticObjectKind.WORLD_ENTITY
        return SemanticObjectKind.ITEM_INSTANCE
    if role in {
        SemanticArgumentRole.AGENT,
        SemanticArgumentRole.PATIENT,
        SemanticArgumentRole.RECIPIENT,
        SemanticArgumentRole.COMPANION,
    }:
        if tokens & _PERSON_WORDS:
            return SemanticObjectKind.CHARACTER
        if value[:1].isupper() and " " not in value.strip():
            return SemanticObjectKind.CHARACTER
    return SemanticObjectKind.UNKNOWN


def _make_argument(
    role: SemanticArgumentRole,
    mention_text: str,
    source_excerpt: str,
    *,
    existing_frame: SemanticActionFrame,
) -> SemanticArgument | None:
    mention_text = _trim_surface(mention_text)
    if not mention_text or not _is_literal(source_excerpt, mention_text):
        return None
    existing_kind = next(
        (
            argument.mention.kind_hint
            for argument in existing_frame.arguments
            if _fold(argument.mention.text) == _fold(mention_text)
        ),
        SemanticObjectKind.UNKNOWN,
    )
    guessed_kind = _guess_kind(mention_text, role)
    kind = (
        guessed_kind
        if guessed_kind is not SemanticObjectKind.UNKNOWN
        else existing_kind
    )
    return SemanticArgument(
        role=role,
        mention=SemanticMention(text=mention_text, kind_hint=kind),
    )


def _find_predicate_match(
    pattern: re.Pattern[str],
    text: str,
    predicate: str,
) -> re.Match[str] | None:
    for match in pattern.finditer(text):
        if _fold(match.group(0)) == _fold(predicate):
            return match
    return None


def _agent_argument(
    text_before_predicate: str,
    source_excerpt: str,
    frame: SemanticActionFrame,
) -> SemanticArgument | None:
    candidate = _trim_surface(text_before_predicate)
    if not candidate or "," in candidate:
        return None
    if _fold(candidate).startswith(
        ("ayer ", "hoy ", "entonces ", "luego ", "después ", "despues ", "más tarde ", "mas tarde ")
    ):
        return None
    if _fold(candidate) in {"yo", "nosotros", "nosotras"}:
        return None
    if not candidate[:1].isupper() and not candidate.casefold().startswith(
        ("el ", "la ", "los ", "las ", "un ", "una ")
    ):
        return None
    return _make_argument(
        SemanticArgumentRole.AGENT,
        candidate,
        source_excerpt,
        existing_frame=frame,
    )


def _normalize_action_frame(
    step: IntentStep,
    *,
    speech_only: bool = False,
) -> tuple[SemanticActionFrame | None, str | None]:
    frame = step.action_frame
    if frame is None:
        return None, None
    text = step.source_excerpt
    predicate = frame.predicate
    all_rules: tuple[tuple[str, re.Pattern[str], SemanticActionFamily], ...] = (
        ("action_combat", _COMBAT_VERB_RE, SemanticActionFamily.COMBAT),
        ("action_movement", _MOVEMENT_VERB_RE, SemanticActionFamily.MOVEMENT),
        ("action_perception", _PERCEPTION_VERB_RE, SemanticActionFamily.PERCEPTION),
        ("action_communication", _COMMUNICATION_VERB_RE, SemanticActionFamily.COMMUNICATION),
        ("action_transfer", _TRANSFER_VERB_RE, SemanticActionFamily.TRANSFER),
    )
    rules = (
        (("action_communication", _COMMUNICATION_VERB_RE, SemanticActionFamily.COMMUNICATION),)
        if speech_only
        or step.modality in {SemanticModality.DIALOGUE, SemanticModality.QUESTION}
        else all_rules
    )
    selected_rule: str | None = None
    selected_family = frame.family
    predicate_match: re.Match[str] | None = None
    for rule_id, pattern, family in rules:
        match = _find_predicate_match(pattern, text, predicate)
        if match is not None:
            selected_rule = rule_id
            selected_family = family
            predicate_match = match
            break

    if predicate_match is None:
        item_use_match = _find_predicate_match(_ITEM_USE_VERB_RE, text, predicate)
        if item_use_match is not None:
            marker = _INSTRUMENT_RE.search(text[item_use_match.end():])
            if (
                marker is not None
                and _guess_kind(
                    marker.group("instrument"),
                    SemanticArgumentRole.PATIENT,
                )
                not in {SemanticObjectKind.CHARACTER, SemanticObjectKind.CREATURE}
            ):
                selected_rule = "action_item_use"
                selected_family = SemanticActionFamily.ITEM_USE
                predicate_match = item_use_match

    if predicate_match is None:
        hide_match = _find_predicate_match(_HIDE_VERB_RE, text, predicate)
        if hide_match is not None:
            tail = text[hide_match.end():].strip()
            location_match = re.match(
                r"^(?P<theme>.+?)\s+(?:bajo|debajo\s+de|detrás\s+de|tras|"
                r"sobre)\s+(?P<location>.+)$",
                tail,
                re.IGNORECASE,
            )
            if location_match is not None:
                selected_rule = "action_hide_location"
                predicate_match = hide_match

    if predicate_match is None:
        return frame, None

    new_arguments: list[SemanticArgument] = []
    tail = text[predicate_match.end():].strip()
    prefix = text[:predicate_match.start()]
    if selected_rule == "action_combat":
        match = re.match(
            r"^(?P<patient>(?:al|a\s+la|a\s+los|a\s+las|a|el|la|los|las|un|una)"
            r"\s+.+?)(?:\s+con\s+(?P<instrument>.+))?$",
            tail,
            re.IGNORECASE,
        )
        if match is not None:
            patient = _make_argument(
                SemanticArgumentRole.PATIENT,
                match.group("patient"),
                text,
                existing_frame=frame,
            )
            instrument = (
                _make_argument(
                    SemanticArgumentRole.INSTRUMENT,
                    match.group("instrument"),
                    text,
                    existing_frame=frame,
                )
                if match.group("instrument")
                else None
            )
            if (
                instrument is not None
                and _guess_kind(
                    instrument.mention.text,
                    SemanticArgumentRole.PATIENT,
                )
                in {SemanticObjectKind.CHARACTER, SemanticObjectKind.CREATURE}
            ):
                instrument = None
            new_arguments.extend(
                argument for argument in (patient, instrument) if argument is not None
            )
    elif selected_rule == "action_item_use":
        marker = _INSTRUMENT_RE.search(tail)
        if marker is not None:
            theme_text = _trim_surface(tail[:marker.start()])
            theme = _make_argument(
                SemanticArgumentRole.THEME,
                theme_text,
                text,
                existing_frame=frame,
            )
            instrument = _make_argument(
                SemanticArgumentRole.INSTRUMENT,
                marker.group("instrument"),
                text,
                existing_frame=frame,
            )
            if (
                instrument is not None
                and _guess_kind(
                    instrument.mention.text,
                    SemanticArgumentRole.PATIENT,
                )
                in {SemanticObjectKind.CHARACTER, SemanticObjectKind.CREATURE}
            ):
                instrument = None
            new_arguments.extend(
                argument for argument in (theme, instrument) if argument is not None
            )
    elif selected_rule == "action_movement":
        path_match = re.match(
            r"^desde\s+(?P<source>.+?)\s+por\s+(?P<path>.+?)\s+"
            r"hasta\s+(?P<destination>.+)$",
            tail,
            re.IGNORECASE,
        )
        companion_match = re.match(
            r"^a\s+(?P<companion>.+?)\s+hasta\s+(?P<destination>.+)$",
            tail,
            re.IGNORECASE,
        )
        if path_match is not None:
            for role, group in (
                (SemanticArgumentRole.SOURCE, "source"),
                (SemanticArgumentRole.PATH, "path"),
                (SemanticArgumentRole.DESTINATION, "destination"),
            ):
                argument = _make_argument(
                    role, path_match.group(group), text, existing_frame=frame
                )
                if argument is not None:
                    new_arguments.append(argument)
        elif companion_match is not None:
            companion = _make_argument(
                SemanticArgumentRole.COMPANION,
                companion_match.group("companion"),
                text,
                existing_frame=frame,
            )
            destination = _make_argument(
                SemanticArgumentRole.DESTINATION,
                companion_match.group("destination"),
                text,
                existing_frame=frame,
            )
            new_arguments.extend(
                argument for argument in (companion, destination) if argument is not None
            )
    elif selected_rule == "action_perception":
        marker = _INSTRUMENT_RE.search(tail)
        theme_text = tail[:marker.start()] if marker is not None else tail
        theme = _make_argument(
            SemanticArgumentRole.THEME,
            theme_text,
            text,
            existing_frame=frame,
        )
        instrument = (
            _make_argument(
                SemanticArgumentRole.INSTRUMENT,
                marker.group("instrument"),
                text,
                existing_frame=frame,
            )
            if marker is not None
            else None
        )
        if (
            instrument is not None
            and _guess_kind(
                instrument.mention.text,
                SemanticArgumentRole.PATIENT,
            )
            in {SemanticObjectKind.CHARACTER, SemanticObjectKind.CREATURE}
        ):
            instrument = None
        new_arguments.extend(
            argument for argument in (theme, instrument) if argument is not None
        )
    elif selected_rule == "action_transfer":
        recipient_match = re.match(
            r"^(?P<theme>.+?)\s+(?:a|al)\s+(?P<recipient>.+)$",
            tail,
            re.IGNORECASE,
        )
        destination_match = re.match(
            r"^(?P<theme>.+?)\s+(?P<marker>en|dentro\s+del?|"
            r"dentro\s+de\s+la|dentro\s+de\s+los|dentro\s+de\s+las)"
            r"\s+(?P<destination>.+)$",
            tail,
            re.IGNORECASE,
        )
        if recipient_match is not None:
            theme = _make_argument(
                SemanticArgumentRole.THEME,
                recipient_match.group("theme"),
                text,
                existing_frame=frame,
            )
            recipient = _make_argument(
                SemanticArgumentRole.RECIPIENT,
                recipient_match.group("recipient"),
                text,
                existing_frame=frame,
            )
            agent = _agent_argument(prefix, text, frame)
            new_arguments.extend(
                argument
                for argument in (agent, theme, recipient)
                if argument is not None
            )
        elif destination_match is not None:
            theme = _make_argument(
                SemanticArgumentRole.THEME,
                destination_match.group("theme"),
                text,
                existing_frame=frame,
            )
            marker = _fold(destination_match.group("marker"))
            target_role = (
                SemanticArgumentRole.CONTAINER
                if marker.startswith("dentro")
                else SemanticArgumentRole.DESTINATION
            )
            target = _make_argument(
                target_role,
                destination_match.group("destination"),
                text,
                existing_frame=frame,
            )
            agent = _agent_argument(prefix, text, frame)
            new_arguments.extend(
                argument for argument in (agent, theme, target) if argument is not None
            )
        else:
            theme = _make_argument(
                SemanticArgumentRole.THEME,
                tail,
                text,
                existing_frame=frame,
            )
            if theme is not None:
                new_arguments.append(theme)
    elif selected_rule == "action_hide_location":
        location_match = re.match(
            r"^(?P<theme>.+?)\s+(?:bajo|debajo\s+de|detrás\s+de|tras|"
            r"sobre)\s+(?P<location>.+)$",
            tail,
            re.IGNORECASE,
        )
        if location_match is not None:
            theme = _make_argument(
                SemanticArgumentRole.THEME,
                location_match.group("theme"),
                text,
                existing_frame=frame,
            )
            location = _make_argument(
                SemanticArgumentRole.LOCATION,
                location_match.group("location"),
                text,
                existing_frame=frame,
            )
            new_arguments.extend(
                argument for argument in (theme, location) if argument is not None
            )

    if new_arguments:
        # These templates describe a complete, unambiguous role pattern. Do not
        # retain conflicting model roles for the same surface construction.
        arguments = tuple(new_arguments)
    else:
        arguments = frame.arguments
    normalized_frame = SemanticActionFrame(
        predicate=frame.predicate,
        family=selected_family,
        arguments=arguments,
    )
    changed = normalized_frame != frame
    return normalized_frame, selected_rule if changed else None


def _relation_family_for_belongs_to(
    subject: str,
    object_: str,
) -> SemanticRelationFamily:
    object_tokens = set(re.findall(r"[^\W_]+", _normalize_kind_word(object_), re.UNICODE))
    if object_tokens & _ORGANIZATION_WORDS:
        return SemanticRelationFamily.MEMBERSHIP
    if _guess_kind(subject) is SemanticObjectKind.ITEM_INSTANCE:
        return SemanticRelationFamily.OWNERSHIP
    return SemanticRelationFamily.UNKNOWN


def _parse_relation_surface(text: str) -> _RelationSurface | None:
    """Recognize one explicit relation construction, abstaining on ambiguity."""
    original = text.strip()
    if not original or len(original) > 300:
        return None

    clause = original
    speaker: str | None = None
    temporal: str | None = None
    reported_match = _REPORTED_PREFIX_RE.match(clause)
    if reported_match is not None:
        speaker = _trim_surface(reported_match.group("speaker"))
        clause = reported_match.group("clause").strip()

    temporal_match = _TEMPORAL_PREFIX_RE.match(clause)
    if temporal_match is not None:
        temporal = _trim_surface(temporal_match.group("temporal"))
        clause = temporal_match.group("clause").strip()

    clause = _trim_surface(clause)
    if not clause:
        return None
    if re.match(r"^(?:si|quizá|quizas|tal\s+vez)\b", _fold(clause)):
        return None

    matches: list[_RelationSurface] = []
    for rule_id, pattern, family in _RELATION_PATTERNS:
        match = pattern.fullmatch(clause)
        if match is None:
            continue
        subject = _trim_surface(match.group("subject"))
        predicate = _trim_surface(match.group("predicate"))
        object_ = _trim_surface(match.group("object"))
        if not subject or not predicate or not object_:
            continue
        negative = bool(match.groupdict().get("negative"))
        if rule_id == "relation_belongs_to":
            family = _relation_family_for_belongs_to(subject, object_)
            if family is SemanticRelationFamily.UNKNOWN:
                # A person belonging to another person may express allegiance,
                # service or another relation. Do not overwrite the model's
                # interpretation with an unsupported ownership guess.
                continue
        matches.append(
            _RelationSurface(
                rule_id=rule_id,
                subject=subject,
                predicate=predicate,
                object=object_,
                family=family,
                negative=negative,
                attributed_to=speaker,
                temporal_expression=temporal,
            )
        )

    if len(matches) != 1:
        return None
    result = matches[0]
    # A second relational predicate in the captured complement makes the
    # surface construction compound; let the LLM handle it rather than slicing
    # an incomplete relation into a single claim.
    if re.search(
        r"\b(?:pertenec\w*|trabaj\w*|proteg\w*|odi\w*|detest\w*|"
        r"jur\w*\s+lealtad|form\w*\s+parte|pose\w*|tien\w*|"
        r"es\s+(?:herman[oa]|madre|padre|hij[oa]|prim[oa]|t[ií][oa])|"
        r"sirv\w*|conoc\w*|está|esta)\b",
        result.object,
        re.IGNORECASE,
    ):
        return None
    return result


def _make_relation_claim(
    step: IntentStep,
    surface: _RelationSurface,
) -> SemanticRelationClaim | None:
    source = step.source_excerpt
    literal_values = (
        surface.subject,
        surface.predicate,
        surface.object,
        surface.attributed_to,
        surface.temporal_expression,
    )
    if any(
        value is not None and not _is_literal(source, value)
        for value in literal_values
    ):
        return None
    if surface.negative or step.polarity.value == "negative":
        polarity = SemanticPolarity.NEGATIVE
    elif step.polarity.value == "uncertain":
        polarity = SemanticPolarity.UNCERTAIN
    else:
        polarity = SemanticPolarity.POSITIVE

    if surface.attributed_to is not None:
        modality = SemanticModality.REPORTED
    elif "?" in source or "¿" in source:
        modality = SemanticModality.QUESTION
    elif polarity is SemanticPolarity.NEGATIVE:
        modality = SemanticModality.NEGATED
    else:
        modality = SemanticModality(step.modality.value)
    attributed_to = (
        SemanticMention(
            surface.attributed_to,
            _guess_kind(surface.attributed_to, SemanticArgumentRole.AGENT),
        )
        if surface.attributed_to is not None
        else None
    )
    try:
        return SemanticRelationClaim(
            step_index=step.index,
            subject=SemanticMention(
                surface.subject,
                _guess_kind(surface.subject, SemanticArgumentRole.AGENT),
            ),
            predicate=surface.predicate,
            object=SemanticMention(
                surface.object,
                _guess_kind(surface.object, SemanticArgumentRole.PATIENT),
            ),
            relation_family=surface.family,
            polarity=polarity,
            modality=modality,
            source_excerpt=source,
            attributed_to=attributed_to,
            temporal_expression=surface.temporal_expression,
        )
    except (TypeError, ValueError):
        return None


def normalize_untrusted_intent_payload(
    payload: Any,
    *,
    player_input: str,
    evidence_text: str,
) -> tuple[Any, SurfaceNormalizationSummary]:
    """Drop only optional semantic mentions that are not literal step evidence.

    Required structures and predicates remain strict: malformed payloads still
    fail the normal domain validator. A single-step relation excerpt may be
    widened to the complete literal utterance when a supported relation
    construction requires its reported attribution or temporal prefix.
    """
    if not isinstance(payload, dict):
        return payload, SurfaceNormalizationSummary()

    normalized = dict(payload)
    raw_steps = normalized.get("steps")
    if not isinstance(raw_steps, list):
        return payload, SurfaceNormalizationSummary()

    widened = 0
    steps = [dict(step) if isinstance(step, dict) else step for step in raw_steps]
    if len(steps) == 1 and isinstance(steps[0], dict):
        step = steps[0]
        excerpt = step.get("source_excerpt")
        if (
            isinstance(excerpt, str)
            and _is_literal(player_input, excerpt)
            and len(player_input.strip()) <= 300
            and _parse_relation_surface(player_input.strip()) is not None
        ):
            full_input = player_input.strip()
            if full_input != excerpt:
                step["source_excerpt"] = full_input
                widened = 1

    dropped_targets = 0
    dropped_arguments = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        excerpt = step.get("source_excerpt")
        if not isinstance(excerpt, str):
            continue
        targets = step.get("target_mentions")
        if isinstance(targets, list):
            kept_targets = [
                value
                for value in targets
                if isinstance(value, str)
                and _is_literal(evidence_text, value)
                and _is_literal(excerpt, value)
            ]
            dropped_targets += len(targets) - len(kept_targets)
            step["target_mentions"] = kept_targets

        frame = step.get("action_frame")
        if isinstance(frame, dict):
            arguments = frame.get("arguments")
            if isinstance(arguments, list):
                kept_arguments = []
                for argument in arguments:
                    if (
                        isinstance(argument, dict)
                        and isinstance(argument.get("mention"), dict)
                        and isinstance(argument["mention"].get("text"), str)
                    ):
                        mention = argument["mention"]["text"]
                        if not (
                            _is_literal(evidence_text, mention)
                            and _is_literal(excerpt, mention)
                        ):
                            dropped_arguments += 1
                            continue
                    kept_arguments.append(argument)
                frame_copy = dict(frame)
                frame_copy["arguments"] = kept_arguments
                step["action_frame"] = frame_copy

    normalized["steps"] = steps
    dropped_relations = 0
    claims = normalized.get("relation_claims")
    if isinstance(claims, list):
        kept_claims: list[Any] = []
        for claim in claims:
            if not isinstance(claim, dict):
                kept_claims.append(claim)
                continue
            step_index = claim.get("step_index")
            if (
                isinstance(step_index, bool)
                or not isinstance(step_index, int)
                or not 0 <= step_index < len(steps)
                or not isinstance(steps[step_index], dict)
            ):
                kept_claims.append(claim)
                continue
            excerpt = steps[step_index].get("source_excerpt")
            if not isinstance(excerpt, str):
                kept_claims.append(claim)
                continue
            values: list[Any] = [
                claim.get("predicate"),
                claim.get("source_excerpt"),
            ]
            for endpoint in ("subject", "object", "attributed_to"):
                mention = claim.get(endpoint)
                if isinstance(mention, dict):
                    values.append(mention.get("text"))
            values.append(claim.get("temporal_expression"))
            if any(
                isinstance(value, str)
                and value
                and not (
                    _is_literal(evidence_text, value)
                    and _is_literal(excerpt, value)
                )
                for value in values
            ):
                dropped_relations += 1
                continue
            kept_claims.append(claim)
        normalized["relation_claims"] = kept_claims

    return normalized, SurfaceNormalizationSummary(
        dropped_ungrounded_target_mentions=dropped_targets,
        dropped_ungrounded_action_arguments=dropped_arguments,
        dropped_ungrounded_relation_claims=dropped_relations,
        widened_relation_evidence_spans=widened,
    )


def normalize_semantic_surface(
    analysis: PlayerIntentAnalysis,
) -> tuple[PlayerIntentAnalysis, SurfaceNormalizationSummary]:
    """Apply only deterministic, evidence-local semantic rules to v2 analyses."""
    if analysis.schema_version != 2:
        return analysis, SurfaceNormalizationSummary()

    normalized_steps: list[IntentStep] = []
    action_rules: list[str] = []
    speech_only = analysis.category.value in {"dialogue", "question"}
    for step in analysis.steps:
        frame, rule_id = _normalize_action_frame(step, speech_only=speech_only)
        normalized_steps.append(
            step if frame is step.action_frame else replace(step, action_frame=frame)
        )
        if rule_id is not None:
            action_rules.append(rule_id)

    candidate_claims: list[SemanticRelationClaim] = []
    relation_rules: list[str] = []
    for step in normalized_steps:
        surface = _parse_relation_surface(step.source_excerpt)
        if surface is None:
            continue
        claim = _make_relation_claim(step, surface)
        if claim is None:
            continue
        candidate_claims.append(claim)
        relation_rules.append(surface.rule_id)

    claims = list(analysis.relation_claims)
    for candidate in candidate_claims:
        # A uniquely recognized relation in this step supersedes model claims
        # for that step. Claims from other steps remain untouched.
        claims = [claim for claim in claims if claim.step_index != candidate.step_index]
        if len(claims) < MAX_RELATION_CLAIMS:
            claims.append(candidate)

    normalized_analysis = replace(
        analysis,
        steps=tuple(normalized_steps),
        relation_claims=tuple(claims),
    )
    return normalized_analysis, SurfaceNormalizationSummary(
        action_rules_applied=tuple(action_rules),
        relation_rules_applied=tuple(relation_rules),
    )
