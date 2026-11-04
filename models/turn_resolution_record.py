from __future__ import annotations

from dataclasses import dataclass
import json
from typing import ClassVar


VALID_LIFECYCLE_STATES = frozenset({
    "accepted",
    "planning",
    "awaiting_input",
    "prepared",
    "committed",
    "narration_pending",
    "completed",
    "rejected",
})


@dataclass(frozen=True)
class TurnResolutionRecord:
    """Durable execution envelope; TurnRecord remains the historical transcript."""

    id: int | None = None
    campaign_id: int = 1
    session_id: int | None = None
    turn_id: int | None = None

    player_input: str = ""
    adapter_namespace: str = "native"
    idempotency_key: str = ""
    request_fingerprint: str = ""

    lifecycle_state: str = "accepted"
    context_revision: int | None = None
    proposal_json: str | None = None
    adjudication_json: str | None = None
    mechanics_json: str | None = None
    operation_results_json: str | None = None
    narrative: str | None = None

    attempt_count: int = 0
    lease_token: str | None = None
    lease_expires_at: str | None = None
    last_error_code: str | None = None

    created_at: str | None = None
    updated_at: str | None = None
    committed_at: str | None = None
    completed_at: str | None = None

    TRANSITIONS: ClassVar[dict[str, frozenset[str]]] = {
        "accepted": frozenset({"planning", "rejected"}),
        "planning": frozenset({"accepted", "awaiting_input", "prepared", "rejected"}),
        "awaiting_input": frozenset({"planning", "rejected"}),
        "prepared": frozenset({"committed", "rejected"}),
        "committed": frozenset({"narration_pending"}),
        "narration_pending": frozenset({"completed"}),
        "completed": frozenset(),
        "rejected": frozenset(),
    }

    def __post_init__(self) -> None:
        self._positive_int(self.campaign_id, "campaign_id")
        self._optional_positive_int(self.id, "id")
        self._optional_positive_int(self.session_id, "session_id")
        self._optional_positive_int(self.turn_id, "turn_id")
        self._optional_positive_int(self.context_revision, "context_revision")

        if not isinstance(self.player_input, str) or not self.player_input.strip():
            raise ValueError("player_input must not be empty")
        for field_name in ("adapter_namespace", "idempotency_key", "request_fingerprint"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if len(self.adapter_namespace) > 100:
            raise ValueError("adapter_namespace must not exceed 100 characters")
        if len(self.idempotency_key) > 500:
            raise ValueError("idempotency_key must not exceed 500 characters")
        if len(self.request_fingerprint) > 128:
            raise ValueError("request_fingerprint must not exceed 128 characters")
        if not isinstance(self.lifecycle_state, str) or self.lifecycle_state not in VALID_LIFECYCLE_STATES:
            raise ValueError("invalid lifecycle_state")
        if not isinstance(self.attempt_count, int) or isinstance(self.attempt_count, bool):
            raise TypeError("attempt_count must be an integer")
        if self.attempt_count < 0:
            raise ValueError("attempt_count must not be negative")
        if (self.lease_token is None) != (self.lease_expires_at is None):
            raise ValueError("lease_token and lease_expires_at must be set together")
        if self.lifecycle_state == "planning" and (
            self.lease_token is None or self.attempt_count < 1
        ):
            raise ValueError("planning state requires an active lease and attempt")
        if self.lifecycle_state == "prepared" and (
            self.context_revision is None or self.proposal_json is None
        ):
            raise ValueError("prepared state requires context_revision and proposal_json")
        if self.lifecycle_state in {"committed", "narration_pending", "completed"} and (
            self.committed_at is None
        ):
            raise ValueError("committed lifecycle states require committed_at")
        if self.lifecycle_state == "completed" and (
            self.completed_at is None or self.narrative is None
        ):
            raise ValueError("completed state requires narrative and completed_at")
        for field_name in (
            "proposal_json", "adjudication_json", "mechanics_json",
            "operation_results_json",
        ):
            value = getattr(self, field_name)
            if value is not None:
                if not isinstance(value, str):
                    raise TypeError(f"{field_name} must be a JSON string or None")
                try:
                    json.loads(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{field_name} must contain valid JSON") from exc
        for field_name in (
            "narrative", "lease_token", "lease_expires_at", "last_error_code",
            "created_at", "updated_at", "committed_at", "completed_at",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string or None")

    @staticmethod
    def _positive_int(value, field_name: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{field_name} must be an integer")
        if value < 1:
            raise ValueError(f"{field_name} must be greater than zero")

    @classmethod
    def _optional_positive_int(cls, value, field_name: str) -> None:
        if value is not None:
            cls._positive_int(value, field_name)

    def can_transition_to(self, target: str) -> bool:
        return target in self.TRANSITIONS[self.lifecycle_state]
