"""Trusted typed references to non-entity world records."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from models.discourse_evidence import DiscourseEvidence


class WorldReferenceCategory(str, enum.Enum):
    ITEM_DEFINITION = "item_definition"
    ITEM_INSTANCE = "item_instance"
    RESOURCE = "resource"
    EVENT = "event"


@dataclass(frozen=True, slots=True)
class ResolvedWorldReference:
    """A player mention linked to one visible, typed world record."""

    mention: str
    category: WorldReferenceCategory
    referent_id: int | str
    name: str
    match_kind: str
    antecedent_turn_id: int | None = None
    evidence: tuple[DiscourseEvidence, ...] = ()
    confidence_score: int = 0
    resolution_signals: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name, value, maximum in (
            ("mention", self.mention, 120),
            ("name", self.name, 160),
            ("match_kind", self.match_kind, 40),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"{field_name} must contain 1-{maximum} characters")
        if not isinstance(self.category, WorldReferenceCategory):
            raise TypeError("category must be a WorldReferenceCategory")
        if self.category is WorldReferenceCategory.EVENT:
            if not isinstance(self.referent_id, str) or not self.referent_id.strip():
                raise ValueError("event references require a non-empty string id")
        elif (
            isinstance(self.referent_id, bool)
            or not isinstance(self.referent_id, int)
            or self.referent_id < 1
        ):
            raise ValueError("world-record references require a positive integer id")
        if self.antecedent_turn_id is not None and (
            isinstance(self.antecedent_turn_id, bool)
            or not isinstance(self.antecedent_turn_id, int)
            or self.antecedent_turn_id < 1
        ):
            raise ValueError("antecedent_turn_id must be a positive integer or None")
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(item, DiscourseEvidence) for item in self.evidence
        ):
            raise TypeError("evidence must contain DiscourseEvidence values")
        if (
            isinstance(self.confidence_score, bool)
            or not isinstance(self.confidence_score, int)
            or not 0 <= self.confidence_score <= 1000
        ):
            raise ValueError("confidence_score must be between 0 and 1000")
        if not isinstance(self.resolution_signals, tuple) or any(
            not isinstance(item, str) or not item.strip() or len(item) > 40
            for item in self.resolution_signals
        ):
            raise ValueError("resolution_signals must be a tuple of bounded strings")
