from __future__ import annotations

import sqlite3


class CampaignStateVersionRepository:
    """Reads the monotonic revision maintained by SQLite mutation triggers."""

    def get_revision(
        self,
        campaign_id: int,
        *,
        conn: sqlite3.Connection,
    ) -> int:
        if isinstance(campaign_id, bool) or not isinstance(campaign_id, int):
            raise TypeError("campaign_id must be an integer")
        if campaign_id < 1:
            raise ValueError("campaign_id must be greater than zero")
        if conn is None:
            raise TypeError("conn is required")

        row = conn.execute(
            """
            SELECT revision
            FROM campaign_state_versions
            WHERE campaign_id = ?
            """,
            (campaign_id,),
        ).fetchone()
        if row is None:
            raise LookupError(
                f"campaign state revision does not exist for campaign {campaign_id}"
            )
        return int(row["revision"] if isinstance(row, sqlite3.Row) else row[0])
