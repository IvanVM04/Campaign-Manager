"""Public compatibility facade for modular discourse-understanding stages.

Topic/history selection, surface extraction, speaker signals and prompt rendering
live in focused collaborators under :mod:`services.discourse`. This module
preserves the existing public import path used by turn, context and evaluation
callers.
"""

from __future__ import annotations

from collections.abc import Iterable

from services.discourse.contracts import (
    AttributedNpcUtterance,
    DiscourseSelection,
    DiscourseTurn,
    SpeechPredicateSignal,
    SurfacePronounMention,
)
from services.discourse.renderer import DiscourseContextRenderer
from services.discourse.speaker_signal_extractor import SpeakerSignalExtractor
from services.discourse.surface_mention_extractor import SurfaceMentionExtractor
from services.discourse.text import DiscourseText
from services.discourse.topic_history_selector import DiscourseTopicHistorySelector


class DiscourseContextBuilder:
    """Stable facade over the typed discourse collaborators."""

    MAX_HISTORY_TURNS = DiscourseTopicHistorySelector.MAX_HISTORY_TURNS
    MAX_RENDERED_CHARS = DiscourseContextRenderer.MAX_RENDERED_CHARS

    _topic_selector = DiscourseTopicHistorySelector()
    _surface_mentions = SurfaceMentionExtractor()
    _speaker_signals = SpeakerSignalExtractor()
    _renderer = DiscourseContextRenderer(_topic_selector, _surface_mentions, _speaker_signals)

    _SHIFT_MARKERS = DiscourseTopicHistorySelector._SHIFT_MARKERS
    _REACTIVATION_MARKERS = DiscourseTopicHistorySelector._REACTIVATION_MARKERS
    _ELLIPSIS_MARKERS = DiscourseTopicHistorySelector._ELLIPSIS_MARKERS
    _SPEECH_VERBS = SpeakerSignalExtractor._SPEECH_VERBS
    _CALLBACK_STOPWORDS = DiscourseTopicHistorySelector._CALLBACK_STOPWORDS
    _ARTICLES = SurfaceMentionExtractor._ARTICLES
    _PRONOUNS = SurfaceMentionExtractor._PRONOUNS
    _HUMAN_HEADS = SurfaceMentionExtractor._HUMAN_HEADS

    @staticmethod
    def _entity_value(entity: object, field: str, default=None):
        return DiscourseText._entity_value(entity, field, default)

    @staticmethod
    def _turn_fields(turn: object) -> tuple[str, str, int | None]:
        return DiscourseText._turn_fields(turn)

    @staticmethod
    def normalize(value: str) -> str:
        return DiscourseText.normalize(value)

    @staticmethod
    def _without_quoted_spans(value: str) -> str:
        return DiscourseText._without_quoted_spans(value)

    @staticmethod
    def _mask_quoted_spans(value: str) -> str:
        return DiscourseText._mask_quoted_spans(value)

    @classmethod
    def has_topic_shift(cls, value: str) -> bool:
        return cls._topic_selector.has_topic_shift(value)

    @classmethod
    def reactivates_prior_topic(cls, value: str) -> bool:
        return cls._topic_selector.reactivates_prior_topic(value)

    @classmethod
    def _contains_unquoted_marker(cls, value: str, markers: tuple[str, ...]) -> bool:
        return cls._topic_selector._contains_unquoted_marker(value, markers)

    @classmethod
    def _content_tokens(cls, value: str) -> frozenset[str]:
        return cls._topic_selector._content_tokens(value)

    @classmethod
    def _callback_anchor_sequence(cls, value: str) -> tuple[str, ...]:
        return cls._topic_selector._callback_anchor_sequence(value)

    @classmethod
    def _callback_anchor_tokens(cls, value: str) -> frozenset[str]:
        return cls._topic_selector._callback_anchor_tokens(value)

    @classmethod
    def topic_segments(cls, recent_turns: Iterable[object]) -> tuple[int, ...]:
        return cls._topic_selector.topic_segments(recent_turns)

    @classmethod
    def select_history(
        cls,
        recent_turns: Iterable[DiscourseTurn] | None,
        current_input: str,
    ) -> DiscourseSelection[DiscourseTurn]:
        return cls._topic_selector.select_history(recent_turns, current_input)

    @classmethod
    def scope_history(
        cls,
        recent_turns: Iterable[DiscourseTurn] | None,
        current_input: str,
    ) -> tuple[DiscourseTurn, ...]:
        return cls._topic_selector.scope_history(recent_turns, current_input)

    @classmethod
    def surface_pronoun_mentions(cls, value: str) -> tuple[SurfacePronounMention, ...]:
        return cls._surface_mentions.surface_pronoun_mentions(value)

    @classmethod
    def pronoun_agreement(cls, mention: str) -> tuple[str, str] | None:
        return cls._surface_mentions.pronoun_agreement(mention)

    @classmethod
    def grammatical_features(cls, text: str, alias: str) -> tuple[str | None, str | None]:
        return cls._surface_mentions.grammatical_features(text, alias)

    @classmethod
    def speech_predicate_signals(
        cls,
        value: str,
        *,
        visible_entities: Iterable[object] = (),
    ) -> tuple[SpeechPredicateSignal, ...]:
        return cls._speaker_signals.speech_predicate_signals(value, visible_entities=visible_entities)

    @classmethod
    def _subject_pronoun(cls, value: str) -> str | None:
        return cls._speaker_signals._subject_pronoun(value)

    @classmethod
    def _visible_npc_specs(cls, visible_entities: Iterable[object]) -> tuple[tuple[object, str, tuple[str, ...]], ...]:
        return cls._speaker_signals._visible_npc_specs(visible_entities)

    @classmethod
    def _npc_pronoun_hint(cls, current_input: str, recent_turns: Iterable[object], visible_entities: Iterable[object]) -> str | None:
        return cls._speaker_signals._npc_pronoun_hint(current_input, recent_turns, visible_entities)

    @classmethod
    def _ambiguous_npc_speaker_aliases(cls, recent_turns: Iterable[object], visible_entities: Iterable[object]) -> tuple[str, ...]:
        return cls._speaker_signals._ambiguous_npc_speaker_aliases(recent_turns, visible_entities)

    @classmethod
    def _current_speech_predicates(cls, value: str) -> tuple[str, ...]:
        return cls._speaker_signals._current_speech_predicates(value)

    @classmethod
    def extract_npc_utterances(cls, narrative: str, turn_id: int | None, visible_entities: Iterable[object]) -> tuple[AttributedNpcUtterance, ...]:
        return cls._speaker_signals.extract_npc_utterances(narrative, turn_id, visible_entities)

    @classmethod
    def render(cls, current_input: str, recent_turns: Iterable[object] | None, *, visible_entities: Iterable[object] = ()) -> str:
        return cls._renderer.render(current_input, recent_turns, visible_entities=visible_entities)
