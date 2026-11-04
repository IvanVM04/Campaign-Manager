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
                ("permanent" if effect.duration_type in (EffectDurationType.CAMPAIGN_TIME, EffectDurationType.ENCOUNTER_ROUNDS, EffectDurationType.ENCOUNTER_TURNS) else effect.duration_type.value), effect.duration_condition,
                effect.level, effect.status.value,
            ),
        )
        if effect.duration_type in (
            EffectDurationType.CAMPAIGN_TIME,
            EffectDurationType.ENCOUNTER_ROUNDS,
            EffectDurationType.ENCOUNTER_TURNS,
        ):
            conn.execute(
                """
                INSERT INTO persistent_effect_timers (
                    effect_id, campaign_id, duration_minutes, expires_at_minute,
                    encounter_id, duration_rounds, expires_at_round,
                    duration_turns, expires_at_turn
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    effect.id, effect.campaign_id, effect.duration_minutes,
                    effect.expires_at_minute, effect.encounter_id,
                    effect.duration_rounds, effect.expires_at_round,
                    effect.duration_turns, effect.expires_at_turn,
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
        query = "SELECT pe.*, timer.duration_minutes AS timer_duration_minutes, timer.expires_at_minute, timer.expired_at_minute FROM persistent_effects pe LEFT JOIN persistent_effect_timers timer ON timer.effect_id = pe.id WHERE pe.id = ? AND pe.campaign_id = ?"
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
        active_only: bool = False,
        conn: sqlite3.Connection | None = None,
    ) -> list[PersistentEffect]:
        query = """
            SELECT pe.*, timer.duration_minutes AS timer_duration_minutes,
                   timer.expires_at_minute, timer.expired_at_minute
            FROM persistent_effects pe
            LEFT JOIN persistent_effect_timers timer ON timer.effect_id = pe.id
            WHERE pe.campaign_id = ? AND pe.entity_id = ?
        """
        params: tuple = (campaign_id, entity_id)
        if active_only:
            query += " AND pe.status = 'active'"
        elif not include_removed:
            query += " AND pe.status != 'removed'"
        query += " ORDER BY pe.created_at, pe.id"
        found = conn.execute(query, params).fetchall() if conn is not None else rows(query, params)
        return [self._row_to_model(dict(row)) for row in found]

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

    def expire_due(self, campaign_id: int, elapsed_minutes: int, *, conn: sqlite3.Connection) -> int:
        due = conn.execute(
            """
            SELECT timer.effect_id
            FROM persistent_effect_timers timer
            JOIN persistent_effects effect
              ON effect.id = timer.effect_id AND effect.campaign_id = timer.campaign_id
            WHERE timer.campaign_id = ? AND timer.expired_at_minute IS NULL
              AND timer.expires_at_minute <= ? AND effect.status IN ('active', 'suspended')
            """,
            (campaign_id, elapsed_minutes),
        ).fetchall()
        if not due:
            return 0
        ids = [row["effect_id"] for row in due]
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE persistent_effects SET status = 'removed', removed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE campaign_id = ? AND id IN ({placeholders})",
            (campaign_id, *ids),
        )
        conn.execute(
            f"UPDATE persistent_effect_timers SET expired_at_minute = expires_at_minute WHERE campaign_id = ? AND effect_id IN ({placeholders}) AND expired_at_minute IS NULL",
            (campaign_id, *ids),
        )
        return len(ids)

    def expire_encounter_due(
        self, campaign_id: int, encounter_id: str, *, round_number: int,
        absolute_turn: int, round_changed: bool, conn: sqlite3.Connection,
    ) -> int:
        clauses = ["timer.campaign_id = ?", "timer.encounter_id = ?",
                   "effect.status IN ('active', 'suspended')"]
        params: list = [campaign_id, encounter_id]
        deadlines = []
        if round_changed:
            deadlines.append("(timer.expires_at_round IS NOT NULL AND timer.expires_at_round <= ?)")
            params.append(round_number)
        deadlines.append("(timer.expires_at_turn IS NOT NULL AND timer.expires_at_turn <= ?)")
        params.append(absolute_turn)
        query = """
            SELECT timer.effect_id FROM persistent_effect_timers timer
            JOIN persistent_effects effect
              ON effect.id = timer.effect_id AND effect.campaign_id = timer.campaign_id
            WHERE """ + " AND ".join(clauses) + " AND (" + " OR ".join(deadlines) + ")"
        due = conn.execute(query, params).fetchall()
        if not due:
            return 0
        ids = [row["effect_id"] for row in due]
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE persistent_effects SET status='removed', removed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE campaign_id=? AND id IN ({placeholders})",
            (campaign_id, *ids),
        )
        conn.execute(
            f"""UPDATE persistent_effect_timers
                SET expired_at_round = CASE WHEN expires_at_round IS NOT NULL THEN expires_at_round ELSE expired_at_round END,
                    expired_at_turn = CASE WHEN expires_at_turn IS NOT NULL THEN expires_at_turn ELSE expired_at_turn END
                WHERE campaign_id=? AND effect_id IN ({placeholders})""",
            (campaign_id, *ids),
        )
        return len(ids)

    def expire_encounter(
        self, campaign_id: int, encounter_id: str, *, conn: sqlite3.Connection
    ) -> int:
        due = conn.execute(
            """
            SELECT timer.effect_id FROM persistent_effect_timers timer
            JOIN persistent_effects effect
              ON effect.id = timer.effect_id AND effect.campaign_id = timer.campaign_id
            WHERE timer.campaign_id = ? AND timer.encounter_id = ?
              AND effect.status IN ('active', 'suspended')
            """,
            (campaign_id, encounter_id),
        ).fetchall()
        if not due:
            return 0
        ids = [row["effect_id"] for row in due]
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE persistent_effects SET status='removed', removed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE campaign_id=? AND id IN ({placeholders})",
            (campaign_id, *ids),
        )
        conn.execute(
            f"""UPDATE persistent_effect_timers
                SET expired_at_round = COALESCE(expired_at_round, expires_at_round),
                    expired_at_turn = COALESCE(expired_at_turn, expires_at_turn)
                WHERE campaign_id=? AND effect_id IN ({placeholders})""",
            (campaign_id, *ids),
        )
        return len(ids)

    @staticmethod
    def _row_to_model(row) -> PersistentEffect:
        expired_at_minute = row["expired_at_minute"]
        duration_minutes = row["timer_duration_minutes"]
        encounter_id = row["encounter_id"]
        duration_rounds = row["duration_rounds"]
        duration_turns = row["duration_turns"]
        duration_type = (
            EffectDurationType.CAMPAIGN_TIME if duration_minutes is not None
            else EffectDurationType.ENCOUNTER_ROUNDS if duration_rounds is not None
            else EffectDurationType.ENCOUNTER_TURNS if duration_turns is not None
            else EffectDurationType(row["duration_type"])
        )
        status = (
            EffectStatus.EXPIRED if any(value is not None for value in (
                expired_at_minute, row["expired_at_round"], row["expired_at_turn"]
            ))
            else EffectStatus(row["status"])
        )
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
            duration_type=duration_type,
            duration_condition=row["duration_condition"],
            duration_minutes=duration_minutes,
            expires_at_minute=row["expires_at_minute"],
            expired_at_minute=expired_at_minute,
            encounter_id=encounter_id,
            duration_rounds=duration_rounds,
            expires_at_round=row["expires_at_round"],
            duration_turns=duration_turns,
            expires_at_turn=row["expires_at_turn"],
            expired_at_round=row["expired_at_round"],
            expired_at_turn=row["expired_at_turn"],
            level=row["level"],
            id=row["id"],
            status=status,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            removed_at=row["removed_at"],
        )
