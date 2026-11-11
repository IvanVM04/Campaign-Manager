from __future__ import annotations

from dataclasses import dataclass

from models.world_state import WorldState


def estimate_tokens(text: str) -> int:
    """Return a conservative, provider-independent token estimate.

    Ollama providers do not expose a tokenizer contract through the current
    provider port. Three UTF-8 bytes per token intentionally errs on the safe
    side for Spanish and structured JSON. This is a budget estimate, not an
    exact model-token count.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not text:
        return 0
    return (len(text.encode("utf-8")) + 2) // 3


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
