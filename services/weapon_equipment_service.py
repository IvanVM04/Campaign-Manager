"""Application service for character equipment and derived attack profiles."""

from models.character_state import CharacterState
from repositories.weapon_equipment_repository import WeaponEquipmentRepository
from rules_engine.dnd5e_2014.armor.armor_class import (
    derive_armor_class,
    derive_armor_proficiency,
)
from rules_engine.dnd5e_2014.weapons.attack_profile import derive_attack_profile
from rules_engine.dnd5e_2014.weapons.catalog import get_weapon


class WeaponEquipmentService:
    def __init__(self, repository: WeaponEquipmentRepository | None = None):
        self.repository = repository or WeaponEquipmentRepository()

    def equip(
        self, *, campaign_id: int, character_entity_id: int,
        item_instance_id: int, slot: str = "main_hand",
    ) -> None:
        self.repository.equip_item(
            campaign_id=campaign_id,
            character_entity_id=character_entity_id,
            item_instance_id=item_instance_id,
            slot=slot,
        )

    def unequip(
        self, *, campaign_id: int, character_entity_id: int,
        slot: str | None = None,
    ) -> None:
        if slot is None:
            self.repository.unequip(
                campaign_id=campaign_id, character_entity_id=character_entity_id
            )
        else:
            self.repository.unequip_slot(
                campaign_id=campaign_id,
                character_entity_id=character_entity_id,
                slot=slot,
            )

    def inventory_items(self, *, campaign_id: int, character_entity_id: int):
        return self.repository.list_inventory(
            campaign_id=campaign_id, character_entity_id=character_entity_id
        )

    def equipped_items(self, *, campaign_id: int, character_entity_id: int):
        return self.repository.list_equipped(
            campaign_id=campaign_id, character_entity_id=character_entity_id
        )

    def armor_class(self, character: CharacterState, *, campaign_id: int, conn=None):
        """Derive current AC from the character's equipped body armor and shield."""
        body = self.repository.get_equipped_slot(
            campaign_id=campaign_id,
            character_entity_id=character.entity_id,
            slot="body",
            conn=conn,
        )
        off_hand = self.repository.get_equipped_slot(
            campaign_id=campaign_id,
            character_entity_id=character.entity_id,
            slot="off_hand",
            conn=conn,
        )
        armor_key = body["armor_key"] if body is not None else None
        shield_equipped = bool(
            off_hand is not None and off_hand["armor_key"] == "shield"
        )
        return derive_armor_class(
            dexterity_score=character.dexterity,
            strength_score=character.strength,
            armor_key=armor_key,
            shield_equipped=shield_equipped,
        )

    def armor_proficiency(
        self, character: CharacterState, *, campaign_id: int, conn=None
    ):
        """Report whether equipped armor and shield match character training."""
        body = self.repository.get_equipped_slot(
            campaign_id=campaign_id,
            character_entity_id=character.entity_id,
            slot="body",
            conn=conn,
        )
        off_hand = self.repository.get_equipped_slot(
            campaign_id=campaign_id,
            character_entity_id=character.entity_id,
            slot="off_hand",
            conn=conn,
        )
        armor_key = body["armor_key"] if body is not None else None
        shield_equipped = bool(
            off_hand is not None and off_hand["armor_key"] == "shield"
        )
        return derive_armor_proficiency(
            armor_key=armor_key,
            shield_equipped=shield_equipped,
            proficiencies=character.armor_proficiencies,
        )

    def attack_profile(
        self, character: CharacterState, *, campaign_id: int,
        versatile_two_handed: bool = False,
    ):
        equipped = self.repository.get_equipped(
            campaign_id=campaign_id, character_entity_id=character.entity_id
        )
        if equipped is None:
            raise LookupError("character has no equipped main-hand weapon")
        if equipped["weapon_key"] is None:
            raise ValueError("main-hand item has no weapon definition")
        return derive_attack_profile(
            character, get_weapon(equipped["weapon_key"]),
            versatile_two_handed=versatile_two_handed,
        )
