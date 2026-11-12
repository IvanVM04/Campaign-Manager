from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import ClassVar

ACTIVITY_EVENT_TYPES = frozenset(
    {
        "turn.accepted",
        "turn.awaiting_input",
        "turn.committed",
        "turn.completed",
        "turn.failed",
    }
)


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    """Safe, campaign-scoped activity record for player-facing history."""

    campaign_id: int
    event_type: str
    summary: str
    dedupe_key: str
    id: int | None = None
    resolution_id: int | None = None
    session_id: int | None = None
    turn_id: int | None = None
    details: dict[str, object] = field(default_factory=dict)
    request_id: str | None = None
    occurred_at: str | None = None

    VALID_DETAILS: ClassVar[dict[str, frozenset[str]]] = {
        "turn.accepted": frozenset({"adapter", "dice_mode"}),
        "turn.awaiting_input": frozenset({"challenge_type"}),
        "turn.committed": frozenset(
            {
                "operation_count",
                "successful_operation_count",
                "failed_operation_count",
                "world_changed",
            }
        ),
        "turn.completed": frozenset({"turn_version"}),
        "turn.failed": frozenset({"error_code", "retryable"}),
    }

    def __post_init__(self) -> None:
        if isinstance(self.campaign_id, bool) or not isinstance(self.campaign_id, int) or self.campaign_id < 1:
            raise ValueError("campaign_id must be a positive integer")
        for name in ("id", "resolution_id", "session_id", "turn_id"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer or None")
        if self.event_type not in ACTIVITY_EVENT_TYPES:
            raise ValueError("unsupported activity event type")
        if not isinstance(self.summary, str) or not self.summary.strip() or len(self.summary) > 160:
            raise ValueError("summary must contain 1-160 characters")
        if not isinstance(self.dedupe_key, str) or not self.dedupe_key.strip() or len(self.dedupe_key) > 200:
            raise ValueError("dedupe_key must contain 1-200 characters")
        if not isinstance(self.details, dict):
            raise TypeError("details must be a dictionary")
        allowed = self.VALID_DETAILS[self.event_type]
        if not set(self.details).issubset(allowed):
            raise ValueError("activity details contain unsupported fields")
        try:
            encoded = json.dumps(
                self.details,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("activity details must be JSON serializable") from exc
        if len(encoded.encode("utf-8")) > 2048:
            raise ValueError("activity details must not exceed 2048 bytes")
        if self.request_id is not None and (
            not isinstance(self.request_id, str) or len(self.request_id) > 64
        ):
            raise ValueError("request_id must be at most 64 characters or None")
