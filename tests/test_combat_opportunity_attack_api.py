import json

from database import get_conn
from repositories.combat_encounter_repository import CombatEncounterRepository
from repositories.weapon_equipment_repository import WeaponEquipmentRepository


def _prepare_opportunity_attack(client):
    mover_response = client.post(
        "/characters",
        json={
            "name": "Mover", "max_hp": 20, "current_hp": 20,
            "armor_class": 10, "strength": 10, "dexterity": 12,
        },
    )
    attacker_response = client.post(
        "/characters",
        json={
            "name": "Guard", "max_hp": 20, "current_hp": 20,
            "armor_class": 16, "strength": 16, "dexterity": 12,
        },
    )
    assert mover_response.status_code == 200
    assert attacker_response.status_code == 200
    mover_id = mover_response.json()["character"]["entity_id"]
    attacker_id = attacker_response.json()["character"]["entity_id"]

    with get_conn() as conn:
        conn.execute(
            "UPDATE character_states SET weapon_proficiencies = ? WHERE entity_id = ? AND campaign_id = 1",
            (json.dumps(["martial_melee"]), attacker_id),
        )
        item_id = conn.execute(
            "INSERT INTO items (name, weapon_key, campaign_id) VALUES (?, ?, 1)",
            ("Guard longsword", "longsword"),
        ).lastrowid
        instance_id = conn.execute(
            "INSERT INTO item_instances (item_id, owner_id, campaign_id, active) VALUES (?, ?, 1, 1)",
            (item_id, attacker_id),
        ).lastrowid

    WeaponEquipmentRepository().equip(
        campaign_id=1,
        character_entity_id=attacker_id,
        item_instance_id=instance_id,
    )

    created = client.post(
        "/encounters",
        json={
            "encounter_id": "opportunity-test",
            "participants": [
                {"character_id": mover_id, "position_x": 1, "position_y": 0},
                {"character_id": attacker_id, "position_x": 0, "position_y": 0},
            ],
        },
    )
    assert created.status_code == 201, created.text
    mover_key = f"character-{mover_id}"
    attacker_key = f"character-{attacker_id}"
    started = client.post(
        "/encounters/opportunity-test/start",
        json={
            "dice_mode": "manual",
            "manual_rolls": {mover_key: 18, attacker_key: 10},
            "initiative_order": [mover_key, attacker_key],
        },
    )
    assert started.status_code == 200, started.text
    return mover_id, attacker_id, mover_key, attacker_key


def _move_mover_out_of_reach(client, mover_key):
    moved = client.post(
        "/encounters/opportunity-test/move",
        json={
            "combatant_id": mover_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "path": [{"x": 1, "y": 0}, {"x": 2, "y": 0}],
        },
    )
    assert moved.status_code == 200, moved.text


def test_opportunity_attack_uses_reaction_and_resolves_normal_weapon_attack(client):
    _mover_id, _attacker_id, mover_key, attacker_key = _prepare_opportunity_attack(client)
    _move_mover_out_of_reach(client, mover_key)

    response = client.post(
        "/encounters/opportunity-test/opportunity-attack",
        json={
            "attacker_combatant_id": attacker_key,
            "target_combatant_id": mover_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "mover_previous_position": {"x": 1, "y": 0},
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["opportunity_attack"] is True
    assert payload["attack"]["hit"] is True
    assert payload["damage"]["target_current_hp"] == 11
    attacker = payload["encounter"]["combatants"][attacker_key]
    assert attacker["reaction_used"] is True
    assert attacker["action_used"] is False
    mover = payload["encounter"]["combatants"][mover_key]
    assert mover["current_hp"] == 11

    with get_conn() as conn:
        hp = conn.execute(
            "SELECT current_hp FROM character_states WHERE entity_id = ? AND campaign_id = 1",
            (_mover_id,),
        ).fetchone()["current_hp"]
    assert hp == 11


def test_opportunity_attack_rejects_movement_that_did_not_leave_reach(client):
    _mover_id, _attacker_id, mover_key, attacker_key = _prepare_opportunity_attack(client)
    _move_mover_out_of_reach(client, mover_key)
    response = client.post(
        "/encounters/opportunity-test/opportunity-attack",
        json={
            "attacker_combatant_id": attacker_key,
            "target_combatant_id": mover_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "mover_previous_position": {"x": 1, "y": 0},
            "disengaging": true,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 409
    assert "does not provoke" in response.json()["detail"]
    encounter = CombatEncounterRepository().get("opportunity-test", campaign_id=1)
    assert encounter.combatants[attacker_key].reaction_used is False


def test_opportunity_attack_consumes_only_one_reaction(client):
    _mover_id, _attacker_id, mover_key, attacker_key = _prepare_opportunity_attack(client)
    _move_mover_out_of_reach(client, mover_key)
    payload = {
        "attacker_combatant_id": attacker_key,
        "target_combatant_id": mover_key,
        "expected_round": 1,
        "expected_turn_index": 0,
        "mover_previous_position": {"x": 1, "y": 0},
        "dice_mode": "manual",
        "manual_attack_rolls": [2],
        "manual_damage_rolls": [],
    }
    first = client.post("/encounters/opportunity-test/opportunity-attack", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["attack"]["hit"] is False
    assert first.json()["encounter"]["combatants"][attacker_key]["reaction_used"] is True

    second = client.post("/encounters/opportunity-test/opportunity-attack", json=payload)
    assert second.status_code == 409
    assert "already used its reaction" in second.json()["detail"]
