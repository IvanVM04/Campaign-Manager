"""Immutable discourse-stage output contracts.

These records carry source spans and bounded selection diagnostics only.
They never assign canonical entity identity or grant world-write authority.
"""

from dataclasses import dataclass
from typing import TypeVar

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
