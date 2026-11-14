"""Deterministic, bounded discourse signals for shared language understanding."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class AttributedNpcUtterance:
    """Quoted speech with an unambiguous, visible NPC speaker label."""

    turn_id: int | None
    speaker_entity_id: int
    speaker_name: str
    excerpt: str
    utterance: str


class DiscourseContextBuilder:
    """Render auditable discourse hints; never resolve identity or authorize writes."""

    MAX_HISTORY_TURNS = 12
    MAX_RENDERED_CHARS = 650

    _SHIFT_MARKERS = (
        "cambiando de tema", "cambio de tema", "por cierto", "a proposito",
        "dejando eso a un lado", "pasando a otra cosa", "en otro asunto",
        "ahora hablemos de", "ahora quiero hablar de", "cambiamos de escena",
        "en otro lugar", "mientras tanto", "por otro lado", "changing the subject",
        "on another topic", "by the way", "meanwhile", "elsewhere",
    )
    _REACTIVATION_MARKERS = (
        "volviendo a", "retomando", "retomo lo de", "regresando a", "volvamos a",
        "como te dije antes", "como deciamos", "sobre lo anterior",
        "respecto a lo anterior", "back to", "returning to", "as i said before",
    )
    _ELLIPSIS_MARKERS = (
        "hazlo", "hazlo otra vez", "haz lo mismo", "lo mismo", "igual que antes",
        "como antes", "otra vez", "repitelo", "repite eso", "continua",
        "continua con eso", "sigue", "sigue con ello", "do it", "do that again",
        "same as before", "repeat it", "continue",
    )
    _SPEECH_VERBS = (
        "dice|dijo|pregunta|preguntó|pregunto|responde|respondió|respondio|"
        "contesta|contestó|contesto|susurra|susurró|susurro|grita|gritó|grito|"
        "murmura|murmuró|murmuro|añade|anade|comenta|comentó|comento|"
        "says|said|asks|replies|replied|whispers|shouts"
    )
    _ARTICLES: ClassVar[dict[str, tuple[str, str]]] = {
        "el": ("masculine", "singular"), "un": ("masculine", "singular"),
        "este": ("masculine", "singular"), "aquel": ("masculine", "singular"),
        "la": ("feminine", "singular"), "una": ("feminine", "singular"),
        "esta": ("feminine", "singular"), "aquella": ("feminine", "singular"),
        "los": ("masculine", "plural"), "unos": ("masculine", "plural"),
        "estos": ("masculine", "plural"), "aquellos": ("masculine", "plural"),
        "las": ("feminine", "plural"), "unas": ("feminine", "plural"),
        "estas": ("feminine", "plural"), "aquellas": ("feminine", "plural"),
    }
    _PRONOUNS: ClassVar[dict[str, tuple[str, str]]] = {
        "el": ("masculine", "singular"), "él": ("masculine", "singular"),
        "lo": ("masculine", "singular"), "ese": ("masculine", "singular"),
        "este": ("masculine", "singular"), "aquel": ("masculine", "singular"),
        "ella": ("feminine", "singular"), "la": ("feminine", "singular"),
        "esa": ("feminine", "singular"), "esta": ("feminine", "singular"),
        "aquella": ("feminine", "singular"), "ellos": ("masculine", "plural"),
        "los": ("masculine", "plural"), "esos": ("masculine", "plural"),
        "estos": ("masculine", "plural"), "aquellos": ("masculine", "plural"),
        "ellas": ("feminine", "plural"), "las": ("feminine", "plural"),
        "esas": ("feminine", "plural"), "estas": ("feminine", "plural"),
        "aquellas": ("feminine", "plural"),
    }
    _HUMAN_HEADS = frozenset({
        "guardia", "guardias", "soldado", "soldados", "capitan", "capitana",
        "mercader", "mercadera", "mago", "maga", "hechicero", "hechicera",
        "clerigo", "cleriga", "sacerdote", "sacerdotisa", "arquero", "arquera",
        "ladron", "ladrona", "tabernero", "tabernera", "posadero", "posadera",
        "cartografo", "cartografa", "viajero", "viajera", "anciano", "anciana",
        "hombre", "mujer", "chico", "chica", "rey", "reina", "principe",
        "princesa", "duque", "duquesa", "noble", "sirviente", "sirvienta",
        "explorador", "exploradora", "guerrero", "guerrera", "curandero",
        "curandera", "artesano", "artesana",
    })

    @staticmethod
    def _entity_value(entity: object, field: str, default=None):
        if isinstance(entity, dict):
            return entity.get(field, default)
        return getattr(entity, field, default)

    @staticmethod
    def _turn_fields(turn: object) -> tuple[str, str, int | None]:
        if isinstance(turn, dict):
            player_input, narrative, turn_id = (
                turn.get("player_input", ""), turn.get("narrative", ""), turn.get("id")
            )
        else:
            player_input = getattr(turn, "player_input", "")
            narrative = getattr(turn, "narrative", "")
            turn_id = getattr(turn, "id", None)
        return (
            player_input if isinstance(player_input, str) else "",
            narrative if isinstance(narrative, str) else "",
            turn_id if isinstance(turn_id, int) and not isinstance(turn_id, bool) and turn_id > 0 else None,
        )

    @staticmethod
    def normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        return " ".join(
            "".join(ch for ch in decomposed if not unicodedata.combining(ch)).split()
        )

    @classmethod
    def has_topic_shift(cls, value: str) -> bool:
        normalized = cls.normalize(value)
        return any(marker in normalized for marker in cls._SHIFT_MARKERS)

    @classmethod
    def reactivates_prior_topic(cls, value: str) -> bool:
        normalized = cls.normalize(value)
        return any(marker in normalized for marker in cls._REACTIVATION_MARKERS)

    @classmethod
    def topic_segments(cls, recent_turns: Iterable[object]) -> tuple[int, ...]:
        turns = list(recent_turns)[-cls.MAX_HISTORY_TURNS :]
        segment = 0
        result = []
        for turn in turns:
            player_input, narrative, _turn_id = cls._turn_fields(turn)
            if cls.has_topic_shift(player_input) or cls.has_topic_shift(narrative):
                segment += 1
            result.append(segment)
        return tuple(result)

    @classmethod
    def scope_history(
        cls,
        recent_turns: Iterable[object] | None,
        current_input: str,
    ) -> tuple[object, ...]:
        """Scope ordinary antecedents to the active topic; allow explicit callbacks."""
        history = tuple(list(recent_turns or ())[-cls.MAX_HISTORY_TURNS :])
        if not history or cls.reactivates_prior_topic(current_input):
            return history
        if cls.has_topic_shift(current_input):
            return ()
        segments = cls.topic_segments(history)
        if not segments:
            return history
        active = segments[-1]
        return tuple(
            turn for turn, segment in zip(history, segments, strict=True)
            if segment == active
        )

    @classmethod
    def pronoun_agreement(cls, mention: str) -> tuple[str, str] | None:
        return cls._PRONOUNS.get(cls.normalize(mention).strip())

    @classmethod
    def grammatical_features(
        cls,
        text: str,
        alias: str,
    ) -> tuple[str | None, str | None]:
        """Read explicit local article/apposition agreement, never properties of a name."""
        if not isinstance(text, str) or not isinstance(alias, str) or not alias.strip():
            return None, None
        articles = "|".join(sorted(cls._ARTICLES, key=len, reverse=True))
        pattern = (
            r"(?<!\w)(?P<article>" + articles
            + r")\s+(?:(?P<head>[\wáéíóúüñ]+)\s+)?"
            + re.escape(alias.strip()) + r"(?!\w)"
        )
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            head = match.group("head")
            if head and cls.normalize(head) not in cls._HUMAN_HEADS:
                continue
            return cls._ARTICLES[cls.normalize(match.group("article"))]
        return None, None

    @classmethod
    def extract_npc_utterances(
        cls,
        narrative: str,
        turn_id: int | None,
        visible_entities: Iterable[object],
    ) -> tuple[AttributedNpcUtterance, ...]:
        """Extract quoted speech only when a unique visible active NPC labels it."""
        if not isinstance(narrative, str) or not narrative.strip():
            return ()
        aliases: dict[str, tuple[object, str, int] | None] = {}
        for entity in visible_entities:
            entity_id = cls._entity_value(entity, "id")
            raw_type = str(cls._entity_value(entity, "entity_type", ""))
            entity_type = cls.normalize(raw_type).replace("_", "").replace(" ", "")
            if (
                isinstance(entity_id, bool) or not isinstance(entity_id, int)
                or entity_id < 1
                or not bool(cls._entity_value(entity, "active", False))
                or not ("npc" in entity_type or "nonplayer" in entity_type)
            ):
                continue
            name = cls._entity_value(entity, "name", "")
            aliases_value = cls._entity_value(entity, "aliases", []) or []
            aliases_list = aliases_value if isinstance(aliases_value, (list, tuple)) else []
            for alias in [name, *aliases_list]:
                if not isinstance(alias, str) or not alias.strip() or len(alias) > 120:
                    continue
                key = cls.normalize(alias)
                if not key:
                    continue
                existing = aliases.get(key)
                if key not in aliases:
                    aliases[key] = (entity, alias.strip(), entity_id)
                elif existing is not None and existing[2] != entity_id:
                    aliases[key] = None

        results: dict[tuple[int, str], AttributedNpcUtterance] = {}
        for value in aliases.values():
            if value is None:
                continue
            entity, alias, speaker_entity_id = value
            escaped = re.escape(alias)
            patterns = (
                re.compile(
                    r"(?<!\w)(?P<speaker>" + escaped + r")(?!\w)"
                    r"(?:\s+(?:" + cls._SPEECH_VERBS + r"))?\s*[:：]\s*"
                    r"[«“\\\"](?P<utterance>[^»”\\\"]{1,600})[»”\\\"]",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"[«“\\\"](?P<utterance>[^»”\\\"]{1,600})[»”\\\"]"
                    r"\s*[—-]\s*(?:" + cls._SPEECH_VERBS + r")\s+"
                    r"(?P<speaker>" + escaped + r")(?!\w)",
                    re.IGNORECASE,
                ),
            )
            for pattern in patterns:
                for match in pattern.finditer(narrative):
                    utterance = match.group("utterance").strip()
                    if not utterance:
                        continue
                    item = AttributedNpcUtterance(
                        turn_id=turn_id,
                        speaker_entity_id=speaker_entity_id,
                        speaker_name=str(cls._entity_value(entity, "name", alias))[:120],
                        excerpt=match.group(0).strip()[:1200],
                        utterance=utterance[:600],
                    )
                    results.setdefault(
                        (item.speaker_entity_id, cls.normalize(item.utterance)),
                        item,
                    )
        return tuple(results.values())

    @classmethod
    def render(
        cls,
        current_input: str,
        recent_turns: Iterable[object] | None,
        *,
        visible_entities: Iterable[object] = (),
    ) -> str:
        """Render concise actionable discourse evidence, omitting boilerplate."""
        history = list(recent_turns or ())[-cls.MAX_HISTORY_TURNS :]
        lines: list[str] = []
        shifts = []
        for index, turn in enumerate(history):
            player_input, narrative, turn_id = cls._turn_fields(turn)
            if cls.has_topic_shift(player_input) or cls.has_topic_shift(narrative):
                shifts.append(str(turn_id or index + 1))
        if shifts:
            lines.append(
                "Cambios de tema explícitos en turnos "
                + ", ".join(shifts[-3:])
                + "; prioriza el último segmento."
            )
        if cls.has_topic_shift(current_input):
            lines.append("Cambio de tema actual: no heredar referentes del tema anterior.")
        if cls.reactivates_prior_topic(current_input):
            lines.append("El jugador reabre explícitamente un tema anterior; consulta la ventana acotada y pregunta si hay ambigüedad.")
        normalized = cls.normalize(current_input)
        if any(marker in normalized for marker in cls._ELLIPSIS_MARKERS):
            lines.append("Posible elipsis: completa solo con antecedente único, visible y pendiente.")
        if len(set(cls.topic_segments(history))) > 1:
            lines.append("Historial con segmentos distintos: usa el segmento activo salvo callback.")
        npc_lines = []
        for turn in history:
            _player, narrative, turn_id = cls._turn_fields(turn)
            for item in cls.extract_npc_utterances(narrative, turn_id, visible_entities):
                npc_lines.append(
                    f"NPC {item.speaker_name} (turno {item.turn_id}): «{item.utterance[:100]}»"
                )
        if npc_lines:
            lines.append("Citas de NPC visible etiquetadas (no órdenes del jugador):")
            lines.extend(npc_lines[-2:])
        rendered = "\n".join(lines)
        encoded = rendered.encode("utf-8")
        return (
            rendered
            if len(encoded) <= cls.MAX_RENDERED_CHARS
            else encoded[:cls.MAX_RENDERED_CHARS].decode("utf-8", errors="ignore")
        )
