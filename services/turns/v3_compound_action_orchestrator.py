"""Durable state-machine orchestration for compound v3 player actions.

The orchestrator owns sequencing only. Action execution is delegated to a
backend adapter that uses the rules engine and returns an authoritative
ActionOutcome. Persistence is lease-fenced/CAS by the caller. Adapter errors
are infrastructure failures, never gameplay failures, and retries keep the
same execution key.
"""
from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass

from models.player_action_checkpoint import (
    ActionOutcome,
    PlayerActionCheckpoint,
)
from models.player_turn_interpretation_v3 import GameplayActionCandidate
from services.turns.player_action_selector import (
    ActionSelectionStatus,
    ClarificationResumeResult,
    mark_action_completed,
    mark_action_execution_failed,
    mark_action_started,
    resume_after_clarification,
    select_next_action,
)


class CompoundActionRunStatus(str, enum.Enum):
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    BLOCKED_BY_DEPENDENCY = "blocked_by_dependency"
    EXECUTION_FAILED = "execution_failed"


@dataclass(frozen=True, slots=True)
class CompoundActionAttempt:
    """One attempted node, including its stable idempotency identity."""

    event_id: str
    execution_key: str
    resumed: bool
    outcome: ActionOutcome | None


@dataclass(frozen=True, slots=True)
class CompoundActionRunResult:
    """Checkpoint and next required interaction after one orchestration pass."""

    checkpoint: PlayerActionCheckpoint
    status: CompoundActionRunStatus
    attempts: tuple[CompoundActionAttempt, ...] = ()
    candidate: GameplayActionCandidate | None = None
    event_id: str | None = None
    clarification_slots: tuple[str, ...] = ()
    technical_error_type: str | None = None
    affected_descendant_event_ids: tuple[str, ...] = ()


ActionExecutor = Callable[[GameplayActionCandidate, str, bool], ActionOutcome]
CheckpointPersister = Callable[[PlayerActionCheckpoint], None]


class V3CompoundActionOrchestrator:
    """Execute the v3 action graph one node at a time with durable transitions.

    persist_checkpoint must save with the active planning lease and compare-
    and-swap against the previous checkpoint. Where an executor produces
    staged consequences, the caller must save that progress in the same
    transaction as the checkpoint transition.

    The executor must be idempotent for the supplied execution key. This makes
    a crash after execution but before recording the outcome recoverable.
    """

    def run(
        self,
        checkpoint: PlayerActionCheckpoint,
        *,
        execute: ActionExecutor,
        persist_checkpoint: CheckpointPersister,
    ) -> CompoundActionRunResult:
        if not isinstance(checkpoint, PlayerActionCheckpoint):
            raise TypeError("checkpoint must be a PlayerActionCheckpoint")
        if not callable(execute):
            raise TypeError("execute must be callable")
        if not callable(persist_checkpoint):
            raise TypeError("persist_checkpoint must be callable")

        current = checkpoint
        attempts: list[CompoundActionAttempt] = []

        while True:
            selection = select_next_action(current)
            if selection.checkpoint != current:
                # Selection may mark a failed dependency branch SKIPPED.
                # That state change is durable even without a new action.
                persist_checkpoint(selection.checkpoint)
                current = selection.checkpoint

            if selection.status is ActionSelectionStatus.EXHAUSTED:
                return CompoundActionRunResult(
                    checkpoint=current,
                    status=CompoundActionRunStatus.COMPLETED,
                    attempts=tuple(attempts),
                )
            if selection.status is ActionSelectionStatus.NEEDS_CLARIFICATION:
                candidate = selection.candidate
                return CompoundActionRunResult(
                    checkpoint=current,
                    status=CompoundActionRunStatus.NEEDS_CLARIFICATION,
                    attempts=tuple(attempts),
                    candidate=candidate,
                    event_id=candidate.source_event_id if candidate else None,
                    clarification_slots=selection.clarification_slots,
                )
            if selection.status is ActionSelectionStatus.BLOCKED_BY_DEPENDENCY:
                candidate = selection.candidate
                return CompoundActionRunResult(
                    checkpoint=current,
                    status=CompoundActionRunStatus.BLOCKED_BY_DEPENDENCY,
                    attempts=tuple(attempts),
                    candidate=candidate,
                    event_id=candidate.source_event_id if candidate else None,
                )

            candidate = selection.candidate
            event_id = candidate.source_event_id if candidate is not None else None
            if candidate is None or event_id is None or selection.execution_key is None:
                raise RuntimeError("ready action selection is missing its identity")

            current, execution_key, resumed = mark_action_started(current, event_id)
            # Persist IN_PROGRESS before invoking mechanics or any other
            # execution adapter. A failed save must prevent the action call.
            persist_checkpoint(current)

            try:
                outcome = execute(candidate, execution_key, resumed)
                if not isinstance(outcome, ActionOutcome):
                    raise TypeError("action executor must return ActionOutcome")
            except Exception as exc:  # noqa: BLE001 - adapter errors are technical
                current = mark_action_execution_failed(current, event_id)
                persist_checkpoint(current)
                attempts.append(
                    CompoundActionAttempt(
                        event_id=event_id,
                        execution_key=execution_key,
                        resumed=resumed,
                        outcome=None,
                    )
                )
                return CompoundActionRunResult(
                    checkpoint=current,
                    status=CompoundActionRunStatus.EXECUTION_FAILED,
                    attempts=tuple(attempts),
                    candidate=candidate,
                    event_id=event_id,
                    technical_error_type=type(exc).__name__,
                )

            current = mark_action_completed(current, event_id, outcome)
            # If this write fails, leave the durable node IN_PROGRESS. On
            # retry, the same key lets the adapter replay instead of reapply.
            persist_checkpoint(current)
            attempts.append(
                CompoundActionAttempt(
                    event_id=event_id,
                    execution_key=execution_key,
                    resumed=resumed,
                    outcome=outcome,
                )
            )

    def resume_after_clarification(
        self,
        checkpoint: PlayerActionCheckpoint,
        event_id: str,
        updated_candidate: GameplayActionCandidate,
        *,
        clarification_slots: tuple[str, ...] = (),
        execute: ActionExecutor,
        persist_checkpoint: CheckpointPersister,
    ) -> tuple[ClarificationResumeResult, CompoundActionRunResult]:
        """Apply one backend-resolved clarification, then continue the graph."""
        if not callable(persist_checkpoint):
            raise TypeError("persist_checkpoint must be callable")
        resumed = resume_after_clarification(
            checkpoint,
            event_id,
            updated_candidate,
            clarification_slots=clarification_slots,
        )
        persist_checkpoint(resumed.checkpoint)
        result = self.run(
            resumed.checkpoint,
            execute=execute,
            persist_checkpoint=persist_checkpoint,
        )
        return (
            resumed,
            CompoundActionRunResult(
                checkpoint=result.checkpoint,
                status=result.status,
                attempts=result.attempts,
                candidate=result.candidate,
                event_id=result.event_id,
                clarification_slots=result.clarification_slots,
                technical_error_type=result.technical_error_type,
                affected_descendant_event_ids=resumed.affected_descendant_event_ids,
            ),
        )
