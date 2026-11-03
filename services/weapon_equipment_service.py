"""Application service for equipped weapons and derived attack profiles."""
from models.character_state import CharacterState
from repositories.weapon_equipment_repository import WeaponEquipmentRepository
from rules_engine.dnd5e_2014.weapons.attack_profile import derive_attack_profile
from rules_engine.dnd5e_2014.weapons.catalog import get_weapon


class WeaponEquipmentService:
    def __init__(self, repository: WeaponEquipmentRepository | None = None):
        self.repository = repository or WeaponEquipmentRepository()

    def equip(self, *, campaign_id: int, character_entity_id: int, item_instance_id: int) -> None:
        self.repository.equip(campaign_id=campaign_id, character_entity_id=character_entity_id, item_instance_id=item_instance_id)

    def unequip(self, *, campaign_id: int, character_entity_id: int) -> None:
        self.repository.unequip(campaign_id=campaign_id, character_entity_id=character_entity_id)

    def attack_profile(self, character: CharacterState, *, campaign_id: int, versatile_two_handed: bool = False):
        equipped = self.repository.get_equipped(campaign_id=campaign_id, character_entity_id=character.entity_id)
        if equipped is None:
            raise LookupError("character has no equipped weapon")
        if equipped["weapon_key"] is None:
            raise ValueError("equipped item has no weapon definition")
        return derive_attack_profile(
            character, get_weapon(equipped["weapon_key"]),
            versatile_two_handed=versatile_two_handed,
        )
