"""Durable state-machine orchestration for compound v3 player actions.

The orchestrator owns sequencing only. Action execution is delegated to a
backend adapter that uses the rules engine and returns an authoritative
ActionOutcome. Persistence is lease-fenced/CAS by the caller. Adapter errors
are infrastructure failures, never gameplay failures, and retries keep the
same execution key.
"""
from __future__ import annotations

import enum
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

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


_ALLOWED_ACTION_PROGRESS_FIELDS = frozenset(
    {"proposal_json", "intent_json", "adjudication_json", "mechanics_json"}
)
_MAX_ACTION_PROGRESS_BYTES = 131_072


@dataclass(frozen=True, slots=True)
class CompoundActionExecution:
    """Authoritative result plus JSON progress to persist with its checkpoint.

    Progress fields are intentionally limited to the same durable columns
    accepted by TurnResolutionRepository.save_action_checkpoint. Values are
    validated before the orchestrator lets the checkpoint persister commit
    them in the same CAS update.
    """

    outcome: ActionOutcome
    progress_updates: Mapping[str, str | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ActionOutcome):
            raise TypeError("outcome must be an authoritative ActionOutcome")
        if not isinstance(self.progress_updates, Mapping):
            raise TypeError("progress_updates must be a mapping")
        updates = dict(self.progress_updates)
        unknown = set(updates) - _ALLOWED_ACTION_PROGRESS_FIELDS
        if unknown:
            raise ValueError("progress_updates contains a protected field")
        for name, value in updates.items():
            if value is None:
                continue
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a JSON string or None")
            if len(value.encode("utf-8")) > _MAX_ACTION_PROGRESS_BYTES:
                raise ValueError(f"{name} exceeds its progress byte budget")
            try:
                json.loads(value)
            except (TypeError, ValueError):
                raise ValueError(f"{name} must contain valid JSON") from None
        object.__setattr__(
            self,
            "progress_updates",
            MappingProxyType(updates),
        )


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


ActionExecutor = Callable[
    [GameplayActionCandidate, str, bool],
    CompoundActionExecution,
]
# One-argument callbacks remain valid when there are no staged progress
# updates; callbacks that receive updates must save both values atomically.
CheckpointPersister = Callable[..., None]


class V3CompoundActionOrchestrator:
    """Execute the v3 action graph one node at a time with durable transitions.

    persist_checkpoint must save with the active planning lease and compare-
    and-swap against the previous checkpoint. Where an executor produces
    staged consequences, the caller must save that progress in the same
    transaction as the checkpoint transition.

    The executor must be idempotent for the supplied execution key. This makes
    a crash after execution but before recording the outcome recoverable.
    Its CompoundActionExecution.progress_updates are passed to the persister
    together with the RESOLVED checkpoint so proposal/mechanics state and the
    authoritative outcome share one repository CAS transaction.
    """

    @staticmethod
    def _persist(
        persist_checkpoint: CheckpointPersister,
        checkpoint: PlayerActionCheckpoint,
        progress_updates: Mapping[str, str | None] | None = None,
    ) -> None:
        updates = None if not progress_updates else dict(progress_updates)
        if updates is None:
            persist_checkpoint(checkpoint)
        else:
            persist_checkpoint(checkpoint, updates)

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
                self._persist(persist_checkpoint, selection.checkpoint)
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
            self._persist(persist_checkpoint, current)

            try:
                execution = execute(candidate, execution_key, resumed)
                if not isinstance(execution, CompoundActionExecution):
                    raise TypeError(
                        "action executor must return CompoundActionExecution"
                    )
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
        self._persist(persist_checkpoint, resumed.checkpoint)
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
