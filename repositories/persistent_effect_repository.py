"""SQLite repository for persistent campaign effects."""

from __future__ import annotations

import sqlite3

from database import one, one_in_conn, rows
from models.persistent_effect import (
    EffectDurationType,
    EffectSourceType,
    EffectStatus,
    EffectType,
    PersistentEffect,
)


class PersistentEffectRepository:
    def create(self, effect: PersistentEffect, *, conn: sqlite3.Connection) -> PersistentEffect:
        conn.execute(
            """
            INSERT INTO persistent_effects (
                id, campaign_id, entity_id, effect_type, effect_key,
                name, description, source_type, source_entity_id,
                source_reference, duration_type, duration_condition,
                level, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                effect.id, effect.campaign_id, effect.entity_id,
                effect.effect_type.value, effect.effect_key, effect.name,
                effect.description, effect.source_type.value,
                effect.source_entity_id, effect.source_reference,
                effect.duration_type.value, effect.duration_condition,
                effect.level, effect.status.value,
            ),
        )
        return self.get(effect.id, campaign_id=effect.campaign_id, conn=conn)

    def get(
        self,
        effect_id: str,
        *,
        campaign_id: int,
        conn: sqlite3.Connection | None = None,
    ) -> PersistentEffect | None:
        query = "SELECT * FROM persistent_effects WHERE id = ? AND campaign_id = ?"
        params = (effect_id, campaign_id)
        if conn is None:
            row = one(query, params)
        else:
            row = one_in_conn(conn, query, params)
        return self._row_to_model(row) if row else None

    def list_for_entity(
        self,
        entity_id: int,
        *,
        campaign_id: int,
        include_removed: bool = False,
    ) -> list[PersistentEffect]:
        query = """
            SELECT * FROM persistent_effects
            WHERE campaign_id = ? AND entity_id = ?
        """
        params: tuple = (campaign_id, entity_id)
        if not include_removed:
            query += " AND status != 'removed'"
        query += " ORDER BY created_at, id"
        return [self._row_to_model(row) for row in rows(query, params)]

    def update_status(
        self,
        effect_id: str,
        *,
        campaign_id: int,
        status: EffectStatus,
        conn: sqlite3.Connection,
    ) -> bool:
        cursor = conn.execute(
            """
            UPDATE persistent_effects
            SET status = ?,
                removed_at = CASE
                    WHEN ? = 'removed' THEN COALESCE(removed_at, CURRENT_TIMESTAMP)
                    ELSE NULL
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND campaign_id = ?
            """,
            (status.value, status.value, effect_id, campaign_id),
        )
        return cursor.rowcount == 1

    @staticmethod
    def _row_to_model(row) -> PersistentEffect:
        return PersistentEffect(
            campaign_id=row["campaign_id"],
            entity_id=row["entity_id"],
            effect_type=EffectType(row["effect_type"]),
            effect_key=row["effect_key"],
            name=row["name"],
            description=row["description"],
            source_type=EffectSourceType(row["source_type"]),
            source_entity_id=row["source_entity_id"],
            source_reference=row["source_reference"],
            duration_type=EffectDurationType(row["duration_type"]),
            duration_condition=row["duration_condition"],
            level=row["level"],
            id=row["id"],
            status=EffectStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            removed_at=row["removed_at"],
        )
