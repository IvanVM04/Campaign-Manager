from __future__ import annotations

from dataclasses import dataclass

from models.world_state import WorldState


def estimate_tokens(text: str) -> int:
    """Return a conservative upper bound for model tokens.

    The provider port does not expose the selected model's tokenizer. Counting
    one token per UTF-8 byte is intentionally pessimistic: a tokenizer may
    combine bytes into larger tokens, but it cannot require more tokens than
    input bytes. The value is a budget upper bound, not an exact token count.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return len(text.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class ContextProjectionDiagnostics:
    """Size and selection metrics for a detached, model-facing world view."""

    estimated_tokens: int
    budget_tokens: int
    available_counts: tuple[tuple[str, int], ...]
    candidate_counts: tuple[tuple[str, int], ...]
    selected_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        for name in ("estimated_tokens", "budget_tokens"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.budget_tokens <= 0:
            raise ValueError("budget_tokens must be greater than zero")

    @property
    def available_records(self) -> int:
        return sum(count for _, count in self.available_counts)

    @property
    def candidate_records(self) -> int:
        return sum(count for _, count in self.candidate_counts)

    @property
    def selected_records(self) -> int:
        return sum(count for _, count in self.selected_counts)

    @property
    def excluded_records(self) -> int:
        return max(0, self.available_records - self.selected_records)


@dataclass(frozen=True, slots=True)
class WorldContextProjection:
    """Detached subset of a campaign world selected for one model request."""

    world: WorldState
    diagnostics: ContextProjectionDiagnostics

    def __post_init__(self) -> None:
        if not isinstance(self.world, WorldState):
            raise TypeError("world must be a WorldState")
        if not isinstance(self.diagnostics, ContextProjectionDiagnostics):
            raise TypeError("diagnostics must be ContextProjectionDiagnostics")
