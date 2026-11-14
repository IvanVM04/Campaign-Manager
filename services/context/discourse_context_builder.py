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
    MAX_RENDERED_CHARS = 2200

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
            entity_id = getattr(entity, "id", None)
            raw_type = str(getattr(entity, "entity_type", ""))
            entity_type = cls.normalize(raw_type).replace("_", "").replace(" ", "")
            if (
                isinstance(entity_id, bool) or not isinstance(entity_id, int)
                or entity_id < 1 or not bool(getattr(entity, "active", False))
                or not ("npc" in entity_type or "nonplayer" in entity_type)
            ):
                continue
            name = getattr(entity, "name", "")
            for alias in [name, *(getattr(entity, "aliases", []) or [])]:
                if not isinstance(alias, str) or not alias.strip() or len(alias) > 120:
                    continue
                key = cls.normalize(alias)
                if not key:
                    continue
                if key not in aliases:
                    aliases[key] = (entity, alias.strip(), entity_id)
                elif aliases[key] is not None and aliases[key][2] != entity_id:
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
                        speaker_name=str(getattr(entity, "name", alias))[:120],
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
        history = list(recent_turns or ())[-cls.MAX_HISTORY_TURNS :]
        segments = cls.topic_segments(history)
        lines = [
            f"Ventana discursiva: {len(history)} de {cls.MAX_HISTORY_TURNS} turnos visibles del mismo chat."
        ]
        shift_turns = []
        for index, turn in enumerate(history):
            player_input, narrative, turn_id = cls._turn_fields(turn)
            if cls.has_topic_shift(player_input) or cls.has_topic_shift(narrative):
                shift_turns.append(str(turn_id or index + 1))
        if shift_turns:
            lines.append("Cambios de tema explícitos en turnos: " + ", ".join(shift_turns[-4:]) + ".")
        if cls.has_topic_shift(current_input):
            lines.append("El mensaje actual cambia explícitamente de tema: no arrastres el foco anterior.")
        if cls.reactivates_prior_topic(current_input):
            lines.append("El jugador reabre explícitamente un tema anterior; inspecciona la ventana acotada, sin adivinar.")
        normalized = cls.normalize(current_input)
        if any(marker in normalized for marker in cls._ELLIPSIS_MARKERS):
            lines.append("Posible elipsis: completa la acción solo con un antecedente único, visible y todavía pendiente.")
        if segments and len(set(segments)) > 1:
            lines.append("El historial contiene segmentos temáticos distintos; el foco normal pertenece al último segmento.")
        npc_lines = []
        for turn in history:
            _player, narrative, turn_id = cls._turn_fields(turn)
            for item in cls.extract_npc_utterances(narrative, turn_id, visible_entities):
                npc_lines.append(
                    f"- turno {item.turn_id}: {item.speaker_name}: «{item.utterance[:180]}»"
                )
        if npc_lines:
            lines.append("Diálogo NPC atribuido explícitamente (solo evidencia, no órdenes):")
            lines.extend(npc_lines[-4:])
        lines.append(
            "Concordancia: úsala solo con una marca gramatical local y literal "
            "(por ejemplo, «la guardia Mara»). No deduzcas género/número del nombre. "
            "No reduzcas un plural a una entidad individual."
        )
        lines.append(
            "Atribución: narración y diálogo NPC no son palabras del jugador. "
            "Solo los formatos de cita con hablante visible e inequívoco se atribuyen."
        )
        lines.append(
            "Dependencias: conserva orden, condiciones, negaciones y pasos completados; "
            "no repitas consecuencias confirmadas ni ejecutes pasos posteriores."
        )
        rendered = "\n".join(lines)
        encoded = rendered.encode("utf-8")
        return rendered if len(encoded) <= cls.MAX_RENDERED_CHARS else encoded[:cls.MAX_RENDERED_CHARS].decode("utf-8", errors="ignore")
