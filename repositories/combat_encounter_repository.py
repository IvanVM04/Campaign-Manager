"""SQLite persistence for D&D combat encounters, scoped to a campaign."""

from __future__ import annotations

import json
import sqlite3

from database import one, rows
from models.combat_encounter_state import CombatEncounterState, EncounterStatus
from models.combatant_state import CombatantState
from rules_engine.dnd5e_2014.combat.conditions import Condition, ConditionSet


class CombatEncounterRepository:
    """Stores complete encounter snapshots; callers own transaction boundaries."""

    @staticmethod
    def _serialize(encounter: CombatEncounterState) -> tuple[str, int, int, str, str]:
        combatants = {
            key: {
                "name": value.name,
                "initiative": value.initiative,
                "current_hp": value.current_hp,
                "max_hp": value.max_hp,
                "armor_class": value.armor_class,
                "entity_id": value.entity_id,
                "is_player_character": value.is_player_character,
                "conscious": value.conscious,
                "conditions": sorted(item.value for item in value.conditions.conditions),
                "exhaustion_level": value.conditions.exhaustion_level,
            }
            for key, value in encounter.combatants.items()
        }
        return (
            encounter.status.value,
            encounter.round_number,
            encounter.turn_index,
            json.dumps(encounter.initiative_order),
            json.dumps(combatants, sort_keys=True),
        )

    @staticmethod
    def _deserialize(row: dict) -> CombatEncounterState:
        payload = json.loads(row["combatants"])
        combatants = {}
        for combatant_id, value in payload.items():
            combatants[combatant_id] = CombatantState(
                combatant_id=combatant_id,
                name=value["name"],
                initiative=value["initiative"],
                current_hp=value["current_hp"],
                max_hp=value["max_hp"],
                armor_class=value["armor_class"],
                entity_id=value.get("entity_id"),
                is_player_character=value.get("is_player_character", False),
                conscious=value.get("conscious", True),
                conditions=ConditionSet(
                    frozenset(Condition(item) for item in value.get("conditions", [])),
                    value.get("exhaustion_level", 0),
                ),
            )
        return CombatEncounterState(
            encounter_id=row["encounter_id"],
            combatants=combatants,
            initiative_order=tuple(json.loads(row["initiative_order"])),
            round_number=row["round_number"],
            turn_index=row["turn_index"],
            status=EncounterStatus(row["status"]),
        )

    def save(
        self,
        encounter: CombatEncounterState,
        *,
        campaign_id: int,
        conn: sqlite3.Connection | None = None,
    ) -> CombatEncounterState:
        if not isinstance(encounter, CombatEncounterState):
            raise TypeError("encounter must be a CombatEncounterState")
        if isinstance(campaign_id, bool) or not isinstance(campaign_id, int) or campaign_id < 1:
            raise ValueError("campaign_id must be a positive integer")
        status, round_number, turn_index, initiative_order, combatants = self._serialize(encounter)
        query = """
            INSERT INTO combat_encounters (
                encounter_id, campaign_id, status, round_number,
                turn_index, initiative_order, combatants
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(encounter_id, campaign_id) DO UPDATE SET
                status=excluded.status,
                round_number=excluded.round_number,
                turn_index=excluded.turn_index,
                initiative_order=excluded.initiative_order,
                combatants=excluded.combatants,
                updated_at=CURRENT_TIMESTAMP
        """
        params = (
            encounter.encounter_id, campaign_id, status, round_number,
            turn_index, initiative_order, combatants,
        )
        if conn is None:
            from database import execute
            execute(query, params)
        else:
            conn.execute(query, params)
        loaded = self.get(encounter.encounter_id, campaign_id=campaign_id, conn=conn)
        if loaded is None:
            raise RuntimeError("saved combat encounter could not be reloaded")
        return loaded

    def get(
        self,
        encounter_id: str,
        *,
        campaign_id: int,
        conn: sqlite3.Connection | None = None,
    ) -> CombatEncounterState | None:
        query = """
            SELECT encounter_id, status, round_number, turn_index,
                   initiative_order, combatants
            FROM combat_encounters
            WHERE encounter_id = ? AND campaign_id = ?
        """
        params = (encounter_id, campaign_id)
        if conn is None:
            row = one(query, params)
        else:
            found = conn.execute(query, params).fetchone()
            row = dict(found) if found else None
        return self._deserialize(row) if row else None

    def list_for_campaign(self, campaign_id: int) -> list[CombatEncounterState]:
        found = rows(
            """
            SELECT encounter_id, status, round_number, turn_index,
                   initiative_order, combatants
            FROM combat_encounters
            WHERE campaign_id = ?
            ORDER BY created_at, encounter_id
            """,
            (campaign_id,),
        )
        return [self._deserialize(row) for row in found]

    def delete(
        self,
        encounter_id: str,
        *,
        campaign_id: int,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        query = "DELETE FROM combat_encounters WHERE encounter_id = ? AND campaign_id = ?"
        params = (encounter_id, campaign_id)
        if conn is None:
            from database import execute
            execute(query, params)
            return True
        cursor = conn.execute(query, params)
        return cursor.rowcount > 0
