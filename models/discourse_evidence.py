"""Typed, application-produced evidence for cross-turn discourse resolution."""

from __future__ import annotations

import enum
import re
import unicodedata
from dataclasses import dataclass

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class DiscourseSource(str, enum.Enum):
    PLAYER_INPUT = "player_input"
    NARRATIVE = "narrative"


class DiscourseSpeaker(str, enum.Enum):
    PLAYER = "player"
    NARRATOR = "narrator"
    NPC = "npc"


@dataclass(frozen=True, slots=True)
class DiscourseEvidence:
    """One literal antecedent occurrence from an already scoped transcript turn."""

    turn_id: int | None
    source: DiscourseSource
    speaker: DiscourseSpeaker
    mention: str
    excerpt: str
    recency_rank: int
    speaker_entity_id: int | None = None

    def __post_init__(self) -> None:
        if self.turn_id is not None and (
            isinstance(self.turn_id, bool)
            or not isinstance(self.turn_id, int)
            or self.turn_id < 1
        ):
            raise ValueError("turn_id must be a positive integer or None")
        if not isinstance(self.source, DiscourseSource):
            raise TypeError("source must be a DiscourseSource")
        if not isinstance(self.speaker, DiscourseSpeaker):
            raise TypeError("speaker must be a DiscourseSpeaker")
        _validate_text(self.mention, "mention", 120)
        _validate_text(self.excerpt, "excerpt", 1200)
        if (
            isinstance(self.recency_rank, bool)
            or not isinstance(self.recency_rank, int)
            or not 1 <= self.recency_rank <= 12
        ):
            raise ValueError("recency_rank must be between 1 and 12")
        if self.speaker_entity_id is not None and (
            isinstance(self.speaker_entity_id, bool)
            or not isinstance(self.speaker_entity_id, int)
            or self.speaker_entity_id < 1
        ):
            raise ValueError("speaker_entity_id must be a positive integer or None")
        if self.speaker is DiscourseSpeaker.NPC and self.speaker_entity_id is None:
            raise ValueError("NPC discourse evidence requires an explicit speaker entity id")
        if self.speaker is not DiscourseSpeaker.NPC and self.speaker_entity_id is not None:
            raise ValueError("speaker_entity_id is only valid for NPC discourse evidence")
        if not _contains_literal(self.excerpt, self.mention):
            raise ValueError("mention must occur in its evidence excerpt")


@dataclass(frozen=True, slots=True)
class DiscourseCandidate:
    """A visible canonical entity supported by typed transcript evidence."""

    entity_id: int
    entity_name: str
    score: int
    evidence: tuple[DiscourseEvidence, ...]
    signals: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.entity_id, bool)
            or not isinstance(self.entity_id, int)
            or self.entity_id < 1
        ):
            raise ValueError("entity_id must be a positive integer")
        _validate_text(self.entity_name, "entity_name", 120)
        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, int)
            or not 0 <= self.score <= 1000
        ):
            raise ValueError("score must be an integer between 0 and 1000")
        if not isinstance(self.evidence, tuple) or not self.evidence:
            raise ValueError("evidence must be a non-empty tuple")
        if any(not isinstance(item, DiscourseEvidence) for item in self.evidence):
            raise TypeError("evidence must contain DiscourseEvidence values")
        if not isinstance(self.signals, tuple) or any(
            not isinstance(item, str) or not item.strip() or len(item) > 40
            for item in self.signals
        ):
            raise ValueError("signals must be a tuple of bounded strings")


def _validate_text(value: str, field_name: str, maximum: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field_name} must contain 1-{maximum} characters")


def _contains_literal(source: str, fragment: str) -> bool:
    normalize = lambda value: " ".join(
        _TOKEN_PATTERN.findall(
            "".join(
                char
                for char in unicodedata.normalize("NFKD", value.casefold())
                if not unicodedata.combining(char)
            )
        )
    )
    normalized_fragment = normalize(fragment)
    return bool(normalized_fragment) and (
        f" {normalized_fragment} " in f" {normalize(source)} "
    )
