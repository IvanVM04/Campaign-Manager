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



@dataclass(frozen=True, slots=True)
class ResolvedConversationGroupMember:
    """One independently evidenced visible entity in a resolved discourse group."""

    entity_id: int
    entity_name: str
    evidence: tuple[DiscourseEvidence, ...]
    confidence_score: int
    resolution_signals: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.entity_id, bool) or not isinstance(self.entity_id, int) or self.entity_id < 1:
            raise ValueError("entity_id must be a positive integer")
        if not isinstance(self.entity_name, str) or not self.entity_name.strip() or len(self.entity_name) > 120:
            raise ValueError("entity_name must contain 1-120 characters")
        if not isinstance(self.evidence, tuple) or not self.evidence or any(
            not isinstance(item, DiscourseEvidence) for item in self.evidence
        ):
            raise ValueError("group member evidence must be a non-empty tuple of DiscourseEvidence")
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


@dataclass(frozen=True, slots=True)
class ResolvedConversationGroupReference:
    """A plural surface mention mapped to a proven set of visible group members.

    This is transient comprehension only. It never creates a persistent group
    entity and never makes the group a valid single-target mechanics identifier.
    """

    mention: str
    members: tuple[ResolvedConversationGroupMember, ...]
    antecedent_turn_id: int
    match_kind: str = "conversation_group"

    def __post_init__(self) -> None:
        if not isinstance(self.mention, str) or not self.mention.strip() or len(self.mention) > 120:
            raise ValueError("mention must contain 1-120 characters")
        if not isinstance(self.members, tuple) or not 2 <= len(self.members) <= 8:
            raise ValueError("conversation group must contain 2-8 members")
        if any(not isinstance(item, ResolvedConversationGroupMember) for item in self.members):
            raise TypeError("members must contain ResolvedConversationGroupMember values")
        ids = tuple(item.entity_id for item in self.members)
        if len(set(ids)) != len(ids):
            raise ValueError("conversation group members must have unique entity IDs")
        if (
            isinstance(self.antecedent_turn_id, bool)
            or not isinstance(self.antecedent_turn_id, int)
            or self.antecedent_turn_id < 1
        ):
            raise ValueError("antecedent_turn_id must be a positive integer")
        if not isinstance(self.match_kind, str) or not self.match_kind.strip() or len(self.match_kind) > 40:
            raise ValueError("match_kind must contain 1-40 characters")

    @property
    def entity_ids(self) -> tuple[int, ...]:
        return tuple(member.entity_id for member in self.members)

    @property
    def entity_names(self) -> tuple[str, ...]:
        return tuple(member.entity_name for member in self.members)


ResolvedConversationReferenceResult = (
    ResolvedConversationReference | ResolvedConversationGroupReference
)
