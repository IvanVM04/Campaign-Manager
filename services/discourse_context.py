"""Deterministic, bounded discourse signals for shared language understanding."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar, TypeVar

DiscourseTurn = TypeVar("DiscourseTurn")


@dataclass(frozen=True, slots=True)
class AttributedNpcUtterance:
    """Quoted speech with an unambiguous, visible NPC speaker label."""

    turn_id: int | None
    speaker_entity_id: int
    speaker_name: str
    excerpt: str
    utterance: str


@dataclass(frozen=True, slots=True)
class DiscourseSelection[TurnT]:
    """Auditable result of topic-scoping, including ambiguous selections."""

    turns: tuple[TurnT, ...]
    reason: str
    anchor_tokens: tuple[str, ...] = ()
    selected_segments: tuple[int, ...] = ()
    ambiguous: bool = False
    candidate_scores: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class SurfacePronounMention:
    """Literal current-utterance pronoun span without canonical identity."""

    text: str
    start: int
    end: int
    gender: str
    number: str


@dataclass(frozen=True, slots=True)
class SpeechPredicateSignal:
    """Explicit unquoted third-person subject + speech-predicate surface signal."""

    subject: str
    predicate: str
    subject_start: int
    subject_end: int
    predicate_start: int
    predicate_end: int
    gender: str
    number: str
    subject_kind: str = "pronoun"


class DiscourseContextBuilder:
    """Render auditable discourse hints; never resolve identity or authorize writes."""

    MAX_HISTORY_TURNS = 12
    MAX_RENDERED_CHARS = 1200

    _SHIFT_MARKERS = (
        "cambiando de tema", "cambio de tema", "por cierto", "a proposito",
        "dejando eso a un lado", "pasando a otra cosa", "en otro asunto",
        "ahora hablemos del", "ahora quiero hablar del",
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
        "dice|dicen|dijo|dijeron|decia|decía|decian|decían|"
        "pregunta|preguntan|preguntó|preguntaron|pregunto|preguntaba|"
        "responde|responden|respondió|respondieron|respondia|respondían|"
        "contesta|contestan|contestó|contestaron|contestaba|contestaban|"
        "habla|hablan|habló|hablaron|hablaba|hablaban|"
        "susurra|susurran|susurró|susurraron|grita|gritan|gritó|gritaron|"
        "murmura|murmuran|murmuró|murmuraron|añade|añaden|añadió|añadieron|"
        "comenta|comentan|comentó|comentaron|avisa|avisan|avisó|avisaron|"
        "says|say|said|asks|ask|replies|reply|replied|whispers|whisper|shouts|shout|tells|tell|told"
    )
    _CALLBACK_STOPWORDS = frozenset({
        "a", "al", "algo", "antes", "anterior", "anteriores", "as", "asunto",
        "ahora", "back", "bien", "by", "como", "con", "conversation",
        "conversacion", "continuar", "de", "del", "dijiste", "el", "ella",
        "ellas", "ello", "ellos", "en", "esa", "ese", "eso", "esta", "este",
        "esto", "for", "from", "hablar", "hablo", "i", "la", "las", "le",
        "les", "lo", "los", "me", "mi", "mis", "no", "of", "on", "over",
        "para", "paso", "pasos", "por", "preguntar", "pregunto", "que",
        "quien", "returning", "retomando", "retomo", "regresando", "volviendo",
        "volvamos", "sobre", "tema", "the", "to", "what", "when", "with",
        "you", "quiero", "responde", "responden", "contesta", "contestan",
        "pregunta", "preguntan", "sucedio", "ocurrio",
    })
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

    @staticmethod
    def _without_quoted_spans(value: str) -> str:
        """Remove quoted text before detecting discourse-control markers.

        A phrase mentioned as dialogue is evidence about what someone said,
        not an instruction to change the current topic or repeat an action.
        """
        return re.sub(
            r"«[^»]*»|“[^”]*”|\"[^\"]*\"|'[^']*'",
            " ",
            value,
        )

    @staticmethod
    def _mask_quoted_spans(value: str) -> str:
        """Mask quoted text without changing offsets in the source utterance."""
        return re.sub(
            r"«[^»]*»|“[^”]*”|\"[^\"]*\"|'[^']*'",
            lambda match: " " * len(match.group(0)),
            value,
        )

    @classmethod
    def surface_pronoun_mentions(cls, value: str) -> tuple[SurfacePronounMention, ...]:
        """Extract literal subject pronouns and narrowly recognized dative clitics."""
        if not isinstance(value, str) or not value:
            return ()
        masked = cls._mask_quoted_spans(value)
        subject_pattern = re.compile(
            r"(?<!\w)(?P<pronoun>ellas|ellos|ella|él|she|he|they)(?!\w)",
            re.IGNORECASE,
        )
        # "le" is also a feminine article and "les" has other uses. Treat
        # them as clitics only when immediately followed by a known finite
        # verb form; never classify "la puerta" as an object reference.
        clitic_verbs = (
            "pregunto|pregunta|pregunté|preguntó|preguntan|preguntaba|preguntaron|"
            "digo|dice|dijo|dije|dicen|decía|"
            "respondo|responde|respondió|respondí|responden|"
            "contesto|contesta|contestó|contesté|contestan|"
            "entrego|entrega|entregó|entregué|entregan|"
            "ofrezco|ofrece|ofreció|ofrecí|pido|pide|pidió|pedí|"
            "aviso|avisa|avisó|avisé|muestro|muestra|mostró|mostré|"
            "doy|da|dio|di|llamo|llama|llamó|llamé|"
            "saludo|saluda|saludó|saludé|explico|explica|explicó|expliqué|"
            "cuento|cuenta|contó|conté|escribo|escribe|escribió|escribí"
        )
        clitic_pattern = re.compile(
            r"(?<!\w)(?P<pronoun>les|le)\s+"
            r"(?P<verb>" + clitic_verbs + r")(?!\w)",
            re.IGNORECASE,
        )
        found: list[SurfacePronounMention] = []
        seen_spans: set[tuple[int, int]] = set()
        for pattern in (subject_pattern, clitic_pattern):
            for match in pattern.finditer(masked):
                start = match.start("pronoun")
                end = match.end("pronoun")
                if (start, end) in seen_spans:
                    continue
                text = value[start:end]
                features = cls.pronoun_agreement(text)
                if features is None:
                    continue
                seen_spans.add((start, end))
                found.append(
                    SurfacePronounMention(
                        text=text,
                        start=start,
                        end=end,
                        gender=features[0],
                        number=features[1],
                    )
                )
        found.sort(key=lambda item: item.start)
        return tuple(found)

    @classmethod
    def speech_predicate_signals(
        cls,
        value: str,
        *,
        visible_entities: Iterable[object] = (),
    ) -> tuple[SpeechPredicateSignal, ...]:
        """Detect literal speech cues with a pronoun or unique visible NPC subject.

        A named subject is eligible only when its exact alias belongs to one
        active visible NPC. Quoted spans and ambiguous aliases are ignored.
        """
        if not isinstance(value, str) or not value:
            return ()
        masked = cls._mask_quoted_spans(value)
        verbs = sorted(cls._SPEECH_VERBS.split("|"), key=len, reverse=True)
        verb_pattern = "|".join(re.escape(item) for item in verbs)
        signals: list[SpeechPredicateSignal] = []
        pronoun_pattern = re.compile(
            r"(?<!\w)(?P<subject>ellas|ellos|ella|él|she|he|they)\s+"
            r"(?P<predicate>" + verb_pattern + r")(?!\w)",
            re.IGNORECASE,
        )
        pronoun_spans: set[tuple[int, int]] = set()
        for match in pronoun_pattern.finditer(masked):
            subject = value[match.start("subject"):match.end("subject")]
            predicate = value[match.start("predicate"):match.end("predicate")]
            features = cls.pronoun_agreement(subject)
            if features is None:
                continue
            pronoun_spans.add((match.start("subject"), match.end("subject")))
            signals.append(
                SpeechPredicateSignal(
                    subject=subject,
                    predicate=predicate,
                    subject_start=match.start("subject"),
                    subject_end=match.end("subject"),
                    predicate_start=match.start("predicate"),
                    predicate_end=match.end("predicate"),
                    gender=features[0],
                    number=features[1],
                    subject_kind="pronoun",
                )
            )

        unique_aliases: dict[str, tuple[object, str] | None] = {}
        for identity, _name, aliases in cls._visible_npc_specs(visible_entities):
            for alias in aliases:
                key = cls.normalize(alias)
                if not key:
                    continue
                existing = unique_aliases.get(key)
                if key not in unique_aliases:
                    unique_aliases[key] = (identity, alias)
                elif existing is not None and existing[0] != identity:
                    unique_aliases[key] = None

        for entry in unique_aliases.values():
            if entry is None:
                continue
            _identity, alias = entry
            alias_pattern = re.escape(alias).replace(r"\ ", r"\s+")
            named_pattern = re.compile(
                r"(?<!\w)(?P<subject>" + alias_pattern + r")(?!\w)\s+"
                r"(?P<predicate>" + verb_pattern + r")(?!\w)",
                re.IGNORECASE,
            )
            for match in named_pattern.finditer(masked):
                span = (match.start("subject"), match.end("subject"))
                if any(span[0] < end and start < span[1] for start, end in pronoun_spans):
                    continue
                signals.append(
                    SpeechPredicateSignal(
                        subject=value[span[0]:span[1]],
                        predicate=value[match.start("predicate"):match.end("predicate")],
                        subject_start=span[0],
                        subject_end=span[1],
                        predicate_start=match.start("predicate"),
                        predicate_end=match.end("predicate"),
                        gender="unknown",
                        number="unknown",
                        subject_kind="visible_npc",
                    )
                )
        signals.sort(key=lambda item: (item.subject_start, item.predicate_start))
        return tuple(signals)

    @classmethod
    def _contains_unquoted_marker(
        cls,
        value: str,
        markers: tuple[str, ...],
    ) -> bool:
        normalized = cls.normalize(cls._without_quoted_spans(value))
        for marker in markers:
            marker_pattern = re.escape(cls.normalize(marker)).replace(r"\ ", r"\s+")
            if re.search(
                r"(?<!\w)" + marker_pattern + r"(?!\w)",
                normalized,
            ):
                return True
        return False

    @classmethod
    def has_topic_shift(cls, value: str) -> bool:
        normalized = cls.normalize(cls._without_quoted_spans(value))
        for marker in cls._SHIFT_MARKERS:
            marker_pattern = re.escape(cls.normalize(marker)).replace(r"\ ", r"\s+")
            if re.search(
                r"(?:^|[.!?;,:]\s*)" + marker_pattern + r"(?=$|[\s,:.!?;])",
                normalized,
            ):
                return True
        return False

    @classmethod
    def reactivates_prior_topic(cls, value: str) -> bool:
        return cls._contains_unquoted_marker(value, cls._REACTIVATION_MARKERS)

    @classmethod
    def _content_tokens(cls, value: str) -> frozenset[str]:
        """Return meaningful normalized words for matching an explicit callback anchor."""
        normalized = cls.normalize(value)
        return frozenset(
            token for token in re.findall(r"[a-z0-9]+", normalized)
            if len(token) > 2 and token not in cls._CALLBACK_STOPWORDS
        )

    @classmethod
    def _callback_anchor_sequence(cls, value: str) -> tuple[str, ...]:
        """Extract unique callback anchors in the order used by the player."""
        normalized = cls.normalize(cls._without_quoted_spans(value))
        for marker in sorted(cls._REACTIVATION_MARKERS, key=len, reverse=True):
            pattern = re.escape(cls.normalize(marker)).replace(r"\ ", r"\s+")
            match = re.search(r"(?<!\w)" + pattern + r"(?!\w)", normalized)
            if match is None:
                continue
            tail = normalized[match.end():]
            # Keep the callback anchor in its introductory clause. The
            # action/question after a comma must not steer retrieval toward
            # another historical segment.
            anchor_clause = re.split(r"[,;.!?]", tail, maxsplit=1)[0]
            anchor_source = (
                anchor_clause if cls._content_tokens(anchor_clause) else tail
            )
            content_tokens = cls._content_tokens(anchor_source)
            ordered: list[str] = []
            seen: set[str] = set()
            for token in re.findall(r"[a-z0-9]+", anchor_source):
                if token in content_tokens and token not in seen:
                    ordered.append(token)
                    seen.add(token)
            return tuple(ordered)
        return ()

    @classmethod
    def _callback_anchor_tokens(cls, value: str) -> frozenset[str]:
        """Set view used for overlap scoring; metadata keeps source order."""
        return frozenset(cls._callback_anchor_sequence(value))

    @classmethod
    def _subject_pronoun(cls, value: str) -> str | None:
        """Find a third-person subject pronoun without reading quoted dialogue."""
        match = re.search(
            r"(?<!\w)(?P<pronoun>ellas|ellos|ella|él)\s+[a-záéíóúüñ]+",
            cls._without_quoted_spans(value),
            flags=re.IGNORECASE,
        )
        return match.group("pronoun") if match is not None else None

    @classmethod
    def _visible_npc_specs(
        cls, visible_entities: Iterable[object],
    ) -> tuple[tuple[object, str, tuple[str, ...]], ...]:
        """Return active visible NPC labels without inferring identity from names."""
        result = []
        seen: set[object] = set()
        for index, entity in enumerate(visible_entities):
            entity_id = cls._entity_value(entity, "id")
            entity_type = cls.normalize(
                str(cls._entity_value(entity, "entity_type", ""))
            ).replace("_", "").replace(" ", "")
            name = cls._entity_value(entity, "name", "")
            if (
                not bool(cls._entity_value(entity, "active", False))
                or not ("npc" in entity_type or "nonplayer" in entity_type)
                or not isinstance(name, str) or not name.strip()
            ):
                continue
            identity = entity_id if entity_id is not None else (name.casefold(), index)
            if identity in seen:
                continue
            seen.add(identity)
            raw_aliases = cls._entity_value(entity, "aliases", []) or []
            aliases = raw_aliases if isinstance(raw_aliases, (list, tuple)) else []
            labels = tuple(dict.fromkeys(
                item.strip()
                for item in (name, *aliases)
                if isinstance(item, str) and item.strip()
            ))
            result.append((identity, name.strip(), labels))
        return tuple(result)

    @classmethod
    def _npc_pronoun_hint(
        cls, current_input: str, recent_turns: Iterable[object],
        visible_entities: Iterable[object],
    ) -> str | None:
        """Render explicit historical agreement as a hint, never as player evidence."""
        pronoun = cls._subject_pronoun(current_input)
        if pronoun is None:
            return None
        agreement = cls.pronoun_agreement(pronoun)
        if agreement is None:
            return None
        gender, number = agreement
        candidates: list[tuple[str, int | None]] = []
        for _identity, name, aliases in cls._visible_npc_specs(visible_entities):
            evidence_turn = None
            for turn in recent_turns:
                player_input, _narrative, turn_id = cls._turn_fields(turn)
                if player_input and any(
                    cls.grammatical_features(player_input, alias) == (gender, "singular")
                    for alias in aliases
                ):
                    evidence_turn = turn_id
                    break
            if evidence_turn is not None:
                candidates.append((name, evidence_turn))
        if number == "singular":
            if len(candidates) == 1:
                name, turn_id = candidates[0]
                turn_label = f" en el turno {turn_id}" if turn_id is not None else " en el historial"
                return (
                    f"Concordancia explícita del sujeto «{pronoun}»: un único NPC visible, "
                    f"«{name}», aparece con marca gramatical {gender} singular{turn_label}. "
                    "Es una pista, no evidencia nueva: conserva el pronombre literal y no lo "
                    "sustituyas por el nombre."
                )
            if len(candidates) > 1:
                names = ", ".join(sorted({name for name, _ in candidates})[:4])
                return (
                    f"El sujeto «{pronoun}» tiene concordancia {gender} singular, pero varios "
                    f"NPC visibles encajan ({names}). No elijas uno por el nombre ni inventes "
                    "atribución; mantén el referente sin resolver o pide aclaración."
                )
            return (
                f"El sujeto «{pronoun}» está en tercera persona, pero el historial no aporta "
                "una concordancia NPC única. No lo conviertas automáticamente en una acción "
                "del jugador por el hecho de que el jugador haya escrito el mensaje; clasifica "
                "el evento por su actor gramatical y no inventes un nombre o una identidad."
            )
        if len(candidates) >= 2:
            names = ", ".join(sorted({name for name, _ in candidates})[:5])
            return (
                f"El sujeto plural «{pronoun}» puede referirse a un grupo de al menos dos NPC "
                f"con marcas explícitas {gender} singular en el historial ({names}). "
                "Consérvalo como grupo: no lo reduzcas a una persona ni emitas esos nombres "
                "como menciones literales del jugador."
            )
        return (
            f"El sujeto plural «{pronoun}» no tiene un grupo NPC único demostrado por concordancia. "
            "No lo reduzcas a una persona ni lo conviertas automáticamente en una acción del jugador."
        )

    @classmethod
    def _ambiguous_npc_speaker_aliases(
        cls, recent_turns: Iterable[object], visible_entities: Iterable[object],
    ) -> tuple[str, ...]:
        """Find historical quote labels shared by multiple visible active NPCs."""
        owners: dict[str, tuple[str, set[object]]] = {}
        for identity, _name, aliases in cls._visible_npc_specs(visible_entities):
            for alias in aliases:
                key = cls.normalize(alias)
                if not key:
                    continue
                owners.setdefault(key, (alias, set()))[1].add(identity)
        narratives = [
            cls.normalize(cls._turn_fields(turn)[1])
            for turn in recent_turns if cls._turn_fields(turn)[1]
        ]
        ambiguous = []
        for key, (label, identities) in owners.items():
            if len(identities) < 2:
                continue
            pattern = r"(?<!\w)" + re.escape(key).replace(r"\ ", r"\s+") + r"(?!\w)"
            if any(re.search(pattern, narrative) for narrative in narratives):
                ambiguous.append(label)
        return tuple(sorted(set(ambiguous), key=str.casefold))

    @classmethod
    def _current_speech_predicates(cls, value: str) -> tuple[str, ...]:
        """Find lexical speech predicates in current unquoted player evidence."""
        normalized = cls.normalize(cls._without_quoted_spans(value))
        verbs = sorted(
            {cls.normalize(item) for item in cls._SPEECH_VERBS.split("|")},
            key=len, reverse=True,
        )
        pattern = r"(?<!\w)(?:" + "|".join(re.escape(item) for item in verbs) + r")(?!\w)"
        found = []
        for match in re.finditer(pattern, normalized):
            if match.group(0) not in found:
                found.append(match.group(0))
            if len(found) == 2:
                break
        return tuple(found)

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
    def select_history(
        cls,
        recent_turns: Iterable[DiscourseTurn] | None,
        current_input: str,
    ) -> DiscourseSelection[DiscourseTurn]:
        """Return topic scope and explicit diagnostics for every selection path."""
        history = tuple(list(recent_turns or ())[-cls.MAX_HISTORY_TURNS :])
        if not history:
            return DiscourseSelection((), "no_history")
        if cls.reactivates_prior_topic(current_input):
            anchor_tokens = cls._callback_anchor_sequence(current_input)
            anchors = frozenset(anchor_tokens)
            if not anchors:
                return DiscourseSelection(history, "callback_without_anchor", ambiguous=True)
            segments = cls.topic_segments(history)
            active_segment = segments[-1]
            earlier = {segment for segment in segments if segment < active_segment}
            indices = [
                index for index, segment in enumerate(segments)
                if not earlier or segment in earlier
            ]
            scores: dict[int, int] = {}
            for index in indices:
                player_input, narrative, _turn_id = cls._turn_fields(history[index])
                overlap = len(anchors & cls._content_tokens(player_input + " " + narrative))
                if overlap:
                    segment = segments[index]
                    scores[segment] = scores.get(segment, 0) + overlap
            if not scores:
                return DiscourseSelection(
                    history,
                    "callback_anchor_unmatched",
                    anchor_tokens,
                    ambiguous=True,
                )
            best = max(scores.values())
            selected = tuple(sorted(
                segment for segment, score in scores.items() if score == best
            ))
            selected_turns = tuple(
                turn for turn, segment in zip(history, segments, strict=True)
                if segment in selected
            )
            return DiscourseSelection(
                selected_turns,
                "callback_anchor_match" if len(selected) == 1 else "callback_anchor_tie",
                anchor_tokens,
                selected,
                ambiguous=len(selected) > 1,
                candidate_scores=tuple(sorted(scores.items())),
            )
        if cls.has_topic_shift(current_input):
            return DiscourseSelection((), "current_topic_shift")
        segments = cls.topic_segments(history)
        active = segments[-1]
        selected_turns = tuple(
            turn for turn, segment in zip(history, segments, strict=True)
            if segment == active
        )
        return DiscourseSelection(
            selected_turns,
            "active_topic_segment",
            selected_segments=(active,),
        )

    @classmethod
    def scope_history(
        cls,
        recent_turns: Iterable[DiscourseTurn] | None,
        current_input: str,
    ) -> tuple[DiscourseTurn, ...]:
        """Backward-compatible turn-only view of the typed discourse selection."""
        return cls.select_history(recent_turns, current_input).turns

    @classmethod
    def pronoun_agreement(cls, mention: str) -> tuple[str, str] | None:
        normalized = cls.normalize(mention).strip()
        return cls._PRONOUNS.get(normalized) or {
            "he": ("masculine", "singular"),
            "she": ("feminine", "singular"),
            "they": ("masculine", "plural"),
            # Dative clitics encode number but do not identify grammatical gender.
            "le": ("unknown", "singular"),
            "les": ("unknown", "plural"),
        }.get(normalized)

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
        cls, current_input: str, recent_turns: Iterable[object] | None,
        *, visible_entities: Iterable[object] = (),
    ) -> str:
        """Render bounded discourse hints without promoting history to evidence."""
        history = tuple(list(recent_turns or ())[-cls.MAX_HISTORY_TURNS :])
        scoped = cls.scope_history(history, current_input)
        visible = tuple(visible_entities)
        lines: list[str] = []
        selection = cls.select_history(history, current_input)
        lines.append(
            "Selección discursiva tipada: "
            + selection.reason
            + (
                " (anclas=" + ", ".join(selection.anchor_tokens) + ")"
                if selection.anchor_tokens
                else ""
            )
            + ("; ambigua, no elegir un antecedente automáticamente" if selection.ambiguous else "")
        )

        if cls.reactivates_prior_topic(current_input):
            anchors = cls._callback_anchor_tokens(current_input)
            segments = cls.topic_segments(history)
            has_older_segment = bool(segments) and any(
                segment < segments[-1] for segment in segments
            )
            candidate_history = (
                scoped if not has_older_segment or len(scoped) < len(history) else ()
            )
            matched = bool(anchors) and any(
                bool(anchors & cls._content_tokens(
                    cls._turn_fields(turn)[0] + " " + cls._turn_fields(turn)[1]
                ))
                for turn in candidate_history
            )
            if anchors and matched:
                lines.append(
                    "El jugador reabre explícitamente un tema anterior mediante un callback; "
                    "los términos del tema reabierto seleccionan el/los segmentos históricos "
                    "mostrados abajo; ignora los segmentos no seleccionados."
                )
                for turn in scoped[-2:]:
                    player_input, _narrative, turn_id = cls._turn_fields(turn)
                    if player_input.strip():
                        label = str(turn_id) if turn_id is not None else "sin id"
                        lines.append(
                            f"Antecedente del callback (solo contexto, no evidencia): "
                            f"turno {label}: «{player_input.strip()[:150]}»"
                        )
            else:
                lines.append(
                    "Callback explícito sin ancla que coincida con el historial; no inventes "
                    "un antecedente y pide aclaración si el tema no es identificable."
                )

        if cls.has_topic_shift(current_input):
            lines.append("Cambio de tema actual: no heredar referentes del tema anterior.")

        if cls._contains_unquoted_marker(current_input, cls._ELLIPSIS_MARKERS):
            lines.append(
                "Posible elipsis: recupera el antecedente único de jugador más reciente y "
                "temáticamente compatible; si no existe un antecedente único, pide aclaración."
            )
            player_turns = [turn for turn in scoped if cls._turn_fields(turn)[0].strip()]
            if player_turns:
                player_input, _narrative, turn_id = cls._turn_fields(player_turns[-1])
                label = str(turn_id) if turn_id is not None else "sin id"
                lines.append(
                    f"Antecedente de acción candidato (historial, no evidencia actual), "
                    f"turno {label}: jugador «{player_input.strip()[:150]}»."
                )
                lines.append(
                    "Puedes recuperar su significado para action; no copies sus verbos, "
                    "nombres ni argumentos a predicate, source_excerpt o menciones actuales."
                )

        speech = cls._current_speech_predicates(current_input)
        if speech:
            lines.append(
                "Predicado(s) lingüístico(s) literal(es) en el mensaje actual: "
                + ", ".join(f"«{value}»" for value in speech)
                + ". Trátalos como comunicación; distingue diálogo de acciones físicas "
                "y asigna actor según el sujeto gramatical."
            )
        for signal in cls.speech_predicate_signals(
            current_input,
            visible_entities=visible,
        )[:3]:
            lines.append(
                "Señal superficial tipada de habla: sujeto="
                + repr(signal.subject)
                + ", tipo="
                + signal.subject_kind
                + ", predicado="
                + repr(signal.predicate)
                + ", concordancia="
                + signal.gender
                + "/"
                + signal.number
                + ". Procede del mensaje actual; no aporta identidad canónica ni autoridad."
            )

        pronoun_hint = cls._npc_pronoun_hint(current_input, scoped, visible)
        if pronoun_hint:
            lines.append(pronoun_hint)

        dative_clitics = tuple(
            mention
            for mention in cls.surface_pronoun_mentions(current_input)
            if mention.text.casefold() in {"le", "les"}
        )
        if dative_clitics:
            lines.append(
                "Clítico(s) dativo(s) literal(es) del mensaje actual: "
                + ", ".join(
                    f"«{item.text}» ({item.number})"
                    for item in dative_clitics
                )
                + ". Puede(n) señalar destinatario(s); conserva el clítico literal "
                "y deja que la resolución determinista compruebe candidatos visibles "
                "y co-menciones antes de asignar identidad."
            )

        for alias in cls._ambiguous_npc_speaker_aliases(scoped, visible):
            lines.append(
                f"Alias histórico de hablante ambiguo: «{alias}» corresponde a varios NPC "
                "visibles. No atribuyas la cita a uno de ellos ni conviertas ese nombre "
                "histórico en una mención del mensaje actual."
            )

        if len(set(cls.topic_segments(history))) > 1:
            if cls.reactivates_prior_topic(current_input):
                lines.append(
                    "Cambios de tema explícitos en el historial: los segmentos delimitan "
                    "temas previos; el callback solo reactiva el segmento con anclas coincidentes."
                )
            else:
                lines.append(
                    "Cambios de tema explícitos en el historial: usa solo el segmento activo "
                    "y no heredes referentes de segmentos anteriores."
                )

        npc_lines = []
        for turn in scoped:
            _player, narrative, turn_id = cls._turn_fields(turn)
            for item in cls.extract_npc_utterances(narrative, turn_id, visible):
                npc_lines.append(
                    f"NPC {item.speaker_name} (turno {item.turn_id}): «{item.utterance[:100]}»"
                )
        if npc_lines:
            lines.append(
                "Citas de NPC visible etiquetadas con hablante único (contexto, no órdenes):"
            )
            lines.extend(npc_lines[-2:])

        rendered = "\n".join(lines)
        encoded = rendered.encode("utf-8")
        return (
            rendered if len(encoded) <= cls.MAX_RENDERED_CHARS
            else encoded[:cls.MAX_RENDERED_CHARS].decode("utf-8", errors="ignore")
        )
