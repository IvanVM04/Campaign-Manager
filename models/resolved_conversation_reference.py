"""Trusted conversation-reference matches produced by deterministic application code."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolvedConversationReference:
    """A literal player mention mapped to one visible canonical entity."""

    mention: str
    entity_id: int
    entity_name: str
    match_kind: str
    antecedent_turn_id: int | None = None

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
