"""Durable native and external narration lifecycle management."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from database import transaction
from models.turn_record import TurnRecord
from models.turn_resolution_record import TurnResolutionRecord
from models.turn_resolution_result import TurnResolutionResult
from services.turns.durable_turn_result_mapper import DurableTurnResultMapper
from services.turns.turn_resolution_codec import TurnResolutionCodec


class DurableTurnNarrationService:
    """Own narration generation, external transcript versioning, and completion."""

    def __init__(
        self,
        *,
        scope,
        resolver,
        turn_repository,
        resolution_repository,
        turn_execution_lock=None,
        context_loader,
        error_type=RuntimeError,
    ) -> None:
        self.scope = scope
        self.resolver = resolver
        self.turn_repository = turn_repository
        self.resolution_repository = resolution_repository
        self.turn_execution_lock = turn_execution_lock
        self.context_loader = context_loader
        self.error_type = error_type

    def complete_external_narration(
        self,
        *,
        external_turn_id: str,
        player_input: str,
        narrative: str,
        turn_version: int,
    ) -> TurnResolutionResult:
        if not isinstance(external_turn_id, str) or not external_turn_id.strip():
            raise self.error_type("external_turn_id must not be empty")
        if not isinstance(player_input, str) or not player_input.strip():
            raise self.error_type("player_input must not be empty")
        if not isinstance(narrative, str) or not narrative.strip():
            raise self.error_type("narrative must not be empty")
        if not isinstance(turn_version, int) or isinstance(turn_version, bool) or turn_version < 1:
            raise self.error_type("turn_version must be a positive integer")

        def complete():
            return self._complete_external_narration_locked(
                external_turn_id=external_turn_id.strip(),
                player_input=player_input.strip(),
                narrative=narrative.strip(),
                turn_version=turn_version,
            )

        if self.turn_execution_lock is None:
            return complete()
        with self.turn_execution_lock.acquire():
            return complete()

    def _complete_external_narration_locked(
        self,
        *,
        external_turn_id: str,
        player_input: str,
        narrative: str,
        turn_version: int,
    ) -> TurnResolutionResult:
        record = self.resolution_repository.get_by_idempotency_key(
            "sillytavern", external_turn_id, scope=self.scope
        )
        active_turn = self.turn_repository.get_active_by_external_turn_id(
            external_turn_id, scope=self.scope
        )

        if record is not None and record.player_input != player_input:
            raise self.error_type(
                "external turn identity was reused with different player input"
            )

        if record is not None and record.lifecycle_state == "awaiting_input":
            raise self.error_type(
                "turn is awaiting player clarification and cannot be completed as narration"
            )

        if record is not None and record.lifecycle_state not in {
            "narration_pending",
            "completed",
        }:
            raise self.error_type(
                f"turn is not ready for narration: {record.lifecycle_state}"
            )

        previous_turn = active_turn
        if previous_turn is None and record is not None and record.turn_id is not None:
            previous_turn = self.turn_repository.get_turn(
                record.turn_id, scope=self.scope
            )

        existing_versions = self.turn_repository.get_versions_by_external_turn_id(
            external_turn_id, scope=self.scope
        )
        latest_version = max(
            (turn.version for turn in existing_versions),
            default=0,
        )

        if previous_turn is not None:
            if previous_turn.player_input != player_input:
                raise self.error_type(
                    "external turn identity was reused with different player input"
                )
            if turn_version == previous_turn.version:
                if previous_turn.narrative != narrative:
                    raise self.error_type(
                        "external turn version already exists with different content"
                    )
                if record is not None and record.lifecycle_state == "completed":
                    return self.result_from_completed_record(
                        record, previous_turn, already_processed=True
                    )
                return TurnResolutionResult.from_persisted_turn(previous_turn)
            if turn_version < previous_turn.version:
                raise self.error_type("external turn version is older than the active version")

        if turn_version != latest_version + 1:
            raise self.error_type(
                f"external turn version must be {latest_version + 1}"
            )

        if record is None and previous_turn is None:
            raise self.error_type(
                "no durable resolution exists for this external turn"
            )
        if record is None and previous_turn is None:
            raise RuntimeError("previous turn is required without a durable resolution")

        operation_results = (
            json.loads(record.operation_results_json or "[]")
            if record is not None
            else []
        )
        operation_count = (
            len(operation_results) if record is not None else previous_turn.operation_count
        )
        successful_count = (
            sum(1 for item in operation_results if item.get("success", False))
            if record is not None else previous_turn.successful_operation_count
        )
        failed_count = operation_count - successful_count
        world_changed = (
            any(item.get("changed", False) for item in operation_results)
            if record is not None else previous_turn.world_changed
        )
        session_id = (
            record.session_id if record is not None else previous_turn.session_id
        )
        turn = TurnRecord(
            session_id=session_id,
            player_input=player_input,
            narrative=narrative,
            operation_count=operation_count,
            successful_operation_count=successful_count,
            failed_operation_count=failed_count,
            all_operations_succeeded=(failed_count == 0),
            world_changed=world_changed,
            external_turn_id=external_turn_id,
            version=turn_version,
            status="active",
            snapshot=None,
        )

        with transaction("IMMEDIATE") as conn:
            current_active = self.turn_repository.get_active_by_external_turn_id(
                external_turn_id, scope=self.scope, conn=conn
            )
            current_versions = self.turn_repository.get_versions_by_external_turn_id(
                external_turn_id, scope=self.scope, conn=conn
            )
            current_latest_version = max(
                (turn.version for turn in current_versions),
                default=0,
            )
            if (
                current_active is not None
                and current_active.version >= turn_version
            ):
                if (
                    current_active.version == turn_version
                    and current_active.player_input == player_input
                    and current_active.narrative == narrative
                ):
                    if record is not None and record.lifecycle_state == "completed":
                        current_record = self.resolution_repository.get(
                            record.id, scope=self.scope, conn=conn
                        )
                        return self.result_from_completed_record(
                            current_record, current_active, already_processed=True
                        )
                    return TurnResolutionResult.from_persisted_turn(current_active)
                raise self.error_type(
                    "external turn version changed while narration was being saved"
                )
            if turn_version != current_latest_version + 1:
                raise self.error_type(
                    f"external turn version must be {current_latest_version + 1}"
                )
            if current_active is not None:
                self.turn_repository.supersede_turn(
                    current_active.id, scope=self.scope, conn=conn
                )
            saved_turn = self.turn_repository.save_turn(
                turn, scope=self.scope, conn=conn
            )
            if record is not None and record.lifecycle_state == "narration_pending":
                self.resolution_repository.transition(
                    record.id,
                    "completed",
                    scope=self.scope,
                    expected_state="narration_pending",
                    updates={
                        "turn_id": saved_turn.id,
                        "narrative": narrative,
                        "completed_at": datetime.now(UTC).isoformat(),
                    },
                    conn=conn,
                )
            elif record is not None:
                self.resolution_repository.update_completed_projection(
                    record.id,
                    turn_id=saved_turn.id,
                    narrative=narrative,
                    scope=self.scope,
                    conn=conn,
                )

        if record is None:
            return TurnResolutionResult.from_persisted_turn(saved_turn)
        completed = self.resolution_repository.get(record.id, scope=self.scope)
        return self.result_from_completed_record(
            completed, saved_turn, already_processed=(turn_version > 1)
        )

    def result_from_completed_record(
        self,
        record: TurnResolutionRecord,
        turn: TurnRecord,
        *,
        already_processed: bool,
    ) -> TurnResolutionResult:
        mapper = DurableTurnResultMapper(
            self.resolver.extractor.operation_parser
        )
        return mapper.from_completed_record(
            record,
            turn,
            already_processed=already_processed,
        )

    @staticmethod
    def _resolved_player_input(record: TurnResolutionRecord) -> str:
        adjudication = json.loads(record.adjudication_json or "{}")
        return adjudication.get("resolved_player_input", record.player_input)

    def resume_narration(
        self,
        record: TurnResolutionRecord,
        *,
        already_processed: bool,
    ):
        if record.lifecycle_state == "committed":
            with transaction("IMMEDIATE") as conn:
                record = self.resolution_repository.transition(
                    record.id,
                    "narration_pending",
                    scope=self.scope,
                    expected_state="committed",
                    conn=conn,
                )
        if record.lifecycle_state != "narration_pending":
            raise self.error_type("resolution is not awaiting narration")

        with transaction("DEFERRED") as conn:
            context, recent = self.context_loader(conn)
        mechanics_result = TurnResolutionCodec.mechanics_from_json(record.mechanics_json)
        resolved_player_input = self._resolved_player_input(record)
        committed_resolution = json.dumps(
            {
                "context_revision": record.context_revision,
                "resulting_revision": record.resulting_revision,
                "operations": json.loads(
                    record.proposal_json or '{"operations":[]}'
                )["operations"],
                "operation_results": json.loads(
                    record.operation_results_json or "[]"
                ),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        narrative = self.resolver.generate_narrative(
            context,
            resolved_player_input,
            recent_turns=recent,
            mechanics_result=mechanics_result,
            committed_resolution=committed_resolution,
        )
        if not narrative:
            raise self.error_type("DMService returned an empty narrative")

        with transaction("IMMEDIATE") as conn:
            turn = self.turn_repository.save_turn(
                TurnRecord(
                    session_id=record.session_id,
                    player_input=resolved_player_input,
                    narrative=narrative,
                    operation_count=len(
                        json.loads(record.operation_results_json or "[]")
                    ),
                    successful_operation_count=len(
                        json.loads(record.operation_results_json or "[]")
                    ),
                    failed_operation_count=0,
                    all_operations_succeeded=True,
                    world_changed=any(
                        item.get("changed", False)
                        for item in json.loads(record.operation_results_json or "[]")
                    ),
                ),
                scope=self.scope,
                conn=conn,
            )
            self.resolution_repository.transition(
                record.id,
                "completed",
                scope=self.scope,
                expected_state="narration_pending",
                updates={
                    "turn_id": turn.id,
                    "narrative": narrative,
                    "completed_at": datetime.now(UTC).isoformat(),
                },
                conn=conn,
            )
        completed = self.resolution_repository.get(
            record.id, scope=self.scope
        )
        completed_turn = self.turn_repository.get_turn(
            completed.turn_id, scope=self.scope
        )
        return self.result_from_completed_record(
            completed, completed_turn, already_processed=already_processed
        )
