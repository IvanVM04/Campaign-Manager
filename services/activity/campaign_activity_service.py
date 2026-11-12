from __future__ import annotations

from models.activity_event import ActivityEvent
from models.activity_read_models import ActivityEventPage, ActivityEventRead
from models.campaign_scope import CampaignScope
from observability.log_context import current_request_id
from repositories.activity_event_repository import ActivityEventRepository


class CampaignActivityService:
    """Writes a fixed, safe activity vocabulary and reads player-facing pages."""

    def __init__(
        self,
        *,
        scope: CampaignScope,
        repository: ActivityEventRepository | None = None,
    ) -> None:
        if not isinstance(scope, CampaignScope):
            raise TypeError("scope must be a CampaignScope")
        self.scope = scope
        self.repository = repository or ActivityEventRepository()

    def record_turn_accepted(self, record, *, dice_mode: str, conn) -> None:
        self._record(
            record,
            event_type="turn.accepted",
            summary="Turn accepted",
            details={
                "adapter": record.adapter_namespace,
                "dice_mode": dice_mode,
            },
            dedupe_key=f"resolution:{self._resolution_id(record)}:accepted",
            conn=conn,
        )

    def record_turn_awaiting_input(
        self,
        record,
        *,
        challenge_type: str,
        conn,
    ) -> None:
        if challenge_type not in {"manual_roll", "clarification"}:
            raise ValueError("unsupported activity challenge type")
        self._record(
            record,
            event_type="turn.awaiting_input",
            summary=(
                "Waiting for a manual roll"
                if challenge_type == "manual_roll"
                else "Waiting for clarification"
            ),
            details={"challenge_type": challenge_type},
            dedupe_key=(
                f"resolution:{self._resolution_id(record)}:awaiting:"
                f"{record.attempt_count}:{challenge_type}"
            ),
            conn=conn,
        )

    def record_turn_committed(self, record, result, *, conn) -> None:
        operation_results = tuple(result.operation_results)
        successful = sum(1 for item in operation_results if item.success)
        failed = len(operation_results) - successful
        self._record(
            record,
            event_type="turn.committed",
            summary="World changes committed",
            details={
                "operation_count": len(operation_results),
                "successful_operation_count": successful,
                "failed_operation_count": failed,
                "world_changed": bool(result.world_changed),
            },
            dedupe_key=f"resolution:{self._resolution_id(record)}:committed",
            conn=conn,
        )

    def record_turn_completed(self, record, turn, *, conn) -> None:
        version = int(getattr(turn, "version", 1) or 1)
        self._record(
            record,
            event_type="turn.completed",
            summary="Turn completed",
            details={"turn_version": version},
            dedupe_key=f"resolution:{self._resolution_id(record)}:completed:{version}",
            turn_id=turn.id,
            session_id=turn.session_id,
            conn=conn,
        )

    def record_turn_failed(
        self,
        record,
        *,
        error_code: str,
        retryable: bool,
        conn,
    ) -> None:
        safe_code = error_code[:80] if isinstance(error_code, str) and error_code else "planning_failed"
        self._record(
            record,
            event_type="turn.failed",
            summary="Turn planning failed",
            details={
                "error_code": safe_code,
                "retryable": bool(retryable),
            },
            dedupe_key=(
                f"resolution:{self._resolution_id(record)}:failed:"
                f"{record.attempt_count}:{safe_code}"
            ),
            conn=conn,
        )

    def list_activity(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        resolution_id: int | None = None,
        session_id: int | None = None,
        event_type: str | None = None,
    ) -> ActivityEventPage:
        events = self.repository.list_events(
            scope=self.scope,
            limit=limit,
            offset=offset,
            resolution_id=resolution_id,
            session_id=session_id,
            event_type=event_type,
        )
        total = self.repository.count_events(
            scope=self.scope,
            resolution_id=resolution_id,
            session_id=session_id,
            event_type=event_type,
        )
        return ActivityEventPage(
            items=tuple(
                ActivityEventRead(
                    id=event.id,
                    resolution_id=event.resolution_id,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    event_type=event.event_type,
                    summary=event.summary,
                    details=event.details,
                    occurred_at=event.occurred_at or "",
                )
                for event in events
                if event.id is not None
            ),
            total=total,
            limit=limit,
            offset=offset,
        )

    def _record(
        self,
        record,
        *,
        event_type: str,
        summary: str,
        details: dict[str, object],
        dedupe_key: str,
        conn,
        turn_id: int | None = None,
        session_id: int | None = None,
    ) -> None:
        self.repository.create(
            ActivityEvent(
                campaign_id=self.scope.campaign_id,
                resolution_id=self._resolution_id(record),
                session_id=(
                    session_id
                    if session_id is not None
                    else record.session_id
                ),
                turn_id=turn_id,
                event_type=event_type,
                summary=summary,
                details=details,
                request_id=current_request_id(),
                dedupe_key=dedupe_key,
            ),
            scope=self.scope,
            conn=conn,
        )

    @staticmethod
    def _resolution_id(record) -> int:
        if record.id is None:
            raise ValueError("activity requires a persisted resolution")
        return record.id
