"""Bounded topic/history selection with explicit callback diagnostics."""

from __future__ import annotations

from collections.abc import Iterable

from services.discourse.contracts import DiscourseSelection, DiscourseTurn
from services.discourse.text import DiscourseText


class DiscourseTopicHistorySelector(DiscourseText):
    """Select same-conversation history without promoting it to current evidence."""

    MAX_HISTORY_TURNS = 12
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
