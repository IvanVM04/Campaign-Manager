import json

from database import get_conn
from repositories.combat_encounter_repository import CombatEncounterRepository
from repositories.weapon_equipment_repository import WeaponEquipmentRepository


def _prepare_encounter(client, *, target_is_character=True):
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
    attacker_id, _target_id, _attacker_combatant_id, target_combatant_id = _prepare_encounter(client)
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
