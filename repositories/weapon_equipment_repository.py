"""Campaign-scoped persistence for equipped weapon instances."""

from database import execute, one


class WeaponEquipmentRepository:
    def equip(self, *, campaign_id: int, character_entity_id: int, item_instance_id: int) -> None:
        execute(
            """
            INSERT INTO equipped_weapons (
                campaign_id, character_entity_id, item_instance_id
            ) VALUES (?, ?, ?)
            ON CONFLICT(campaign_id, character_entity_id) DO UPDATE SET
                item_instance_id = excluded.item_instance_id
            """,
            (campaign_id, character_entity_id, item_instance_id),
        )
        loaded = self.get_equipped(
            campaign_id=campaign_id,
            character_entity_id=character_entity_id,
        )
        if loaded is None or loaded["item_instance_id"] != item_instance_id:
            raise RuntimeError("weapon could not be equipped for this campaign")

    def get_equipped(self, *, campaign_id: int, character_entity_id: int, conn=None):
        query = """
            SELECT ew.character_entity_id, ew.item_instance_id, ii.item_id, i.weapon_key
            FROM equipped_weapons ew
            JOIN item_instances ii
              ON ii.id = ew.item_instance_id AND ii.campaign_id = ew.campaign_id
            JOIN items i
              ON i.id = ii.item_id AND i.campaign_id = ew.campaign_id
            WHERE ew.campaign_id = ? AND ew.character_entity_id = ?
        """
        params = (campaign_id, character_entity_id)
        if conn is None:
            return one(query, params)
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None

    def unequip(self, *, campaign_id: int, character_entity_id: int) -> None:
        execute(
            "DELETE FROM equipped_weapons WHERE campaign_id = ? AND character_entity_id = ?",
            (campaign_id, character_entity_id),
        )
