from __future__ import annotations

import json
from dataclasses import dataclass

from models.turn_resolution_record import TurnResolutionRecord


@dataclass(frozen=True, slots=True)
class DurableTurnPreparation:
    """Committed resolution evidence awaiting an adapter-generated narrative."""

    resolution_id: int | None
    lifecycle_state: str
    player_input: str
    committed_resolution: str
    clarification_question: str | None = None
    pending_clarification_id: str | None = None
    legacy_replay: bool = False
    pending_roll_id: str | None = None
    pending_roll: dict | None = None


class DurableTurnPreparationMapper:
    """Build adapter-facing preparation data from committed resolution records."""

    @staticmethod
    def committed_resolution_json(record: TurnResolutionRecord) -> str:
        return json.dumps(
            {
                "resolution_id": record.id,
                "lifecycle_state": record.lifecycle_state,
                "context_revision": record.context_revision,
                "resulting_revision": record.resulting_revision,
                "operations": json.loads(
                    record.proposal_json or '{"operations":[]}'
                )["operations"],
                "operation_results": json.loads(
                    record.operation_results_json or "[]"
                ),
                "mechanics": json.loads(record.mechanics_json)
                if record.mechanics_json else None,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def from_record(
        cls,
        record: TurnResolutionRecord,
    ) -> DurableTurnPreparation:
        question = None
        clarification = None
        pending_roll_id = None
        pending_roll = None
        if record.lifecycle_state == "awaiting_input":
            pending = json.loads(record.adjudication_json or "{}")
            manual_roll = pending.get("manual_roll")
            if isinstance(manual_roll, dict):
                pending_roll_id = str(record.id) + ":" + manual_roll["challenge_id"]
                pending_roll = {
                    key: value for key, value in manual_roll.items()
                    if key not in {"challenge_id", "decision", "submitted_rolls"}
                }
            clarification = pending.get("clarification")
            question = (
                clarification.get("question")
                if isinstance(clarification, dict)
                else pending.get("clarification_question")
            )
        return DurableTurnPreparation(
            resolution_id=record.id,
            lifecycle_state=record.lifecycle_state,
            player_input=record.player_input,
            committed_resolution=cls.committed_resolution_json(record),
            clarification_question=question,
            pending_clarification_id=(
                str(record.id) + ":" + clarification["challenge_id"]
                if isinstance(clarification, dict)
                else None
            ),
            pending_roll_id=pending_roll_id,
            pending_roll=pending_roll,
        )
