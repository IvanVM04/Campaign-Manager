"""Campaign-scoped persistence for NPC creature mechanics."""

import json

from database import one
from models.creature_state import CreatureState


class CreatureRepository:
    def get_creature(self, entity_id: int, *, campaign_id: int, conn=None):
        query = """
            SELECT entity_id, current_hp, max_hp, armor_class, strength,
                   dexterity, constitution, intelligence, wisdom, charisma,
                   proficiency_bonus, metadata
            FROM creature_states
            WHERE entity_id = ? AND campaign_id = ?
        """
        params = (entity_id, campaign_id)
        row = one(query, params) if conn is None else conn.execute(query, params).fetchone()
        return self._row_to_model(row) if row else None

    def save_creature(self, creature: CreatureState, *, campaign_id: int, conn):
        conn.execute(
            """
            INSERT INTO creature_states (
                entity_id, campaign_id, current_hp, max_hp, armor_class,
                strength, dexterity, constitution, intelligence, wisdom,
                charisma, proficiency_bonus, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                current_hp=excluded.current_hp, max_hp=excluded.max_hp,
                armor_class=excluded.armor_class, strength=excluded.strength,
                dexterity=excluded.dexterity, constitution=excluded.constitution,
                intelligence=excluded.intelligence, wisdom=excluded.wisdom,
                charisma=excluded.charisma,
                proficiency_bonus=excluded.proficiency_bonus,
                metadata=excluded.metadata
            WHERE creature_states.campaign_id = excluded.campaign_id
            """,
            (
                creature.entity_id, campaign_id, creature.current_hp,
                creature.max_hp, creature.armor_class, creature.strength,
                creature.dexterity, creature.constitution, creature.intelligence,
                creature.wisdom, creature.charisma, creature.proficiency_bonus,
                json.dumps(creature.metadata, sort_keys=True),
            ),
        )
        loaded = self.get_creature(creature.entity_id, campaign_id=campaign_id, conn=conn)
        if loaded is None:
            raise RuntimeError("creature state could not be saved for this campaign")
        return loaded

    def update_current_hp(
        self, entity_id: int, *, campaign_id: int,
        expected_current_hp: int, new_current_hp: int, conn,
    ) -> None:
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (expected_current_hp, new_current_hp)
        ):
            raise ValueError("hit points must be non-negative integers")
        cursor = conn.execute(
            """
            UPDATE creature_states SET current_hp = ?, updated_at = CURRENT_TIMESTAMP
            WHERE entity_id = ? AND campaign_id = ? AND current_hp = ?
            """,
            (new_current_hp, entity_id, campaign_id, expected_current_hp),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("creature hit points changed; reload the encounter")

    @staticmethod
    def _row_to_model(row):
        return CreatureState(
            entity_id=row["entity_id"],
            current_hp=row["current_hp"],
            max_hp=row["max_hp"],
            armor_class=row["armor_class"],
            strength=row["strength"],
            dexterity=row["dexterity"],
            constitution=row["constitution"],
            intelligence=row["intelligence"],
            wisdom=row["wisdom"],
            charisma=row["charisma"],
            proficiency_bonus=row["proficiency_bonus"],
            metadata=json.loads(row["metadata"] or "{}"),
        )
