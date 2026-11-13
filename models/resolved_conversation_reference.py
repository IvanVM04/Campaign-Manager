"""Trusted conversation-reference matches produced by deterministic application code."""

from __future__ import annotations

from dataclasses import dataclass

from models.discourse_evidence import DiscourseEvidence


@dataclass(frozen=True, slots=True)
class ResolvedConversationReference:
    """A literal player mention mapped to one visible canonical entity."""

    mention: str
    entity_id: int
    entity_name: str
    match_kind: str
    antecedent_turn_id: int | None = None
    evidence: tuple[DiscourseEvidence, ...] = ()
    confidence_score: int = 0
    resolution_signals: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value, maximum in (
            ("mention", self.mention, 120),
            ("entity_name", self.entity_name, 120),
            ("match_kind", self.match_kind, 40),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"{name} must contain 1-{maximum} characters")
        if isinstance(self.entity_id, bool) or not isinstance(self.entity_id, int) or self.entity_id < 1:
            raise ValueError("entity_id must be a positive integer")
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
