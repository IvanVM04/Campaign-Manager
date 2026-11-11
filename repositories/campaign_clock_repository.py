"""Persistence for the campaign's fictional-time clock."""

from database import one, one_in_conn
from models.campaign_clock import CampaignClock


class CampaignClockRepository:
    @staticmethod
    def _model(row):
        return CampaignClock(
            campaign_id=row["campaign_id"],
            elapsed_minutes=row["elapsed_minutes"],
            version=row["version"],
            updated_at=row["updated_at"],
        )

    def get(self, campaign_id: int, *, conn=None) -> CampaignClock | None:
        query = "SELECT * FROM campaign_clocks WHERE campaign_id = ?"
        row = one(query, (campaign_id,)) if conn is None else one_in_conn(conn, query, (campaign_id,))
        return self._model(row) if row else None

    def ensure(self, campaign_id: int, *, conn) -> CampaignClock:
        conn.execute(
            "INSERT OR IGNORE INTO campaign_clocks (campaign_id) VALUES (?)",
            (campaign_id,),
        )
        clock = self.get(campaign_id, conn=conn)
        if clock is None:
            raise LookupError("campaign does not exist")
        return clock

    def advance(self, campaign_id: int, *, minutes: int, expected_elapsed_minutes: int, conn) -> CampaignClock:
        cursor = conn.execute(
            """
            UPDATE campaign_clocks
            SET elapsed_minutes = elapsed_minutes + ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE campaign_id = ? AND elapsed_minutes = ?
            """,
            (minutes, campaign_id, expected_elapsed_minutes),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("campaign clock changed; reload before advancing time")
        clock = self.get(campaign_id, conn=conn)
        if clock is None:
            raise RuntimeError("campaign clock disappeared after advancing time")
        return clock
