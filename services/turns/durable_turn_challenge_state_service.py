"""Read-only projections for durable player challenge state."""

from __future__ import annotations

import json


class DurableTurnChallengeStateService:
    """Build safe, adapter-scoped views of persisted challenge state.

    Challenge submissions remain coordinated by DurableNativeTurnService because
    they participate in planning leases and atomic consequence commits. This
    collaborator owns only the read/projection boundary used by clients to
    recover pending clarification and manual-roll challenges.
    """

    def __init__(
        self,
        *,
        scope,
        turn_repository,
        resolution_repository,
        error_type=ValueError,
    ) -> None:
        self.scope = scope
        self.turn_repository = turn_repository
        self.resolution_repository = resolution_repository
        self.error_type = error_type

    def get_external_clarification_state(self, external_turn_id: str) -> dict:
        """Return the durable clarification envelope for a SillyTavern turn."""
        if not isinstance(external_turn_id, str):
            raise self.error_type("external_turn_id must be a string")
        external_turn_id = external_turn_id.strip()
        if not external_turn_id or len(external_turn_id) > 500:
            raise self.error_type(
                "external_turn_id must contain 1-500 characters"
            )

        record = self.resolution_repository.get_by_idempotency_key(
            "sillytavern", external_turn_id, scope=self.scope
        )
        if record is None:
            return {
                "external_turn_id": external_turn_id,
                "has_clarification": False,
                "lifecycle_state": None,
            }

        adjudication = json.loads(record.adjudication_json or "{}")
        clarification = adjudication.get("clarification")
        history = adjudication.get("clarification_history", [])
        active_challenge_id = (
            clarification.get("challenge_id")
            if isinstance(clarification, dict)
            else None
        )
        last_challenge_id = adjudication.get("last_challenge_id")
        has_clarification = bool(
            isinstance(clarification, dict) or history or last_challenge_id
        )
        active_turn = self.turn_repository.get_active_by_external_turn_id(
            external_turn_id, scope=self.scope
        )

        return {
            "external_turn_id": external_turn_id,
            "has_clarification": has_clarification,
            "lifecycle_state": record.lifecycle_state,
            "player_input": record.player_input,
            "clarification_question": (
                clarification.get("question")
                if isinstance(clarification, dict)
                and record.lifecycle_state == "awaiting_input"
                else None
            ),
            "pending_clarification_id": (
                f"{record.id}:{active_challenge_id}"
                if record.lifecycle_state in {"awaiting_input", "planning"}
                and active_challenge_id
                else None
            ),
            "last_pending_clarification_id": (
                f"{record.id}:{last_challenge_id}" if last_challenge_id else None
            ),
            "last_answer": adjudication.get("last_answer"),
            "last_answer_external_turn_id": adjudication.get(
                "last_answer_external_turn_id"
            ),
            "resolved_player_input": adjudication.get("resolved_player_input"),
            "narrative": active_turn.narrative if active_turn is not None else None,
        }

    def get_external_manual_roll_state(self, external_turn_id: str) -> dict:
        """Return a sanitized manual-roll challenge envelope for SillyTavern."""
        if not isinstance(external_turn_id, str) or not external_turn_id.strip():
            raise self.error_type("external_turn_id must not be empty")
        external_turn_id = external_turn_id.strip()
        record = self.resolution_repository.get_by_idempotency_key(
            "sillytavern", external_turn_id, scope=self.scope
        )
        if record is None:
            return {"external_turn_id": external_turn_id, "has_manual_roll": False}

        state = json.loads(record.adjudication_json or "{}")
        pending = state.get("manual_roll")
        submitted_external_turn_id = (
            pending.get("submitted_external_turn_id")
            if isinstance(pending, dict)
            else None
        )
        active = isinstance(pending, dict) and (
            record.lifecycle_state
            in {
                "awaiting_input",
                "planning",
                "prepared",
                "committed",
                "narration_pending",
            }
            or (
                record.lifecycle_state == "completed"
                and isinstance(submitted_external_turn_id, str)
                and bool(submitted_external_turn_id)
            )
        )
        return {
            "external_turn_id": external_turn_id,
            "has_manual_roll": active,
            "lifecycle_state": record.lifecycle_state,
            "player_input": record.player_input,
            "submitted_external_turn_id": (
                submitted_external_turn_id if active else None
            ),
            "pending_roll_id": (
                f"{record.id}:{pending['challenge_id']}" if active else None
            ),
            "pending_roll": (
                {
                    key: value
                    for key, value in pending.items()
                    if key
                    not in {
                        "challenge_id",
                        "decision",
                        "submitted_rolls",
                        "submitted_external_turn_id",
                    }
                }
                if active
                else None
            ),
        }
