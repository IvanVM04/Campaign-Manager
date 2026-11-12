from dataclasses import replace

from database import get_conn, transaction
from repositories.combat_encounter_repository import CombatEncounterRepository
from repositories.creature_repository import CreatureRepository


def _create_npc_attack_encounter(client, *, encounter_id, npc_options):
    target = client.post(
        "/characters",
        json={
            "name": "Target",
            "max_hp": 20,
            "current_hp": 20,
            "armor_class": 10,
            "strength": 10,
            "dexterity": 10,
        },
    )
    assert target.status_code == 200, target.text
    target_id = target.json()["character"]["entity_id"]

    created = client.post(
        "/encounters",
        json={
            "encounter_id": encounter_id,
            "participants": [
                {
                    "name": "Configured NPC",
                    "max_hp": 18,
                    "current_hp": 18,
                    "armor_class": 12,
                    "strength": 16,
                    "dexterity": 12,
                    "proficiency_bonus": 2,
                    **npc_options,
                },
                {"character_id": target_id},
            ],
        },
    )
    assert created.status_code == 201, created.text
    combatants = created.json()["combatants"]
    npc_key = next(key for key in combatants if key.startswith("creature-"))
    target_key = f"character-{target_id}"

    started = client.post(
        f"/encounters/{encounter_id}/start",
        json={
            "dice_mode": "manual",
            "manual_rolls": {npc_key: 18, target_key: 10},
            "initiative_order": [npc_key, target_key],
        },
    )
    assert started.status_code == 200, started.text
    return target_id, npc_key, target_key, combatants[npc_key]["entity_id"]


def test_manual_npc_attack_configuration_is_persisted_in_one_creature_write(
    client,
    monkeypatch,
):
    original_save = CreatureRepository.save_creature
    persisted_metadata = []

    def record_save(self, creature, *, campaign_id, conn):
        persisted_metadata.append(dict(creature.metadata))
        return original_save(
            self,
            creature,
            campaign_id=campaign_id,
            conn=conn,
        )

    monkeypatch.setattr(CreatureRepository, "save_creature", record_save)

    created = client.post(
        "/encounters",
        json={
            "encounter_id": "npc-config-write",
            "participants": [
                {
                    "name": "Configured NPC",
                    "max_hp": 18,
                    "armor_class": 12,
                    "dexterity": 12,
                    "strength": 16,
                    "npc_melee_weapon_keys": ["longsword", "battleaxe"],
                    "npc_melee_proficient": False,
                    "npc_natural_attacks": [
                        {
                            "key": "bite",
                            "name": "Bite",
                            "ability": "strength",
                            "damage_dice": "1d6",
                            "damage_type": "piercing",
                            "reach_feet": 5,
                            "proficient": True,
                        }
                    ],
                    "damage_resistances": ["fire"],
                    "damage_immunities": ["poison"],
                }
            ],
        },
    )

    assert created.status_code == 201, created.text
    assert len(persisted_metadata) == 1
    metadata = persisted_metadata[0]
    assert metadata["npc_melee_attacks"] == [
        {"weapon_key": "longsword", "proficient": False},
        {"weapon_key": "battleaxe", "proficient": False},
    ]
    assert metadata["npc_melee_attack"] == metadata["npc_melee_attacks"][0]
    assert metadata["npc_natural_attacks"][0]["key"] == "bite"
    assert metadata["damage_resistances"] == ["fire"]
    assert metadata["damage_immunities"] == ["poison"]


def test_npc_active_turn_can_select_a_non_default_melee_weapon_and_sync_hp(client):
    target_id, npc_key, target_key, _npc_entity_id = _create_npc_attack_encounter(
        client,
        encounter_id="npc-select-weapon",
        npc_options={
            "npc_melee_weapon_keys": ["battleaxe", "rapier"],
            "npc_melee_proficient": True,
        },
    )

    response = client.post(
        "/encounters/npc-select-weapon/attack",
        json={
            "target_combatant_id": target_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [4],
            "npc_attack_weapon_key": "rapier",
            "finesse_ability": "dexterity",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["attacker_combatant_id"] == npc_key
    assert payload["weapon_key"] == "rapier"
    assert payload["natural_attack_key"] is None
    assert payload["attack_ability"] == "dexterity"
    assert payload["proficient"] is True
    assert payload["damage"]["raw"] == 5
    assert payload["damage"]["target_current_hp"] == 15
    assert payload["encounter"]["combatants"][npc_key]["action_used"] is True

    with get_conn() as conn:
        row = conn.execute(
            "SELECT current_hp FROM character_states WHERE entity_id = ? AND campaign_id = 1",
            (target_id,),
        ).fetchone()
    assert row["current_hp"] == 15


def test_npc_active_turn_can_select_a_natural_attack_profile(client):
    _target_id, npc_key, target_key, _npc_entity_id = _create_npc_attack_encounter(
        client,
        encounter_id="npc-select-natural",
        npc_options={
            "npc_natural_attacks": [
                {
                    "key": "bite",
                    "name": "Bite",
                    "ability": "strength",
                    "damage_dice": "1d6",
                    "damage_type": "piercing",
                    "reach_feet": 5,
                    "proficient": True,
                },
                {
                    "key": "claw",
                    "name": "Claw",
                    "ability": "dexterity",
                    "damage_dice": "1d4",
                    "damage_type": "slashing",
                    "reach_feet": 10,
                    "proficient": False,
                },
            ],
        },
    )

    response = client.post(
        "/encounters/npc-select-natural/attack",
        json={
            "target_combatant_id": target_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [3],
            "npc_natural_attack_key": "claw",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["attacker_combatant_id"] == npc_key
    assert payload["weapon_key"] is None
    assert payload["natural_attack_key"] == "claw"
    assert payload["attack_ability"] == "dexterity"
    assert payload["attack_bonus"] == 1
    assert payload["proficient"] is False
    assert payload["damage"]["type"] == "slashing"
    assert payload["damage"]["raw"] == 4


def test_invalid_persisted_npc_profile_does_not_consume_action_or_change_hp(client):
    target_id, npc_key, target_key, npc_entity_id = _create_npc_attack_encounter(
        client,
        encounter_id="npc-invalid-profile",
        npc_options={
            "npc_natural_attacks": [
                {
                    "key": "bite",
                    "name": "Bite",
                    "ability": "strength",
                    "damage_dice": "1d6",
                    "damage_type": "piercing",
                    "reach_feet": 5,
                    "proficient": True,
                }
            ],
        },
    )
    creature_repository = CreatureRepository()
    creature = creature_repository.get_creature(npc_entity_id, campaign_id=1)
    metadata = dict(creature.metadata)
    metadata["npc_natural_attacks"] = "invalid-persisted-data"
    with transaction("IMMEDIATE") as conn:
        creature_repository.save_creature(
            replace(creature, metadata=metadata),
            campaign_id=1,
            conn=conn,
        )

    response = client.post(
        "/encounters/npc-invalid-profile/attack",
        json={
            "target_combatant_id": target_key,
            "expected_round": 1,
            "expected_turn_index": 0,
            "dice_mode": "manual",
            "manual_attack_rolls": [15],
            "manual_damage_rolls": [3],
        },
    )

    assert response.status_code == 409
    assert "NPC natural attack configuration is invalid" in response.text
    encounter = CombatEncounterRepository().get(
        "npc-invalid-profile",
        campaign_id=1,
    )
    assert encounter.combatants[npc_key].action_used is False
    assert encounter.combatants[target_key].current_hp == 20
    with get_conn() as conn:
        row = conn.execute(
            "SELECT current_hp FROM character_states WHERE entity_id = ? AND campaign_id = 1",
            (target_id,),
        ).fetchone()
    assert row["current_hp"] == 20


def test_existing_creature_profiles_merge_in_one_save_without_erasing_metadata(
    client,
    monkeypatch,
):
    _target_id, _npc_key, _target_key, npc_entity_id = _create_npc_attack_encounter(
        client,
        encounter_id="npc-existing-source",
        npc_options={},
    )
    repository = CreatureRepository()
    creature = repository.get_creature(npc_entity_id, campaign_id=1)
    metadata = dict(creature.metadata)
    metadata["lore"] = {"faction": "Ashen Covenant"}
    with transaction("IMMEDIATE") as conn:
        repository.save_creature(
            replace(creature, metadata=metadata),
            campaign_id=1,
            conn=conn,
        )

    original_save = CreatureRepository.save_creature
    written_metadata = []

    def record_save(self, value, *, campaign_id, conn):
        written_metadata.append(dict(value.metadata))
        return original_save(
            self,
            value,
            campaign_id=campaign_id,
            conn=conn,
        )

    monkeypatch.setattr(CreatureRepository, "save_creature", record_save)
    created = client.post(
        "/encounters",
        json={
            "encounter_id": "npc-existing-config",
            "participants": [
                {
                    "creature_id": npc_entity_id,
                    "npc_melee_weapon_keys": ["longsword", "rapier"],
                    "npc_natural_attacks": [
                        {
                            "key": "bite",
                            "name": "Bite",
                            "ability": "strength",
                            "damage_dice": "1d6",
                            "damage_type": "piercing",
                            "reach_feet": 5,
                            "proficient": True,
                        }
                    ],
                    "damage_vulnerabilities": ["radiant"],
                }
            ],
        },
    )

    assert created.status_code == 201, created.text
    assert len(written_metadata) == 1
    merged = written_metadata[0]
    assert merged["lore"] == {"faction": "Ashen Covenant"}
    assert merged["npc_melee_attacks"] == [
        {"weapon_key": "longsword", "proficient": True},
        {"weapon_key": "rapier", "proficient": True},
    ]
    assert merged["npc_melee_attack"] == merged["npc_melee_attacks"][0]
    assert merged["npc_natural_attacks"][0]["key"] == "bite"
    assert merged["damage_vulnerabilities"] == ["radiant"]
