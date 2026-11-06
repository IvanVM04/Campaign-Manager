from database import (
    execute,
    execute_in_conn,
    one,
    one_in_conn,
    rows,
)


class CampaignRepository:

    def list_campaigns(self):
        return rows(
            """
            SELECT id, name, system, tone, summary
            FROM campaign
            ORDER BY id ASC
            """
        )

    def create_campaign(
        self,
        name: str,
        system: str = "D&D 5e 2014",
        tone: str = "",
        summary: str = "",
    ):
        campaign_id = execute(
            """
            INSERT INTO campaign (name, system, tone, summary)
            VALUES (?, ?, ?, ?)
            """,
            (name, system, tone, summary),
        )
        return self.get_campaign(campaign_id)

    def get_campaign(
        self,
        campaign_id: int,
        *,
        conn=None,
    ):
        query = """
            SELECT *
            FROM campaign
            WHERE id=?
        """

        if conn is None:
            return one(
                query,
                (campaign_id,),
            )

        return one_in_conn(
            conn,
            query,
            (campaign_id,),
        )

    def update_campaign(
        self,
        campaign_id: int,
        name: str,
        system: str,
        tone: str,
        summary: str,
        *,
        conn=None,
    ):
        query = """
            UPDATE campaign
            SET
                name=?,
                system=?,
                tone=?,
                summary=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """

        params = (
            name,
            system,
            tone,
            summary,
            campaign_id,
        )

        if conn is None:
            execute(
                query,
                params,
            )
        else:
            execute_in_conn(
                conn,
                query,
                params,
            )

        return self.get_campaign(
            campaign_id,
            conn=conn,
        )

    def update_current_session(
        self,
        campaign_id: int,
        session_id: int | None,
        *,
        conn=None,
    ):
        query = """
            UPDATE campaign
            SET
                current_session_id=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """

        params = (
            session_id,
            campaign_id,
        )

        if conn is None:
            execute(
                query,
                params,
            )
        else:
            execute_in_conn(
                conn,
                query,
                params,
            )

        return self.get_campaign(
            campaign_id,
            conn=conn,
        )

    def create_session(
        self,
        number: int,
        title: str,
        summary: str,
        start_location: str,
        end_location: str,
        notes: str,
        *,
        campaign_id: int,
        conn=None,
    ):
        query = """
            INSERT INTO sessions
                (
                    number,
                    title,
                    summary,
                    start_location,
                    end_location,
                    notes,
                    campaign_id
                )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            number,
            title,
            summary,
            start_location,
            end_location,
            notes,
            campaign_id,
        )

        if conn is None:
            session_id = execute(
                query,
                params,
            )
        else:
            session_id = execute_in_conn(
                conn,
                query,
                params,
            )

        return self.get_session(
            session_id,
            campaign_id=campaign_id,
            conn=conn,
        )

    @staticmethod
    def _session_overview_query() -> str:
        return """
            SELECT
                s.id,
                s.number,
                s.title,
                s.summary,
                s.start_location,
                s.end_location,
                COUNT(t.id) AS turn_count,
                MAX(t.created_at) AS last_turn_at
            FROM sessions AS s
            LEFT JOIN turns AS t
                ON t.session_id = s.id
                AND t.campaign_id = s.campaign_id
            WHERE s.campaign_id = ?
        """

    @staticmethod
    def _validate_session_pagination(
        campaign_id: int,
        limit: int,
        offset: int,
    ) -> None:
        if not isinstance(campaign_id, int) or isinstance(campaign_id, bool):
            raise TypeError("campaign_id must be an integer")
        if campaign_id < 1:
            raise ValueError("campaign_id must be greater than zero")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError("limit must be an integer")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if not isinstance(offset, int) or isinstance(offset, bool):
            raise TypeError("offset must be an integer")
        if offset < 0:
            raise ValueError("offset must not be negative")

    def list_sessions(
        self,
        *,
        campaign_id: int,
        limit: int = 50,
        offset: int = 0,
        conn=None,
    ):
        self._validate_session_pagination(campaign_id, limit, offset)
        query = self._session_overview_query()
        query += (
            " GROUP BY s.id"
            " ORDER BY s.number DESC, s.id DESC"
            " LIMIT ? OFFSET ?"
        )
        params = (campaign_id, limit, offset)
        if conn is None:
            return rows(query, params)
        return rows_in_conn(conn, query, params)

    def count_sessions(self, *, campaign_id: int, conn=None) -> int:
        query = "SELECT COUNT(*) AS total FROM sessions WHERE campaign_id=?"
        result = (
            one(query, (campaign_id,))
            if conn is None
            else one_in_conn(conn, query, (campaign_id,))
        )
        return int(result["total"]) if result is not None else 0

    def get_session_overview(
        self,
        session_id: int,
        *,
        campaign_id: int,
        conn=None,
    ):
        if not isinstance(session_id, int) or isinstance(session_id, bool):
            raise TypeError("session_id must be an integer")
        if session_id < 1:
            raise ValueError("session_id must be greater than zero")
        query = self._session_overview_query()
        query += " AND s.id=? GROUP BY s.id"
        params = (campaign_id, session_id)
        if conn is None:
            return one(query, params)
        return one_in_conn(conn, query, params)

    def get_session(
        self,
        session_id: int,
        *,
        campaign_id: int,
        conn=None,
    ):
        query = """
            SELECT *
            FROM sessions
            WHERE id=?
        """
        query += " AND campaign_id=?"
        params = (session_id, campaign_id)

        if conn is None:
            return one(
                query,
                params,
            )

        return one_in_conn(
            conn,
            query,
            params,
        )

    def get_current_session(
        self,
        campaign_id: int,
        *,
        conn=None,
    ):
        campaign = self.get_campaign(
            campaign_id,
            conn=conn,
        )

        if campaign is None:
            return None

        session_id = campaign[
            "current_session_id"
        ]

        if session_id is None:
            return None

        return self.get_session(
            session_id,
            campaign_id=campaign_id,
            conn=conn,
        )

    def update_active_character(
        self,
        campaign_id: int,
        character_id: int | None,
        *,
        conn=None,
    ):
        query = """
            UPDATE campaign
            SET
                active_character_id=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """

        params = (
            character_id,
            campaign_id,
        )

        if conn is None:
            execute(
                query,
                params,
            )

        else:
            from database import execute_in_conn

            execute_in_conn(
                conn,
                query,
                params,
            )

        return self.get_campaign(
            campaign_id,
            conn=conn,
        )

    def get_active_character_id(
        self,
        campaign_id: int,
        *,
        conn=None,
    ) -> int | None:
        campaign = self.get_campaign(
            campaign_id,
            conn=conn,
        )

        if campaign is None:
            return None

        return campaign[
            "active_character_id"
        ]