import json

import pytest

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


def test_opportunity_attack_rejects_disengaging_movement(client):
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
            "disengaging": True,
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



def test_npc_opportunity_attacker_uses_persisted_creature_weapon_profile(client):
    mover_response = client.post(
        "/characters",
        json={
            "name": "Escaping hero", "max_hp": 20, "current_hp": 20,
            "armor_class": 10, "strength": 10, "dexterity": 12,
        },
    )
    assert mover_response.status_code == 200, mover_response.text
    mover_id = mover_response.json()["character"]["entity_id"]
    created = client.post(
        "/encounters",
        json={
            "encounter_id": "npc-opportunity-test",
            "participants": [
                {
                    "character_id": mover_id,
                    "position_x": 1,
                    "position_y": 0,
                },
                {
                    "name": "Orc guard",
                    "max_hp": 15,
                    "current_hp": 15,
                    "armor_class": 13,
                    "strength": 16,
                    "dexterity": 10,
                    "proficiency_bonus": 2,
                    "position_x": 0,
                    "position_y": 0,
                    "npc_melee_weapon_key": "longsword",
                    "npc_melee_proficient": True,
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    mover_key = f"character-{mover_id}"
    npc_key = next(
        key for key in created.json()["combatants"] if key.startswith("creature-")
    )
    started = client.post(
        "/encounters/npc-opportunity-test/start",
        json={
            "dice_mode": "manual",
            "manual_rolls": {mover_key: 18, npc_key: 10},
            "initiative_order": [mover_key, npc_key],
        },
    )
    assert started.status_code == 200, started.text
    moved = client.post(
        "/encounters/npc-opportunity-test/move",
        json={
            "combatant_id": mover_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "path": [{"x": 1, "y": 0}, {"x": 2, "y": 0}],
        },
    )
    assert moved.status_code == 200, moved.text

    response = client.post(
        "/encounters/npc-opportunity-test/opportunity-attack",
        json={
            "attacker_combatant_id": npc_key,
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
    assert payload["weapon_key"] == "longsword"
    assert payload["attack"]["hit"] is True
    assert payload["damage"]["target_current_hp"] == 13
    assert payload["encounter"]["combatants"][npc_key]["reaction_used"] is True

    creature_id = int(npc_key.split("-")[1])
    with get_conn() as conn:
        row = conn.execute(
            "SELECT current_hp, metadata FROM creature_states WHERE entity_id = ? AND campaign_id = 1",
            (creature_id,),
        ).fetchone()
    assert row["current_hp"] == 15
    assert json.loads(row["metadata"])["npc_melee_attack"]["weapon_key"] == "longsword"


def test_npc_without_melee_profile_cannot_make_opportunity_attack(client):
    mover_response = client.post(
        "/characters",
        json={
            "name": "Escaping hero", "max_hp": 20, "current_hp": 20,
            "armor_class": 10, "strength": 10, "dexterity": 12,
        },
    )
    mover_id = mover_response.json()["character"]["entity_id"]
    created = client.post(
        "/encounters",
        json={
            "encounter_id": "npc-no-profile-test",
            "participants": [
                {"character_id": mover_id, "position_x": 1, "position_y": 0},
                {
                    "name": "Unarmed guard", "max_hp": 15, "armor_class": 12,
                    "dexterity": 10, "position_x": 0, "position_y": 0,
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    mover_key = f"character-{mover_id}"
    npc_key = next(
        key for key in created.json()["combatants"] if key.startswith("creature-")
    )
    started = client.post(
        "/encounters/npc-no-profile-test/start",
        json={
            "dice_mode": "manual",
            "manual_rolls": {mover_key: 18, npc_key: 10},
            "initiative_order": [mover_key, npc_key],
        },
    )
    assert started.status_code == 200, started.text
    moved = client.post(
        "/encounters/npc-no-profile-test/move",
        json={
            "combatant_id": mover_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "path": [{"x": 1, "y": 0}, {"x": 2, "y": 0}],
        },
    )
    assert moved.status_code == 200, moved.text
    response = client.post(
        "/encounters/npc-no-profile-test/opportunity-attack",
        json={
            "attacker_combatant_id": npc_key,
            "target_combatant_id": mover_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "mover_previous_position": {"x": 1, "y": 0},
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 409
    assert "configured melee weapon profile" in response.json()["detail"]
    encounter = CombatEncounterRepository().get("npc-no-profile-test", campaign_id=1)
    assert encounter.combatants[npc_key].reaction_used is False



@pytest.mark.parametrize(
    ("weapon_key", "detail"),
    [
        ("not-a-real-weapon", "unknown NPC melee weapon profile"),
        ("shortbow", "supported melee weapons"),
        ("lance", "supported melee weapons"),
    ],
)
def test_encounter_rejects_unsupported_npc_opportunity_profiles(
    client, weapon_key, detail
):
    response = client.post(
        "/encounters",
        json={
            "encounter_id": f"invalid-npc-profile-{weapon_key}",
            "participants": [
                {
                    "name": "Invalid profile NPC",
                    "max_hp": 12,
                    "armor_class": 12,
                    "dexterity": 10,
                    "npc_melee_weapon_key": weapon_key,
                }
            ],
        },
    )

    assert response.status_code == 422
    assert detail in response.json()["detail"]



def test_npc_can_select_between_multiple_melee_weapons_for_opportunity_attack(client):
    mover_response = client.post(
        "/characters",
        json={
            "name": "Retreating hero", "max_hp": 20, "current_hp": 20,
            "armor_class": 10, "strength": 10, "dexterity": 12,
        },
    )
    assert mover_response.status_code == 200, mover_response.text
    mover_id = mover_response.json()["character"]["entity_id"]
    created = client.post(
        "/encounters",
        json={
            "encounter_id": "npc-multiple-weapons-test",
            "participants": [
                {
                    "character_id": mover_id,
                    "position_x": 2,
                    "position_y": 0,
                },
                {
                    "name": "Whip sentinel",
                    "max_hp": 18,
                    "current_hp": 18,
                    "armor_class": 14,
                    "strength": 16,
                    "dexterity": 10,
                    "proficiency_bonus": 2,
                    "position_x": 0,
                    "position_y": 0,
                    "npc_melee_weapon_keys": ["longsword", "whip"],
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    mover_key = f"character-{mover_id}"
    npc_key = next(
        key for key in created.json()["combatants"] if key.startswith("creature-")
    )
    started = client.post(
        "/encounters/npc-multiple-weapons-test/start",
        json={
            "dice_mode": "manual",
            "manual_rolls": {mover_key: 18, npc_key: 10},
            "initiative_order": [mover_key, npc_key],
        },
    )
    assert started.status_code == 200, started.text
    moved = client.post(
        "/encounters/npc-multiple-weapons-test/move",
        json={
            "combatant_id": mover_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "path": [{"x": 2, "y": 0}, {"x": 3, "y": 0}],
        },
    )
    assert moved.status_code == 200, moved.text

    response = client.post(
        "/encounters/npc-multiple-weapons-test/opportunity-attack",
        json={
            "attacker_combatant_id": npc_key,
            "target_combatant_id": mover_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "mover_previous_position": {"x": 2, "y": 0},
            "reach_feet": 10,
            "npc_attack_weapon_key": "whip",
            "dice_mode": "manual",
            "manual_attack_rolls": [10],
            "manual_damage_rolls": [4],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["weapon_key"] == "whip"
    assert payload["attack"]["hit"] is True
    assert payload["damage"]["target_current_hp"] == 11
    assert payload["encounter"]["combatants"][npc_key]["reaction_used"] is True

    creature_id = int(npc_key.split("-")[1])
    with get_conn() as conn:
        row = conn.execute(
            "SELECT metadata FROM creature_states WHERE entity_id = ? AND campaign_id = 1",
            (creature_id,),
        ).fetchone()
    metadata = json.loads(row["metadata"])
    assert [profile["weapon_key"] for profile in metadata["npc_melee_attacks"]] == [
        "longsword", "whip"
    ]


def test_npc_cannot_select_an_unconfigured_opportunity_weapon(client):
    mover_response = client.post(
        "/characters",
        json={
            "name": "Retreating hero", "max_hp": 20, "current_hp": 20,
            "armor_class": 10, "strength": 10, "dexterity": 12,
        },
    )
    mover_id = mover_response.json()["character"]["entity_id"]
    created = client.post(
        "/encounters",
        json={
            "encounter_id": "npc-unconfigured-weapon-test",
            "participants": [
                {"character_id": mover_id, "position_x": 1, "position_y": 0},
                {
                    "name": "Guard", "max_hp": 15, "armor_class": 12,
                    "strength": 14, "dexterity": 10, "position_x": 0,
                    "position_y": 0, "npc_melee_weapon_keys": ["longsword"],
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    mover_key = f"character-{mover_id}"
    npc_key = next(
        key for key in created.json()["combatants"] if key.startswith("creature-")
    )
    started = client.post(
        "/encounters/npc-unconfigured-weapon-test/start",
        json={
            "dice_mode": "manual",
            "manual_rolls": {mover_key: 18, npc_key: 10},
            "initiative_order": [mover_key, npc_key],
        },
    )
    assert started.status_code == 200, started.text
    moved = client.post(
        "/encounters/npc-unconfigured-weapon-test/move",
        json={
            "combatant_id": mover_key, "expected_round": 1,
            "expected_turn_index": 0,
            "path": [{"x": 1, "y": 0}, {"x": 2, "y": 0}],
        },
    )
    assert moved.status_code == 200, moved.text
    response = client.post(
        "/encounters/npc-unconfigured-weapon-test/opportunity-attack",
        json={
            "attacker_combatant_id": npc_key,
            "target_combatant_id": mover_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "mover_previous_position": {"x": 1, "y": 0},
            "npc_attack_weapon_key": "whip",
            "dice_mode": "manual",
            "manual_attack_rolls": [10],
            "manual_damage_rolls": [6],
        },
    )
    assert response.status_code == 409
    assert "not configured" in response.json()["detail"]
    encounter = CombatEncounterRepository().get(
        "npc-unconfigured-weapon-test", campaign_id=1
    )
    assert encounter.combatants[npc_key].reaction_used is False
