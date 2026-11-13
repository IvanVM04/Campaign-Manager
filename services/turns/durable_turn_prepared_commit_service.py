"""Atomic commit boundary for prepared durable turn resolutions."""

from __future__ import annotations

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
        error_type=RuntimeError,
    ) -> None:
        self.scope = scope
        self.resolver = resolver
        self.revision_repository = revision_repository
        self.resolution_repository = resolution_repository
        self.context_loader = context_loader
        self.operation_results_serializer = operation_results_serializer
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
        """Apply a prepared plan only if its campaign snapshot is still current."""
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

            result = self.resolver.apply_plan(current_context, plan, conn=conn)
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

        return self.resolution_repository.get(record.id, scope=self.scope)
