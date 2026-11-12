"""Stable error identities for durable turn lifecycle failures."""

from __future__ import annotations

from enum import StrEnum


class DurableTurnErrorCode(StrEnum):
    """Stable machine-readable failure reasons for durable turn operations."""

    CONFLICT = "conflict"
    STALE_CONTEXT = "stale_context"
    CONSEQUENCE_VALIDATION_FAILED = "operation_validation_failed"
    CHARACTER_OPERATION_NOT_ALLOWED = "character_operation_not_allowed"
    EXECUTION_FAILED = "turn_execution_failed"


class DurableNativeTurnError(RuntimeError):
    """Failure while executing or resuming a durable native turn.

    The code attribute is a stable machine-readable reason. Error messages
    remain useful for trusted callers and logs, but lifecycle decisions must
    not be based on their wording.
    """

    def __init__(
        self,
        message: str,
        *,
        code: DurableTurnErrorCode | str = DurableTurnErrorCode.CONFLICT,
    ) -> None:
        super().__init__(message)
        self.code = str(code)


class DurableTurnCommitError(DurableNativeTurnError):
    """A prepared resolution could not be committed against current state."""
