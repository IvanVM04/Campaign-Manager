from __future__ import annotations

import json

from models.operation_result import OperationResult, OperationStatus
from models.turn_record import TurnRecord
from models.turn_resolution_record import TurnResolutionRecord
from models.turn_resolution_result import TurnResolutionResult
from operations.character_operations import CharacterOperation
from operations.referenced_operation import ReferencedOperation
from operations.turn_operations import TurnOperation
from operations.world_operations import WorldOperation
from services.turns.turn_resolution_codec import TurnResolutionCodec


class DurableTurnResultMapper:
    """Reconstruct the public result model from a completed durable record."""

    def __init__(self, operation_parser) -> None:
        self.operation_parser = operation_parser

    @staticmethod
    def _unwrap(raw: TurnOperation | ReferencedOperation) -> TurnOperation:
        return raw.operation if isinstance(raw, ReferencedOperation) else raw

    @classmethod
    def _character_operation(
        cls, raw: TurnOperation | ReferencedOperation
    ) -> CharacterOperation | None:
        operation = cls._unwrap(raw)
        return operation if isinstance(operation, CharacterOperation) else None

    def from_completed_record(
        self,
        record: TurnResolutionRecord,
        turn: TurnRecord,
        *,
        already_processed: bool,
    ) -> TurnResolutionResult:
        parsed = self.operation_parser.parse(
            record.proposal_json or '{"operations":[]}'
        )
        world_operations = tuple(
            operation
            for raw in parsed
            if isinstance((operation := self._unwrap(raw)), WorldOperation)
        )
        character_operations = tuple(
            operation
            for raw in parsed
            if (operation := self._character_operation(raw)) is not None
        )
        stored_results = json.loads(record.operation_results_json or "[]")
        operation_results = tuple(
            OperationResult(
                status=OperationStatus(item["status"]),
                message=item.get("message", ""),
                operation=(
                    self._unwrap(parsed[index]) if index < len(parsed) else None
                ),
            )
            for index, item in enumerate(stored_results)
        )
        return TurnResolutionResult(
            player_input=turn.player_input,
            narrative=turn.narrative,
            operations=world_operations,
            character_operations=character_operations,
            operation_results=operation_results,
            mechanics_result=TurnResolutionCodec.mechanics_from_json(
                record.mechanics_json
            ),
            already_processed=already_processed,
            persisted_operation_count=turn.operation_count,
            persisted_successful_operation_count=turn.successful_operation_count,
            persisted_failed_operation_count=turn.failed_operation_count,
            persisted_all_operations_succeeded=turn.all_operations_succeeded,
            persisted_world_changed=turn.world_changed,
        )

    @staticmethod
    def manual_roll_result(record, pending) -> TurnResolutionResult:
        return TurnResolutionResult(
            player_input=record.player_input,
            narrative="",
            pending_roll_id=str(record.id) + ":" + pending["challenge_id"],
            pending_roll={
                key: value
                for key, value in pending.items()
                if key not in {"challenge_id", "decision"}
            },
        )

    @staticmethod
    def clarification_result(record, pending) -> TurnResolutionResult:
        return TurnResolutionResult(
            player_input=record.player_input,
            narrative=pending["question"],
            pending_clarification_id=(
                str(record.id) + ":" + pending["challenge_id"]
            ),
        )

