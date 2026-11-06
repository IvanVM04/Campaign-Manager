from __future__ import annotations

from database import get_conn, one, one_in_conn, rows, rows_in_conn
from models.campaign_scope import CampaignScope
from models.turn_record import TurnRecord


class TurnRepository:
    """Persistencia de turnos estrictamente limitada a una campaña."""

    _SELECT_FIELDS = """
        id, session_id, player_input, narrative, operation_count,
        successful_operation_count, failed_operation_count,
        all_operations_succeeded, world_changed, created_at,
        external_turn_id, version, status, snapshot
    """

    @staticmethod
    def _validate_scope(scope: CampaignScope) -> None:
        if not isinstance(scope, CampaignScope):
            raise TypeError("scope must be a CampaignScope")

    @staticmethod
    def _validate_positive_int(value, field_name: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{field_name} must be an integer")
        if value < 1:
            raise ValueError(f"{field_name} must be greater than zero")

    @classmethod
    def _validate_optional_positive_int(cls, value, field_name: str) -> None:
        if value is not None:
            cls._validate_positive_int(value, field_name)

    @staticmethod
    def _validate_limit(limit: int, *, optional: bool = False) -> None:
        if optional and limit is None:
            return
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError("limit must be an integer")
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        if limit > 100:
            raise ValueError("limit must not be greater than 100")

    @staticmethod
    def _validate_external_turn_id(value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("external_turn_id must be a string")
        value = value.strip()
        if not value:
            raise ValueError("external_turn_id must not be empty")
        if len(value) > 500:
            raise ValueError(
                "external_turn_id must not be longer than 500 characters"
            )
        return value

    @staticmethod
    def _row_to_model(row: dict) -> TurnRecord:
        return TurnRecord(
            id=row["id"],
            session_id=row["session_id"],
            player_input=row["player_input"],
            narrative=row["narrative"],
            operation_count=row["operation_count"],
            successful_operation_count=row["successful_operation_count"],
            failed_operation_count=row["failed_operation_count"],
            all_operations_succeeded=bool(row["all_operations_succeeded"]),
            world_changed=bool(row["world_changed"]),
            created_at=row["created_at"],
            external_turn_id=row["external_turn_id"],
            version=row["version"],
            status=row["status"],
            snapshot=row["snapshot"],
        )

    def save_turn(
        self,
        turn: TurnRecord,
        *,
        scope: CampaignScope,
        conn=None,
    ) -> TurnRecord:
        self._validate_scope(scope)
        if not isinstance(turn, TurnRecord):
            raise TypeError("turn must be a TurnRecord")
        if not isinstance(turn.player_input, str):
            raise TypeError("turn.player_input must be a string")
        if not isinstance(turn.narrative, str):
            raise TypeError("turn.narrative must be a string")

        external_turn_id = turn.external_turn_id
        if external_turn_id is not None:
            external_turn_id = self._validate_external_turn_id(
                external_turn_id
            )

        query = """
            INSERT INTO turns (
                session_id, player_input, narrative, operation_count,
                successful_operation_count, failed_operation_count,
                all_operations_succeeded, world_changed, external_turn_id,
                version, status, snapshot, campaign_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            turn.session_id, turn.player_input, turn.narrative,
            turn.operation_count, turn.successful_operation_count,
            turn.failed_operation_count, int(turn.all_operations_succeeded),
            int(turn.world_changed), external_turn_id, turn.version,
            turn.status, turn.snapshot, scope.campaign_id,
        )

        if conn is None:
            with get_conn() as connection:
                cursor = connection.execute(query, params)
                row = one_in_conn(
                    connection,
                    f"SELECT {self._SELECT_FIELDS} FROM turns "
                    "WHERE id=? AND campaign_id=?",
                    (cursor.lastrowid, scope.campaign_id),
                )
        else:
            cursor = conn.execute(query, params)
            row = one_in_conn(
                conn,
                f"SELECT {self._SELECT_FIELDS} FROM turns "
                "WHERE id=? AND campaign_id=?",
                (cursor.lastrowid, scope.campaign_id),
            )

        if row is None:
            raise RuntimeError("failed to retrieve saved turn")
        return self._row_to_model(row)

    def get_turn(
        self, turn_id: int, *, scope: CampaignScope, conn=None
    ) -> TurnRecord | None:
        self._validate_scope(scope)
        self._validate_positive_int(turn_id, "turn_id")
        query = (
            f"SELECT {self._SELECT_FIELDS} FROM turns "
            "WHERE id=? AND campaign_id=?"
        )
        params = (turn_id, scope.campaign_id)
        row = one(query, params) if conn is None else one_in_conn(conn, query, params)
        return self._row_to_model(row) if row is not None else None

    def get_by_external_turn_id(
        self, external_turn_id: str, *, scope: CampaignScope, conn=None
    ) -> TurnRecord | None:
        self._validate_scope(scope)
        external_turn_id = self._validate_external_turn_id(external_turn_id)
        query = (
            f"SELECT {self._SELECT_FIELDS} FROM turns "
            "WHERE external_turn_id=? AND campaign_id=? "
            "ORDER BY version DESC LIMIT 1"
        )
        params = (external_turn_id, scope.campaign_id)
        row = one(query, params) if conn is None else one_in_conn(conn, query, params)
        return self._row_to_model(row) if row is not None else None

    @staticmethod
    def _validate_offset(offset: int) -> None:
        if not isinstance(offset, int) or isinstance(offset, bool):
            raise TypeError("offset must be an integer")
        if offset < 0:
            raise ValueError("offset must not be negative")

    def list_turns(
        self,
        *,
        scope: CampaignScope,
        session_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
        conn=None,
    ) -> list[TurnRecord]:
        self._validate_scope(scope)
        self._validate_optional_positive_int(session_id, "session_id")
        self._validate_limit(limit, optional=True)
        self._validate_offset(offset)

        clauses = ["campaign_id=?"]
        params: list[int] = [scope.campaign_id]
        if session_id is not None:
            clauses.append("session_id=?")
            params.append(session_id)
        query = (
            f"SELECT {self._SELECT_FIELDS} FROM turns WHERE "
            + " AND ".join(clauses)
        )
        query += " ORDER BY id ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
            if offset:
                query += " OFFSET ?"
                params.append(offset)
        elif offset:
            query += " LIMIT -1 OFFSET ?"
            params.append(offset)

        result = (
            rows(query, tuple(params))
            if conn is None
            else rows_in_conn(conn, query, tuple(params))
        )
        return [self._row_to_model(row) for row in result]

    def list_recent_turns(
        self,
        *,
        scope: CampaignScope,
        session_id: int | None = None,
        limit: int = 10,
        conn=None,
    ) -> list[TurnRecord]:
        self._validate_scope(scope)
        self._validate_optional_positive_int(session_id, "session_id")
        self._validate_limit(limit)
        clauses = ["campaign_id=?"]
        params: list[int] = [scope.campaign_id]
        if session_id is not None:
            clauses.append("session_id=?")
            params.append(session_id)
        query = f"SELECT {self._SELECT_FIELDS} FROM turns WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        result = rows(query, tuple(params)) if conn is None else rows_in_conn(conn, query, tuple(params))
        return [self._row_to_model(row) for row in reversed(result)]

    def list_recent_active_turns(
        self,
        *,
        scope: CampaignScope,
        session_id: int | None = None,
        limit: int = 10,
        conn=None,
    ) -> list[TurnRecord]:
        self._validate_scope(scope)
        self._validate_optional_positive_int(session_id, "session_id")
        self._validate_limit(limit)
        clauses = ["campaign_id=?", "status='active'"]
        params: list[int] = [scope.campaign_id]
        if session_id is not None:
            clauses.append("session_id=?")
            params.append(session_id)
        query = f"SELECT {self._SELECT_FIELDS} FROM turns WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        result = rows(query, tuple(params)) if conn is None else rows_in_conn(conn, query, tuple(params))
        return [self._row_to_model(row) for row in reversed(result)]

    def get_active_by_external_turn_id(
        self, external_turn_id: str, *, scope: CampaignScope, conn=None
    ) -> TurnRecord | None:
        self._validate_scope(scope)
        external_turn_id = self._validate_external_turn_id(external_turn_id)
        query = (
            f"SELECT {self._SELECT_FIELDS} FROM turns "
            "WHERE external_turn_id=? AND campaign_id=? AND status='active' "
            "ORDER BY version DESC LIMIT 1"
        )
        params = (external_turn_id, scope.campaign_id)
        row = one(query, params) if conn is None else one_in_conn(conn, query, params)
        return self._row_to_model(row) if row is not None else None

    def get_versions_by_external_turn_id(
        self, external_turn_id: str, *, scope: CampaignScope, conn=None
    ) -> list[TurnRecord]:
        self._validate_scope(scope)
        external_turn_id = self._validate_external_turn_id(external_turn_id)
        query = (
            f"SELECT {self._SELECT_FIELDS} FROM turns "
            "WHERE external_turn_id=? AND campaign_id=? ORDER BY version ASC"
        )
        params = (external_turn_id, scope.campaign_id)
        result = rows(query, params) if conn is None else rows_in_conn(conn, query, params)
        return [self._row_to_model(row) for row in result]

    def supersede_turn(
        self,
        turn_id: int,
        *,
        scope: CampaignScope,
        conn,
    ) -> None:
        self._validate_scope(scope)
        self._validate_positive_int(turn_id, "turn_id")
        cursor = conn.execute(
            "UPDATE turns SET status='superseded' "
            "WHERE id=? AND campaign_id=?",
            (turn_id, scope.campaign_id),
        )
        if cursor.rowcount != 1:
            raise LookupError(
                f"turn {turn_id} does not belong to campaign "
                f"{scope.campaign_id}"
            )
