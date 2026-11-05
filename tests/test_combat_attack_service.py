import json
from dataclasses import replace

import pytest

from database import get_conn
from repositories.combat_encounter_repository import CombatEncounterRepository
from repositories.creature_repository import CreatureRepository
from repositories.weapon_equipment_repository import WeaponEquipmentRepository


def _prepare_encounter(client, *, target_is_character=True, target_defenses=None):
    attacker_response = client.post(
        "/characters",
        json={
            "name": "Guerrero",
            "max_hp": 20,
            "current_hp": 20,
            "armor_class": 16,
            "strength": 16,
            "dexterity": 12,
        },
    )
    assert attacker_response.status_code == 200
    attacker_id = attacker_response.json()["character"]["entity_id"]

    if target_is_character:
        target_response = client.post(
            "/characters",
            json={
                "name": "Defensor",
                "max_hp": 20,
                "current_hp": 20,
                "armor_class": 10,
                "strength": 10,
                "dexterity": 10,
            },
        )
        assert target_response.status_code == 200
        target_id = target_response.json()["character"]["entity_id"]
        target = {"character_id": target_id}
        target_combatant_id = f"character-{target_id}"
    else:
        target = {
            "name": "Goblin",
            "max_hp": 7,
            "current_hp": 7,
            "armor_class": 10,
            "dexterity": 10,
            **(target_defenses or {}),
        }
        target_id = None
        target_combatant_id = None

    with get_conn() as conn:
        conn.execute(
            "UPDATE character_states SET weapon_proficiencies = ? WHERE entity_id = ? AND campaign_id = 1",
            (json.dumps(["martial_melee"]), attacker_id),
        )
        cursor = conn.execute(
            "INSERT INTO items (name, weapon_key, campaign_id) VALUES (?, ?, 1)",
            ("Test longsword", "longsword"),
        )
        item_id = cursor.lastrowid
        cursor = conn.execute(
            "INSERT INTO item_instances (item_id, owner_id, campaign_id, active) VALUES (?, ?, 1, 1)",
            (item_id, attacker_id),
        )
        instance_id = cursor.lastrowid

    WeaponEquipmentRepository().equip(
        campaign_id=1,
        character_entity_id=attacker_id,
        item_instance_id=instance_id,
    )

    created = client.post(
        "/encounters",
        json={
            "encounter_id": "attack-test",
            "participants": [{"character_id": attacker_id}, target],
        },
    )
    assert created.status_code == 201
    participants = created.json()["combatants"]
    attacker_combatant_id = f"character-{attacker_id}"
    if target_combatant_id is None:
        target_combatant_id = next(key for key in participants if key != attacker_combatant_id)

    started = client.post(
        "/encounters/attack-test/start",
        json={
            "dice_mode": "manual",
            "manual_rolls": {attacker_combatant_id: 18, target_combatant_id: 10},
            "initiative_order": [attacker_combatant_id, target_combatant_id],
        },
    )
    assert started.status_code == 200
    return attacker_id, target_id, attacker_combatant_id, target_combatant_id


def test_attack_api_applies_damage_to_character_and_encounter_in_sync(client):
    _, _, attacker_combatant_id, target_combatant_id = _prepare_encounter(client)
    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_combatant_id,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["attack"]["hit"] is True
    assert payload["damage"]["raw"] == 9
    assert payload["damage"]["target_current_hp"] == 11
    assert payload["encounter"]["combatants"][target_combatant_id]["current_hp"] == 11
    assert payload["encounter"]["combatants"][attacker_combatant_id]["action_used"] is True

    with get_conn() as conn:
        row = conn.execute(
            "SELECT current_hp FROM character_states WHERE entity_id = ? AND campaign_id = 1",
            (int(target_combatant_id.split("-")[1]),),
        ).fetchone()
    assert row["current_hp"] == 11


def test_missed_attack_consumes_action_and_stale_second_attack_is_rejected(client):
    _, _, attacker_id, target_id = _prepare_encounter(client, target_is_character=False)
    miss = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_id,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [2],
            "manual_damage_rolls": [],
        },
    )
    assert miss.status_code == 200, miss.text
    assert miss.json()["attack"]["hit"] is False
    assert miss.json()["encounter"]["combatants"][attacker_id]["action_used"] is True

    second = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_id,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert second.status_code == 409


def test_attack_transaction_rolls_back_if_encounter_snapshot_save_fails(client, monkeypatch):
    _, target_id, attacker_combatant_id, target_combatant_id = _prepare_encounter(client)
    original_save = CombatEncounterRepository.save

    def fail_save(*args, **kwargs):
        raise RuntimeError("simulated encounter write failure")

    monkeypatch.setattr(CombatEncounterRepository, "save", fail_save)
    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_combatant_id,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 409
    monkeypatch.setattr(CombatEncounterRepository, "save", original_save)

    with get_conn() as conn:
        hp = conn.execute(
            "SELECT current_hp FROM character_states WHERE entity_id = ? AND campaign_id = 1",
            (target_id,),
        ).fetchone()["current_hp"]
    encounter = CombatEncounterRepository().get("attack-test", campaign_id=1)
    assert hp == 20
    assert encounter.combatants[target_combatant_id].current_hp == 20
    assert encounter.combatants[attacker_combatant_id].action_used is False


def test_attack_rejects_manual_npc_as_attacker(client):
    _, _, attacker_id, target_id = _prepare_encounter(client, target_is_character=False)
    from repositories.combat_encounter_repository import CombatEncounterRepository

    repository = CombatEncounterRepository()
    encounter = repository.get("attack-test", campaign_id=1)
    from dataclasses import replace
    encounter.combatants[attacker_id] = replace(
        encounter.combatants[attacker_id], is_player_character=False, entity_id=None
    )
    repository.save(encounter, campaign_id=1)
    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_id,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 409


def test_persistent_poisoned_attacker_has_disadvantage_on_attack(client):
    attacker_id, _target_id, _attacker_combatant_id, target_combatant_id = _prepare_encounter(
        client
    )
    effect = client.post(
        f"/entities/{attacker_id}/effects",
        json={"effect_type": "condition", "effect_key": "poisoned", "name": "Veneno persistente"},
    )
    assert effect.status_code == 201, effect.text
    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_combatant_id,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [18, 4],
            "manual_damage_rolls": [],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["disadvantage"] is True


def test_npc_damage_is_persisted_and_reused_across_encounters(client):
    _attacker_entity_id, _target, attacker_id, target_id = _prepare_encounter(
        client, target_is_character=False
    )
    encounter = CombatEncounterRepository().get("attack-test", campaign_id=1)
    creature_entity_id = encounter.combatants[target_id].entity_id
    assert creature_entity_id is not None

    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_id,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["damage"]["target_current_hp"] == 0

    with get_conn() as conn:
        row = conn.execute(
            "SELECT current_hp, max_hp FROM creature_states WHERE entity_id = ? AND campaign_id = 1",
            (creature_entity_id,),
        ).fetchone()
    assert row["current_hp"] == 0
    assert row["max_hp"] == 7

    reused = client.post(
        "/encounters",
        json={
            "encounter_id": "reuse-persisted-npc",
            "participants": [
                {"character_id": int(attacker_id.split("-")[1])},
                {"creature_id": creature_entity_id},
            ],
        },
    )
    assert reused.status_code == 201, reused.text
    reused_combatants = reused.json()["combatants"]
    npc = reused_combatants[f"creature-{creature_entity_id}"]
    assert npc["entity_id"] == creature_entity_id
    assert npc["current_hp"] == 0
    assert npc["defeated"] is True


def test_attack_uses_current_equipped_armor_and_shield_for_player_target(client):
    _, target_id, _attacker_combatant_id, target_combatant_id = _prepare_encounter(client)
    with get_conn() as conn:
        armor_id = conn.execute(
            "INSERT INTO items (name, armor_key, equipment_slot, campaign_id) VALUES (?, ?, ?, 1)",
            ("Target leather armor", "leather", "body"),
        ).lastrowid
        shield_id = conn.execute(
            "INSERT INTO items (name, armor_key, equipment_slot, campaign_id) VALUES (?, ?, ?, 1)",
            ("Target shield", "shield", "off_hand"),
        ).lastrowid
        armor_instance = conn.execute(
            "INSERT INTO item_instances (item_id, owner_id, campaign_id, active) VALUES (?, ?, 1, 1)",
            (armor_id, target_id),
        ).lastrowid
        shield_instance = conn.execute(
            "INSERT INTO item_instances (item_id, owner_id, campaign_id, active) VALUES (?, ?, 1, 1)",
            (shield_id, target_id),
        ).lastrowid

    equipment = WeaponEquipmentRepository()
    equipment.equip_item(
        campaign_id=1, character_entity_id=target_id,
        item_instance_id=armor_instance, slot="body",
    )
    equipment.equip_item(
        campaign_id=1, character_entity_id=target_id,
        item_instance_id=shield_instance, slot="off_hand",
    )

    equipped_response = client.get(f"/characters/{target_id}/equipment")
    assert equipped_response.status_code == 200
    assert equipped_response.json()["armor_class"] == 13

    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_combatant_id,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [7],
            "manual_damage_rolls": [],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["attack"]["hit"] is False
    assert payload["attack"]["target_ac"] == 13
    assert payload["encounter"]["combatants"][target_combatant_id]["armor_class"] == 13


def test_unproficient_armor_imposes_disadvantage_on_strength_attack(client):
    attacker_id, _target_id, _attacker_combatant_id, target_combatant_id = _prepare_encounter(client)
    with get_conn() as conn:
        armor_id = conn.execute(
            "INSERT INTO items (name, armor_key, equipment_slot, campaign_id) VALUES (?, ?, ?, 1)",
            ("Untrained leather armor", "leather", "body"),
        ).lastrowid
        armor_instance = conn.execute(
            "INSERT INTO item_instances (item_id, owner_id, campaign_id, active) VALUES (?, ?, 1, 1)",
            (armor_id, attacker_id),
        ).lastrowid

    WeaponEquipmentRepository().equip_item(
        campaign_id=1,
        character_entity_id=attacker_id,
        item_instance_id=armor_instance,
        slot="body",
    )

    equipment = client.get(f"/characters/{attacker_id}/equipment")
    assert equipment.status_code == 200
    assert equipment.json()["armor_proficiency"]["armor_proficient"] is False
    assert equipment.json()["armor_proficiency"]["spellcasting_blocked"] is True

    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_combatant_id,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [18, 4],
            "manual_damage_rolls": [],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["disadvantage"] is True
    assert payload["armor_training_penalty"] is True
    assert payload["attack"]["selected"] == 4



def _set_character_target_to_zero_hp(target_id, *, failures=0):
    repository = CombatEncounterRepository()
    encounter = repository.get("attack-test", campaign_id=1)
    target_key = f"character-{target_id}"
    target = encounter.combatants[target_key]
    encounter.combatants[target_key] = replace(
        target,
        current_hp=0,
        conscious=False,
        death_save_successes=0,
        death_save_failures=failures,
        stable=False,
        dead=False,
    )
    with get_conn() as conn:
        conn.execute(
            "UPDATE character_states SET current_hp = 0 WHERE entity_id = ? AND campaign_id = 1",
            (target_id,),
        )
    repository.save(encounter, campaign_id=1)
    return target_key


def test_attack_against_downed_character_adds_one_death_save_failure(client):
    _, target_id, _attacker_id, _target_combatant_id = _prepare_encounter(client)
    target_key = _set_character_target_to_zero_hp(target_id)

    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 200, response.text
    combatant = response.json()["encounter"]["combatants"][target_key]
    assert combatant["current_hp"] == 0
    assert combatant["conscious"] is False
    assert combatant["death_save_failures"] == 1
    assert combatant["stable"] is False
    assert combatant["dead"] is False


def test_critical_hit_against_downed_character_adds_two_failures(client):
    _, target_id, _attacker_id, _target_combatant_id = _prepare_encounter(client)
    target_key = _set_character_target_to_zero_hp(target_id)

    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [20],
            "manual_damage_rolls": [6, 6],
        },
    )
    assert response.status_code == 200, response.text
    combatant = response.json()["encounter"]["combatants"][target_key]
    assert combatant["death_save_failures"] == 2
    assert combatant["dead"] is False
    assert combatant["current_hp"] == 0


def test_damage_to_stable_character_makes_them_unstable_again(client):
    _, target_id, _attacker_id, _target_combatant_id = _prepare_encounter(client)
    target_key = _set_character_target_to_zero_hp(target_id)
    repository = CombatEncounterRepository()
    encounter = repository.get("attack-test", campaign_id=1)
    encounter.combatants[target_key] = replace(
        encounter.combatants[target_key],
        death_save_successes=3,
        stable=True,
    )
    repository.save(encounter, campaign_id=1)

    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 200, response.text
    combatant = response.json()["encounter"]["combatants"][target_key]
    assert combatant["stable"] is False
    assert combatant["death_save_failures"] == 1
    assert combatant["death_save_successes"] == 0



def test_third_failure_from_damage_kills_downed_character(client):
    _, target_id, _attacker_id, _target_combatant_id = _prepare_encounter(client)
    target_key = _set_character_target_to_zero_hp(target_id, failures=2)

    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 200, response.text
    combatant = response.json()["encounter"]["combatants"][target_key]
    assert combatant["death_save_failures"] == 3
    assert combatant["dead"] is True
    assert combatant["current_hp"] == 0
    assert combatant["conscious"] is False



def test_massive_damage_kills_character_when_excess_reaches_max_hp(client):
    _, target_id, _attacker_id, _target_combatant_id = _prepare_encounter(client)
    target_key = f"character-{target_id}"
    repository = CombatEncounterRepository()
    encounter = repository.get("attack-test", campaign_id=1)
    target = encounter.combatants[target_key]
    encounter.combatants[target_key] = replace(
        target,
        current_hp=1,
        max_hp=5,
        conscious=True,
    )
    with get_conn() as conn:
        conn.execute(
            "UPDATE character_states SET current_hp = 1, max_hp = 5 WHERE entity_id = ? AND campaign_id = 1",
            (target_id,),
        )
    repository.save(encounter, campaign_id=1)

    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 200, response.text
    combatant = response.json()["encounter"]["combatants"][target_key]
    assert combatant["current_hp"] == 0
    assert combatant["dead"] is True
    assert combatant["conscious"] is False
    assert combatant["death_save_failures"] == 3


@pytest.mark.parametrize(
    ("defenses", "expected_damage", "expected_hp", "expected_flags"),
    [
        ({"damage_resistances": ["slashing"]}, 4, 3, (False, True, False)),
        ({"damage_vulnerabilities": ["slashing"]}, 18, 0, (False, False, True)),
        ({"damage_immunities": ["slashing"]}, 0, 7, (True, False, False)),
        (
            {
                "damage_resistances": ["slashing"],
                "damage_vulnerabilities": ["slashing"],
            },
            9,
            0,
            (False, True, True),
        ),
    ],
)
def test_npc_damage_defenses_are_persisted_and_applied_to_weapon_attacks(
    client, defenses, expected_damage, expected_hp, expected_flags
):
    _attacker_id, _target_id, _attacker_key, target_key = _prepare_encounter(
        client, target_is_character=False, target_defenses=defenses
    )
    encounter = CombatEncounterRepository().get("attack-test", campaign_id=1)
    target_entity_id = encounter.combatants[target_key].entity_id
    creature = CreatureRepository().get_creature(target_entity_id, campaign_id=1)
    for field_name, values in defenses.items():
        assert creature.metadata[field_name] == values

    response = client.post(
        "/encounters/attack-test/attack",
        json={
            "target_combatant_id": target_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["damage"]["raw"] == 9
    assert payload["damage"]["after_defenses"] == expected_damage
    assert payload["damage"]["target_current_hp"] == expected_hp
    assert (
        payload["damage"]["defenses"]["immune"],
        payload["damage"]["defenses"]["resistant"],
        payload["damage"]["defenses"]["vulnerable"],
    ) == expected_flags
