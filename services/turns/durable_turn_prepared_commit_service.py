"""Atomic commit boundary for prepared durable turn resolutions."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime

from database import transaction
from services.turns.durable_turn_errors import (
    DurableTurnCommitError,
    DurableTurnErrorCode,
)


class DurableTurnPreparedCommitService:
    """Validate a prepared plan against current campaign state and commit it once.

    Planning and challenge-specific input collection stay with the caller. This
    service owns the shared transactional boundary that applies consequences
    and advances a prepared resolution to narration_pending.
    """

    def __init__(
        self,
        *,
        scope,
        resolver,
        revision_repository,
        resolution_repository,
        context_loader,
        operation_results_serializer,
        world_service=None,
        turn_execution_lock=None,
        error_type=RuntimeError,
    ) -> None:
        self.scope = scope
        self.resolver = resolver
        self.revision_repository = revision_repository
        self.resolution_repository = resolution_repository
        self.context_loader = context_loader
        self.operation_results_serializer = operation_results_serializer
        self.world_service = world_service
        self.turn_execution_lock = turn_execution_lock
        self.error_type = error_type

    def commit_prepared_plan(
        self,
        record,
        plan,
        *,
        context,
        recent,
        revision,
        revision_error_message,
        context_error_message,
        conversation_id: str | None = None,
    ):
        """Revalidate and atomically apply a plan from an isolated snapshot.

        The campaign lock covers only the authoritative commit and cache
        publication. Snapshot reads and all provider inference happen outside it.
        """
        lock_scope = (
            self.turn_execution_lock.acquire()
            if self.turn_execution_lock is not None
            else nullcontext()
        )
        isolated_world_service = None
        with lock_scope:
            with transaction("IMMEDIATE") as conn:
                current_revision = self.revision_repository.get_revision(
                    self.scope.campaign_id,
                    conn=conn,
                )
                if current_revision != revision:
                    raise DurableTurnCommitError(
                        revision_error_message,
                        code=DurableTurnErrorCode.STALE_CONTEXT,
                    )

                current_context, current_recent = self.context_loader(
                    conn, conversation_id=conversation_id
                )
                if current_context != context or current_recent != recent:
                    raise DurableTurnCommitError(
                        context_error_message,
                        code=DurableTurnErrorCode.STALE_CONTEXT,
                    )

                if self.world_service is None:
                    result = self.resolver.apply_plan(
                        current_context, plan, conn=conn
                    )
                else:
                    isolated_world_service = self.world_service.isolated_copy(
                        current_context.world
                    )
                    result = self.resolver.apply_plan(
                        current_context,
                        plan,
                        conn=conn,
                        world_service=isolated_world_service,
                    )
                if not result.all_operations_succeeded:
                    raise DurableTurnCommitError(
                        "one or more proposed consequences failed validation",
                        code=DurableTurnErrorCode.CONSEQUENCE_VALIDATION_FAILED,
                    )

                resulting_revision = self.revision_repository.get_revision(
                    self.scope.campaign_id,
                    conn=conn,
                )
                self.resolution_repository.transition(
                    record.id,
                    "committed",
                    scope=self.scope,
                    expected_state="prepared",
                    updates={
                        "resulting_revision": resulting_revision,
                        "operation_results_json": self.operation_results_serializer(
                            result
                        ),
                        "committed_at": datetime.now(UTC).isoformat(),
                    },
                    conn=conn,
                )
                self.resolution_repository.transition(
                    record.id,
                    "narration_pending",
                    scope=self.scope,
                    expected_state="committed",
                    conn=conn,
                )

            # Publish only after SQLite has committed. A failed/rolled-back
            # isolated application must never replace the shared world cache.
            if isolated_world_service is not None:
                self.world_service.publish_snapshot(isolated_world_service.world)

        return self.resolution_repository.get(record.id, scope=self.scope)
