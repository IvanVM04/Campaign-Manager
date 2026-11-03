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
        campaign_id: int
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