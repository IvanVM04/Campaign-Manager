from __future__ import annotations

from dataclasses import replace

from database import get_conn, one_in_conn
from models.campaign_scope import CampaignScope
from models.turn_resolution_record import TurnResolutionRecord


class TurnResolutionRepository:
    """Persists the recoverable execution envelope, not the turn transcript."""

    _FIELDS = """
        id, campaign_id, session_id, turn_id, player_input,
        adapter_namespace, idempotency_key, request_fingerprint,
        lifecycle_state, context_revision, resulting_revision, proposal_json, adjudication_json,
        mechanics_json, operation_results_json, narrative, attempt_count,
        lease_token, lease_expires_at, last_error_code, created_at,
        updated_at, committed_at, completed_at
    """

    _UPDATE_FIELDS = frozenset({
        "session_id", "turn_id", "context_revision", "resulting_revision", "proposal_json",
        "adjudication_json", "mechanics_json", "operation_results_json",
        "narrative", "lease_token", "lease_expires_at", "last_error_code",
        "committed_at", "completed_at",
    })

    @staticmethod
    def _validate_scope(scope: CampaignScope) -> None:
        if not isinstance(scope, CampaignScope):
            raise TypeError("scope must be a CampaignScope")

    @staticmethod
    def _row_to_model(row: dict) -> TurnResolutionRecord:
        return TurnResolutionRecord(**row)

    @staticmethod
    def _require_record(record: TurnResolutionRecord | None) -> TurnResolutionRecord:
        if record is None:
            raise RuntimeError("turn resolution disappeared after a successful update")
        return record

    def create(
        self,
        record: TurnResolutionRecord,
        *,
        scope: CampaignScope,
        conn=None,
    ) -> TurnResolutionRecord:
        self._validate_scope(scope)
        if not isinstance(record, TurnResolutionRecord):
            raise TypeError("record must be a TurnResolutionRecord")
        if record.campaign_id != scope.campaign_id:
            raise ValueError("record campaign does not match scope")
        query = """
            INSERT INTO turn_resolutions (
                campaign_id, session_id, turn_id, player_input,
                adapter_namespace, idempotency_key, request_fingerprint,
                lifecycle_state, context_revision, resulting_revision, proposal_json,
                adjudication_json, mechanics_json, operation_results_json,
                narrative, attempt_count, lease_token, lease_expires_at,
                last_error_code, committed_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            record.campaign_id, record.session_id, record.turn_id,
            record.player_input, record.adapter_namespace,
            record.idempotency_key, record.request_fingerprint,
            record.lifecycle_state, record.context_revision,
            record.resulting_revision, record.proposal_json, record.adjudication_json,
            record.mechanics_json, record.operation_results_json,
            record.narrative, record.attempt_count, record.lease_token,
            record.lease_expires_at, record.last_error_code,
            record.committed_at, record.completed_at,
        )

        def insert(connection):
            cursor = connection.execute(query, params)
            row = one_in_conn(
                connection,
                f"SELECT {self._FIELDS} FROM turn_resolutions WHERE id=? AND campaign_id=?",
                (cursor.lastrowid, scope.campaign_id),
            )
            if row is None:
                raise RuntimeError("failed to retrieve saved turn resolution")
            return self._row_to_model(row)

        if conn is not None:
            return insert(conn)
        with get_conn() as connection:
            return insert(connection)

    def get(
        self, resolution_id: int, *, scope: CampaignScope, conn=None
    ) -> TurnResolutionRecord | None:
        self._validate_scope(scope)
        if not isinstance(resolution_id, int) or isinstance(resolution_id, bool):
            raise TypeError("resolution_id must be an integer")
        if resolution_id < 1:
            raise ValueError("resolution_id must be greater than zero")
        query = (
            f"SELECT {self._FIELDS} FROM turn_resolutions "
            "WHERE id=? AND campaign_id=?"
        )
        params = (resolution_id, scope.campaign_id)
        if conn is not None:
            row = one_in_conn(conn, query, params)
        else:
            with get_conn() as connection:
                row = one_in_conn(connection, query, params)
        return self._row_to_model(row) if row is not None else None

    def get_by_idempotency_key(
        self,
        adapter_namespace: str,
        idempotency_key: str,
        *,
        scope: CampaignScope,
        conn=None,
    ) -> TurnResolutionRecord | None:
        self._validate_scope(scope)
        if not isinstance(adapter_namespace, str) or not adapter_namespace.strip():
            raise ValueError("adapter_namespace must not be empty")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        query = (
            f"SELECT {self._FIELDS} FROM turn_resolutions "
            "WHERE campaign_id=? AND adapter_namespace=? AND idempotency_key=?"
        )
        params = (scope.campaign_id, adapter_namespace, idempotency_key)
        if conn is not None:
            row = one_in_conn(conn, query, params)
        else:
            with get_conn() as connection:
                row = one_in_conn(connection, query, params)
        return self._row_to_model(row) if row is not None else None

    def transition(
        self,
        resolution_id: int,
        target_state: str,
        *,
        scope: CampaignScope,
        expected_state: str,
        updates: dict | None = None,
        expected_lease_token: str | None = None,
        conn,
    ) -> TurnResolutionRecord:
        self._validate_scope(scope)
        current = self.get(resolution_id, scope=scope, conn=conn)
        if current is None:
            raise LookupError("turn resolution not found")
        if current.lifecycle_state != expected_state:
            raise ValueError("turn resolution state changed; reload before transition")
        if expected_state == "planning" and (
            not isinstance(expected_lease_token, str) or not expected_lease_token
        ):
            raise ValueError("expected_lease_token is required for planning transitions")
        if (
            expected_state == "planning"
            and current.lease_token != expected_lease_token
        ):
            raise ValueError("planning lease was superseded")
        if target_state == "planning":
            raise ValueError("use claim_for_planning to acquire a planning lease")
        if not current.can_transition_to(target_state):
            raise ValueError(
                f"invalid turn resolution transition: {expected_state} -> {target_state}"
            )
        updates = {} if updates is None else dict(updates)
        unknown = set(updates) - self._UPDATE_FIELDS
        if unknown:
            raise ValueError(f"unsupported turn resolution fields: {sorted(unknown)}")
        candidate = replace(
            current,
            lifecycle_state=target_state,
            **updates,
        )
        assignments = ["lifecycle_state=?", "updated_at=CURRENT_TIMESTAMP"]
        params: list[object] = [target_state]
        for field_name in updates:
            assignments.append(f"{field_name}=?")
            params.append(getattr(candidate, field_name))
        params.extend([resolution_id, scope.campaign_id, expected_state])
        where = " WHERE id=? AND campaign_id=? AND lifecycle_state=?"
        if expected_state == "planning":
            where += " AND lease_token=?"
            assert isinstance(expected_lease_token, str)
            params.append(expected_lease_token)
        cursor = conn.execute(
            "UPDATE turn_resolutions SET "
            + ", ".join(assignments)
            + where,
            tuple(params),
        )
        if cursor.rowcount != 1:
            raise ValueError("turn resolution state changed during transition")
        return self._require_record(self.get(resolution_id, scope=scope, conn=conn))

    def update_completed_projection(
        self,
        resolution_id: int,
        *,
        turn_id: int,
        narrative: str,
        scope: CampaignScope,
        conn,
    ) -> TurnResolutionRecord:
        self._validate_scope(scope)
        if not isinstance(turn_id, int) or isinstance(turn_id, bool) or turn_id < 1:
            raise ValueError("turn_id must be a positive integer")
        if not isinstance(narrative, str) or not narrative.strip():
            raise ValueError("narrative must not be empty")
        cursor = conn.execute(
            """
            UPDATE turn_resolutions
            SET turn_id=?, narrative=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND campaign_id=? AND lifecycle_state='completed'
            """,
            (turn_id, narrative, resolution_id, scope.campaign_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("completed resolution projection could not be updated")
        return self.get(resolution_id, scope=scope, conn=conn)

    def claim_for_planning(
        self,
        resolution_id: int,
        *,
        scope: CampaignScope,
        lease_token: str,
        lease_expires_at: str,
        now: str,
        conn,
    ) -> TurnResolutionRecord:
        self._validate_scope(scope)
        if not isinstance(lease_token, str) or not lease_token.strip():
            raise ValueError("lease_token must not be empty")
        if not isinstance(lease_expires_at, str) or not lease_expires_at.strip():
            raise ValueError("lease_expires_at must not be empty")
        if not isinstance(now, str) or not now.strip():
            raise ValueError("now must not be empty")
        cursor = conn.execute(
            """
            UPDATE turn_resolutions
            SET lifecycle_state='planning',
                attempt_count=attempt_count+1,
                lease_token=?,
                lease_expires_at=?,
                last_error_code=NULL,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND campaign_id=?
              AND (
                lifecycle_state IN ('accepted', 'awaiting_input')
                OR (lifecycle_state='planning' AND lease_expires_at <= ?)
              )
            """,
            (lease_token, lease_expires_at, resolution_id, scope.campaign_id, now),
        )
        if cursor.rowcount != 1:
            raise ValueError("turn resolution is not claimable")
        return self.get(resolution_id, scope=scope, conn=conn)
