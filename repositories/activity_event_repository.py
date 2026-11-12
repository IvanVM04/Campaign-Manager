from __future__ import annotations

import json

from database import get_conn, one_in_conn, rows_in_conn
from models.activity_event import ActivityEvent, ACTIVITY_EVENT_TYPES
from models.campaign_scope import CampaignScope


class ActivityEventRepository:
    """Persists safe activity events and exposes campaign-scoped pages."""

    @staticmethod
    def _validate_scope(scope: CampaignScope) -> None:
        if not isinstance(scope, CampaignScope):
            raise TypeError("scope must be a CampaignScope")

    @staticmethod
    def _row_to_model(row: dict) -> ActivityEvent:
        return ActivityEvent(
            id=row["id"],
            campaign_id=row["campaign_id"],
            resolution_id=row["resolution_id"],
            session_id=row["session_id"],
            turn_id=row["turn_id"],
            event_type=row["event_type"],
            summary=row["summary"],
            details=json.loads(row["details_json"] or "{}"),
            request_id=row["request_id"],
            dedupe_key=row["dedupe_key"],
            occurred_at=row["occurred_at"],
        )

    def create(
        self,
        event: ActivityEvent,
        *,
        scope: CampaignScope,
        conn=None,
    ) -> ActivityEvent:
        self._validate_scope(scope)
        if not isinstance(event, ActivityEvent):
            raise TypeError("event must be an ActivityEvent")
        if event.campaign_id != scope.campaign_id:
            raise ValueError("activity event campaign does not match scope")
        query = """
            INSERT INTO campaign_activity_events (
                campaign_id, resolution_id, session_id, turn_id,
                event_type, summary, details_json, request_id, dedupe_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (campaign_id, dedupe_key) DO NOTHING
        """
        params = (
            event.campaign_id,
            event.resolution_id,
            event.session_id,
            event.turn_id,
            event.event_type,
            event.summary,
            json.dumps(
                event.details,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            event.request_id,
            event.dedupe_key,
        )

        def insert(connection):
            connection.execute(query, params)
            row = one_in_conn(
                connection,
                """
                SELECT id, campaign_id, resolution_id, session_id, turn_id,
                       event_type, summary, details_json, request_id, dedupe_key,
                       occurred_at
                FROM campaign_activity_events
                WHERE campaign_id = ? AND dedupe_key = ?
                """,
                (scope.campaign_id, event.dedupe_key),
            )
            if row is None:
                raise RuntimeError("activity event disappeared after insert")
            return self._row_to_model(row)

        if conn is not None:
            return insert(conn)
        with get_conn() as connection:
            return insert(connection)

    def list_events(
        self,
        *,
        scope: CampaignScope,
        limit: int = 50,
        offset: int = 0,
        resolution_id: int | None = None,
        session_id: int | None = None,
        event_type: str | None = None,
        conn=None,
    ) -> tuple[ActivityEvent, ...]:
        self._validate_scope(scope)
        self._validate_pagination(limit, offset)
        self._validate_optional_id(resolution_id, "resolution_id")
        self._validate_optional_id(session_id, "session_id")
        if event_type is not None and event_type not in ACTIVITY_EVENT_TYPES:
            raise ValueError("unsupported activity event type")

        where, params = self._filters(
            scope.campaign_id,
            resolution_id=resolution_id,
            session_id=session_id,
            event_type=event_type,
        )
        query = f"""
            SELECT id, campaign_id, resolution_id, session_id, turn_id,
                   event_type, summary, details_json, request_id, dedupe_key,
                   occurred_at
            FROM campaign_activity_events
            WHERE {where}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """

        def select(connection):
            return tuple(
                self._row_to_model(row)
                for row in rows_in_conn(connection, query, (*params, limit, offset))
            )

        if conn is not None:
            return select(conn)
        with get_conn() as connection:
            return select(connection)

    def count_events(
        self,
        *,
        scope: CampaignScope,
        resolution_id: int | None = None,
        session_id: int | None = None,
        event_type: str | None = None,
        conn=None,
    ) -> int:
        self._validate_scope(scope)
        self._validate_optional_id(resolution_id, "resolution_id")
        self._validate_optional_id(session_id, "session_id")
        if event_type is not None and event_type not in ACTIVITY_EVENT_TYPES:
            raise ValueError("unsupported activity event type")
        where, params = self._filters(
            scope.campaign_id,
            resolution_id=resolution_id,
            session_id=session_id,
            event_type=event_type,
        )

        def count(connection):
            row = one_in_conn(
                connection,
                f"SELECT COUNT(*) AS total FROM campaign_activity_events WHERE {where}",
                params,
            )
            return int(row["total"]) if row is not None else 0

        if conn is not None:
            return count(conn)
        with get_conn() as connection:
            return count(connection)

    @staticmethod
    def _filters(
        campaign_id: int,
        *,
        resolution_id: int | None,
        session_id: int | None,
        event_type: str | None,
    ) -> tuple[str, tuple[object, ...]]:
        conditions = ["campaign_id = ?"]
        params: list[object] = [campaign_id]
        if resolution_id is not None:
            conditions.append("resolution_id = ?")
            params.append(resolution_id)
        if session_id is not None:
            conditions.append("session_id = ?")
            params.append(session_id)
        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)
        return " AND ".join(conditions), tuple(params)

    @staticmethod
    def _validate_pagination(limit: int, offset: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")

    @staticmethod
    def _validate_optional_id(value: int | None, field: str) -> None:
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise ValueError(f"{field} must be a positive integer or None")
