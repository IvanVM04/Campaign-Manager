"""Campaign-scoped character equipment projection, backed by owned item instances."""

from database import one, rows, transaction


class WeaponEquipmentRepository:
    """Persist equipped slots; inventory ownership remains on item_instances."""

    def equip_item(
        self, *, campaign_id: int, character_entity_id: int,
        item_instance_id: int, slot: str,
    ) -> None:
        # Replace the slot assignment atomically. The item itself must already
        # be active and owned by this character; database triggers enforce it.
        with transaction("IMMEDIATE") as conn:
            conn.execute(
                """
                DELETE FROM equipped_items
                WHERE campaign_id = ? AND character_entity_id = ? AND slot = ?
                """,
                (campaign_id, character_entity_id, slot),
            )
            conn.execute(
                """
                INSERT INTO equipped_items (
                    campaign_id, character_entity_id, slot, item_instance_id
                ) VALUES (?, ?, ?, ?)
                """,
                (campaign_id, character_entity_id, slot, item_instance_id),
            )

    def equip(
        self, *, campaign_id: int, character_entity_id: int,
        item_instance_id: int,
    ) -> None:
        """Backward-compatible weapon entry point: equip in the main hand."""
        self.equip_item(
            campaign_id=campaign_id,
            character_entity_id=character_entity_id,
            item_instance_id=item_instance_id,
            slot="main_hand",
        )

    def list_inventory(self, *, campaign_id: int, character_entity_id: int, conn=None):
        query = """
            SELECT
                ii.id AS item_instance_id, ii.item_id, i.name AS item_name,
                i.weapon_key, i.armor_key, i.equipment_slot, ii.instance_number,
                ii.condition, ii.notes, ii.active
            FROM item_instances ii
            JOIN items i
              ON i.id = ii.item_id AND i.campaign_id = ii.campaign_id
            WHERE ii.campaign_id = ? AND ii.owner_id = ? AND ii.active = 1
            ORDER BY i.name, ii.instance_number
        """
        params = (campaign_id, character_entity_id)
        if conn is None:
            return rows(query, params)
        return [dict(row) for row in conn.execute(query, params).fetchall()]

    def list_equipped(self, *, campaign_id: int, character_entity_id: int, conn=None):
        query = """
            SELECT
                ei.character_entity_id, ei.slot, ei.item_instance_id,
                ii.item_id, i.name AS item_name, ii.instance_number,
                i.weapon_key, i.armor_key, i.equipment_slot, ii.owner_id, ii.active,
                ii.condition, ii.notes
            FROM equipped_items ei
            JOIN item_instances ii
              ON ii.id = ei.item_instance_id AND ii.campaign_id = ei.campaign_id
            JOIN items i
              ON i.id = ii.item_id AND i.campaign_id = ei.campaign_id
            WHERE ei.campaign_id = ? AND ei.character_entity_id = ?
            ORDER BY ei.slot
        """
        params = (campaign_id, character_entity_id)
        if conn is None:
            return rows(query, params)
        return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_equipped_slot(
        self, *, campaign_id: int, character_entity_id: int,
        slot: str, conn=None,
    ):
        query = """
            SELECT
                ei.character_entity_id, ei.slot, ei.item_instance_id,
                ii.item_id, i.weapon_key, i.armor_key, i.equipment_slot,
                ii.condition, ii.notes
            FROM equipped_items ei
            JOIN item_instances ii
              ON ii.id = ei.item_instance_id AND ii.campaign_id = ei.campaign_id
            JOIN items i
              ON i.id = ii.item_id AND i.campaign_id = ei.campaign_id
            WHERE ei.campaign_id = ? AND ei.character_entity_id = ? AND ei.slot = ?
        """
        params = (campaign_id, character_entity_id, slot)
        if conn is None:
            return one(query, params)
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None

    def get_equipped(self, *, campaign_id: int, character_entity_id: int, conn=None):
        """Backward-compatible accessor for the main-hand weapon."""
        return self.get_equipped_slot(
            campaign_id=campaign_id,
            character_entity_id=character_entity_id,
            slot="main_hand",
            conn=conn,
        )

    def unequip_slot(
        self, *, campaign_id: int, character_entity_id: int, slot: str,
    ) -> None:
        with transaction("IMMEDIATE") as conn:
            conn.execute(
                """
                DELETE FROM equipped_items
                WHERE campaign_id = ? AND character_entity_id = ? AND slot = ?
                """,
                (campaign_id, character_entity_id, slot),
            )

    def unequip(self, *, campaign_id: int, character_entity_id: int) -> None:
        with transaction("IMMEDIATE") as conn:
            conn.execute(
                "DELETE FROM equipped_items WHERE campaign_id = ? AND character_entity_id = ?",
                (campaign_id, character_entity_id),
            )
