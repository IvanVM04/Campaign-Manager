from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ActivityEventType = Literal[
    "turn.accepted",
    "turn.awaiting_input",
    "turn.committed",
    "turn.completed",
    "turn.failed",
]


class ActivityEventRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    resolution_id: int | None
    session_id: int | None
    turn_id: int | None
    event_type: ActivityEventType
    summary: str
    details: dict[str, object]
    occurred_at: str


class ActivityEventPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[ActivityEventRead, ...]
    total: int
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
