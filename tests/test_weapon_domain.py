import sqlite3

import pytest

import database
from database import get_conn, init_db
from models.character_state import CharacterState
from models.entity import Entity
from models.item import Item, ItemInstance
from models.world_state import WorldState
from repositories.character_repository import CharacterRepository
from repositories.weapon_equipment_repository import WeaponEquipmentRepository
from repositories.world_repository import WorldRepository
from rules_engine.dnd5e_2014.weapons.attack_profile import derive_attack_profile
from rules_engine.dnd5e_2014.weapons.catalog import (
    WEAPON_CATALOG,
    WeaponCategory,
    WeaponProperty,
    get_weapon,
)
from services.weapon_equipment_service import WeaponEquipmentService


def setup_db(tmp_path):
    previous = database.DB_PATH
    database.DB_PATH = tmp_path / "weapons.db"
    init_db()
    return previous


def test_srd_catalog_has_37_unique_weapons_and_valid_mechanics():
    assert len(WEAPON_CATALOG) == 37
    assert len({weapon.key for weapon in WEAPON_CATALOG.values()}) == 37
    for weapon in WEAPON_CATALOG.values():
        assert weapon.key and weapon.name
        assert isinstance(weapon.category, WeaponCategory)
        assert weapon.damage_dice
        assert weapon.properties <= set(WeaponProperty)
        assert (weapon.normal_range is None) == (weapon.long_range is None)
    assert get_weapon("longsword").versatile_damage_dice == "1d10"
    assert WeaponProperty.FINESSE in get_weapon("rapier").properties


def test_attack_profile_uses_character_stats_and_proficiency():
    character = CharacterState(entity_id=1, strength=12, dexterity=18, proficiency_bonus=3,
                               weapon_proficiencies=frozenset({"martial_melee"}))
    profile = derive_attack_profile(character, get_weapon("rapier"))
    assert (profile.attack_ability, profile.attack_bonus, profile.damage_bonus) == ("dexterity", 7, 4)
    assert profile.proficient
    untrained = derive_attack_profile(CharacterState(entity_id=2, strength=16), get_weapon("longsword"))
    assert untrained.attack_bonus == 3 and not untrained.proficient


def test_ranged_uses_dexterity_and_versatile_dice_are_explicit():
    character = CharacterState(entity_id=1, strength=18, dexterity=12,
                               weapon_proficiencies=frozenset({"simple_ranged", "simple_melee"}))
    bow = derive_attack_profile(character, get_weapon("shortbow"))
    assert bow.attack_ability == "dexterity" and bow.attack_bonus == 3
    staff = derive_attack_profile(character, get_weapon("quarterstaff"), versatile_two_handed=True)
    assert staff.damage_dice == "1d8"
    with pytest.raises(ValueError):
        derive_attack_profile(character, get_weapon("dagger"), versatile_two_handed=True)


def test_character_weapon_proficiencies_round_trip(tmp_path):
    previous = setup_db(tmp_path)
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO entities (id, name, entity_type, campaign_id) VALUES (1, 'Hero', 'character', 1)")
        saved = CharacterRepository().save_character(
            CharacterState(entity_id=1, weapon_proficiencies=frozenset({"simple_melee", "martial_ranged"})),
            campaign_id=1,
        )
        assert saved.weapon_proficiencies == frozenset({"simple_melee", "martial_ranged"})
    finally:
        database.DB_PATH = previous


def test_world_repository_round_trips_weapon_key(tmp_path):
    previous = setup_db(tmp_path)
    try:
        state = WorldState(
            entities={1: Entity(id=1, name="Hero", entity_type="character")},
            items={1: Item(id=1, name="Longsword", weapon_key="longsword", equipment_slot="main_hand")},
            item_instances={1: ItemInstance(id=1, item_id=1, owner_id=1)},
        )
        repository = WorldRepository()
        repository.save_world(state, campaign_id=1)
        loaded = repository.load_world(campaign_id=1)
        assert loaded.items[1].weapon_key == "longsword"
        assert loaded.items[1].equipment_slot == "main_hand"
        assert loaded.item_instances[1].owner_id == 1
    finally:
        database.DB_PATH = previous


def test_equipped_weapon_requires_owned_weapon_in_same_campaign(tmp_path):
    previous = setup_db(tmp_path)
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO campaign (id, name) VALUES (2, 'Other')")
            conn.execute("INSERT INTO entities (id, name, entity_type, campaign_id) VALUES (1, 'Hero', 'character', 1)")
            conn.execute("INSERT INTO character_states (entity_id, campaign_id) VALUES (1, 1)")
            conn.execute("INSERT INTO items (id, name, weapon_key, campaign_id) VALUES (1, 'Sword', 'longsword', 1)")
            conn.execute("INSERT INTO item_instances (id, item_id, owner_id, campaign_id) VALUES (1, 1, 1, 1)")
        repository = WeaponEquipmentRepository()
        repository.equip(campaign_id=1, character_entity_id=1, item_instance_id=1)
        assert repository.get_equipped(campaign_id=1, character_entity_id=1)["weapon_key"] == "longsword"
        with pytest.raises(sqlite3.IntegrityError):
            repository.equip(campaign_id=2, character_entity_id=1, item_instance_id=1)
        with get_conn() as conn:
            conn.execute("UPDATE item_instances SET owner_id = NULL WHERE id = 1 AND campaign_id = 1")
        assert repository.get_equipped(campaign_id=1, character_entity_id=1) is None
    finally:
        database.DB_PATH = previous



def test_equipment_slots_allow_multiple_items_and_clear_on_ownership_change(tmp_path):
    previous = setup_db(tmp_path)
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO entities (id, name, entity_type, campaign_id) VALUES (1, 'Hero', 'character', 1)"
            )
            conn.execute(
                "INSERT INTO character_states (entity_id, campaign_id) VALUES (1, 1)"
            )
            conn.execute(
                "INSERT INTO items (id, name, weapon_key, equipment_slot, campaign_id) VALUES (1, 'Sword', 'longsword', 'main_hand', 1)"
            )
            conn.execute(
                "INSERT INTO items (id, name, equipment_slot, campaign_id) VALUES (2, 'Chain mail', 'body', 1)"
            )
            conn.execute(
                "INSERT INTO items (id, name, weapon_key, equipment_slot, campaign_id) VALUES (3, 'Dagger', 'dagger', 'main_hand', 1)"
            )
            conn.execute(
                "INSERT INTO item_instances (id, item_id, owner_id, campaign_id) VALUES (1, 1, 1, 1)"
            )
            conn.execute(
                "INSERT INTO item_instances (id, item_id, owner_id, campaign_id) VALUES (2, 2, 1, 1)"
            )
            conn.execute(
                "INSERT INTO item_instances (id, item_id, owner_id, campaign_id) VALUES (3, 3, 1, 1)"
            )
        repository = WeaponEquipmentRepository()
        repository.equip_item(
            campaign_id=1, character_entity_id=1, item_instance_id=1, slot="main_hand"
        )
        repository.equip_item(
            campaign_id=1, character_entity_id=1, item_instance_id=2, slot="body"
        )
        repository.equip_item(
            campaign_id=1, character_entity_id=1, item_instance_id=3, slot="off_hand"
        )
        inventory = repository.list_inventory(campaign_id=1, character_entity_id=1)
        assert {item["item_instance_id"] for item in inventory} == {1, 2, 3}
        equipped = repository.list_equipped(campaign_id=1, character_entity_id=1)
        assert {item["slot"] for item in equipped} == {"main_hand", "off_hand", "body"}
        assert repository.get_equipped(campaign_id=1, character_entity_id=1)["weapon_key"] == "longsword"

        with pytest.raises(sqlite3.IntegrityError, match="match its slot"):
            repository.equip_item(
                campaign_id=1, character_entity_id=1, item_instance_id=2, slot="off_hand"
            )
        # A failed replacement must roll back the prior off-hand assignment.
        assert repository.get_equipped_slot(
            campaign_id=1, character_entity_id=1, slot="off_hand"
        )["item_instance_id"] == 3

        with get_conn() as conn:
            conn.execute(
                "UPDATE item_instances SET owner_id = NULL WHERE id = 2 AND campaign_id = 1"
            )
        assert [item["slot"] for item in repository.list_equipped(
            campaign_id=1, character_entity_id=1
        )] == ["main_hand", "off_hand"]
    finally:
        database.DB_PATH = previous


def test_equipment_slot_mutation_is_rejected_while_item_is_equipped(tmp_path):
    previous = setup_db(tmp_path)
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO entities (id, name, entity_type, campaign_id) VALUES (1, 'Hero', 'character', 1)"
            )
            conn.execute(
                "INSERT INTO character_states (entity_id, campaign_id) VALUES (1, 1)"
            )
            conn.execute(
                "INSERT INTO items (id, name, equipment_slot, campaign_id) VALUES (1, 'Armor', 'body', 1)"
            )
            conn.execute(
                "INSERT INTO item_instances (id, item_id, owner_id, campaign_id) VALUES (1, 1, 1, 1)"
            )
        repository = WeaponEquipmentRepository()
        repository.equip_item(
            campaign_id=1, character_entity_id=1, item_instance_id=1, slot="body"
        )
        with (
            get_conn() as conn,
            pytest.raises(sqlite3.IntegrityError, match="unequip item"),
        ):
            conn.execute(
                "UPDATE items SET equipment_slot = 'head' WHERE id = 1 AND campaign_id = 1"
            )
    finally:
        database.DB_PATH = previous



def test_armor_item_round_trips_through_world_repository(tmp_path):
    previous = setup_db(tmp_path)
    try:
        state = WorldState(
            entities={1: Entity(id=1, name="Hero", entity_type="character")},
            items={
                1: Item(id=1, name="Leather armor", armor_key="leather"),
                2: Item(id=2, name="Shield", armor_key="shield"),
            },
            item_instances={
                1: ItemInstance(id=1, item_id=1, owner_id=1),
                2: ItemInstance(id=2, item_id=2, owner_id=1),
            },
        )
        repository = WorldRepository()
        repository.save_world(state, campaign_id=1)
        loaded = repository.load_world(campaign_id=1)
        assert loaded.items[1].armor_key == "leather"
        assert loaded.items[1].equipment_slot == "body"
        assert loaded.items[2].armor_key == "shield"
        assert loaded.items[2].equipment_slot == "off_hand"
    finally:
        database.DB_PATH = previous


def test_derived_armor_class_uses_equipped_body_armor_and_shield(tmp_path):
    previous = setup_db(tmp_path)
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO entities (id, name, entity_type, campaign_id) VALUES (1, 'Hero', 'character', 1)"
            )
            conn.execute(
                "INSERT INTO character_states (entity_id, campaign_id) VALUES (1, 1)"
            )
            conn.execute(
                "INSERT INTO items (id, name, armor_key, equipment_slot, campaign_id) VALUES (1, 'Leather', 'leather', 'body', 1)"
            )
            conn.execute(
                "INSERT INTO items (id, name, armor_key, equipment_slot, campaign_id) VALUES (2, 'Shield', 'shield', 'off_hand', 1)"
            )
            conn.execute(
                "INSERT INTO item_instances (id, item_id, owner_id, campaign_id) VALUES (1, 1, 1, 1)"
            )
            conn.execute(
                "INSERT INTO item_instances (id, item_id, owner_id, campaign_id) VALUES (2, 2, 1, 1)"
            )
        repository = WeaponEquipmentRepository()
        repository.equip_item(
            campaign_id=1, character_entity_id=1, item_instance_id=1, slot="body"
        )
        repository.equip_item(
            campaign_id=1, character_entity_id=1, item_instance_id=2, slot="off_hand"
        )
        service = WeaponEquipmentService(repository)
        character = CharacterState(entity_id=1, dexterity=16, strength=10)
        result = service.armor_class(character, campaign_id=1)
        assert result.armor_class == 16
        assert result.armor_key == "leather"
        assert result.shield_bonus == 2
    finally:
        database.DB_PATH = previous


def test_unarmored_armor_class_uses_dexterity_modifier(tmp_path):
    previous = setup_db(tmp_path)
    try:
        service = WeaponEquipmentService(WeaponEquipmentRepository())
        result = service.armor_class(
            CharacterState(entity_id=1, dexterity=16), campaign_id=1
        )
        assert result.armor_class == 13
    finally:
        database.DB_PATH = previous
