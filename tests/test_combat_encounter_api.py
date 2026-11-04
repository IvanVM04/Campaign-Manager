def test_encounter_api_lifecycle_with_character_manual_initiative_and_restart_state(client):
    character_response = client.post(
        "/characters",
        json={
            "name": "Aventurera",
            "max_hp": 12,
            "current_hp": 12,
            "armor_class": 16,
            "dexterity": 14,
        },
    )
    assert character_response.status_code == 200
    character_id = character_response.json()["character"]["entity_id"]

    create_response = client.post(
        "/encounters",
        json={
            "encounter_id": "api-encounter-1",
            "participants": [
                {"character_id": character_id},
                {
                    "name": "Goblin",
                    "max_hp": 7,
                    "current_hp": 7,
                    "armor_class": 15,
                    "dexterity": 10,
                },
            ],
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["status"] == "preparing"
    assert len(created["combatants"]) == 2

    hero_id = f"character-{character_id}"
    goblin_id = next(
        key for key in created["combatants"] if key != hero_id
    )
    assert created["combatants"][hero_id]["dexterity"] == 14

    tie_response = client.post(
        "/encounters/api-encounter-1/start",
        json={
            "dice_mode": "manual",
            "manual_rolls": {hero_id: 10, goblin_id: 12},
        },
    )
    assert tie_response.status_code == 409
    assert "initiative_order" in tie_response.json()["detail"]

    start_response = client.post(
        "/encounters/api-encounter-1/start",
        json={
            "dice_mode": "manual",
            "manual_rolls": {hero_id: 10, goblin_id: 12},
            "initiative_order": [hero_id, goblin_id],
        },
    )
    assert start_response.status_code == 200
    started = start_response.json()
    assert started["status"] == "active"
    assert started["round_number"] == 1
    assert started["active_combatant_id"] == hero_id
    assert started["combatants"][hero_id]["initiative"] == 12
    assert started["combatants"][goblin_id]["initiative"] == 12

    advance_response = client.post(
        "/encounters/api-encounter-1/advance",
        json={"expected_round": 1, "expected_turn_index": 0},
    )
    assert advance_response.status_code == 200
    advanced = advance_response.json()
    assert advanced["turn_index"] == 1
    assert advanced["active_combatant_id"] == goblin_id

    stale_response = client.post(
        "/encounters/api-encounter-1/advance",
        json={"expected_round": 1, "expected_turn_index": 0},
    )
    assert stale_response.status_code == 409

    get_response = client.get("/encounters/api-encounter-1")
    assert get_response.status_code == 200
    assert get_response.json()["active_combatant_id"] == goblin_id

    complete_response = client.post(
        "/encounters/api-encounter-1/complete",
        json={"expected_round": 1, "expected_turn_index": 1},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "completed"
    assert complete_response.json()["active_combatant_id"] is None


def test_encounter_api_rejects_invalid_manual_combatant(client):
    response = client.post(
        "/encounters",
        json={
            "participants": [
                {"name": "Goblin", "max_hp": 7, "armor_class": 15}
            ]
        },
    )
    assert response.status_code == 422


def test_encounter_api_scopes_encounters_to_campaign(client):
    created = client.post(
        "/encounters",
        json={
            "encounter_id": "campaign-scope-check",
            "participants": [
                {
                    "name": "Goblin",
                    "max_hp": 7,
                    "armor_class": 15,
                    "dexterity": 10,
                }
            ],
        },
    )
    assert created.status_code == 201

    from app import CampaignRepository
    campaign = CampaignRepository().create_campaign(name="Other campaign")

    from fastapi.testclient import TestClient

    from app import app

    other_client = TestClient(
        app,
        headers={"X-Campaign-Id": str(campaign["id"])},
    )
    response = other_client.get("/encounters/campaign-scope-check")
    assert response.status_code == 404


def test_encounter_api_rejects_duplicate_encounter_id(client):
    payload = {
        "encounter_id": "duplicate-encounter",
        "participants": [
            {
                "name": "Goblin",
                "max_hp": 7,
                "armor_class": 15,
                "dexterity": 10,
            }
        ],
    }
    assert client.post("/encounters", json=payload).status_code == 201
    response = client.post("/encounters", json=payload)
    assert response.status_code == 422


def test_manual_npc_becomes_campaign_creature_and_can_join_later_encounters(client):
    created = client.post(
        "/encounters",
        json={
            "encounter_id": "persist-npc-first",
            "participants": [
                {
                    "name": "Capitán Goblin",
                    "max_hp": 18,
                    "current_hp": 13,
                    "armor_class": 16,
                    "dexterity": 14,
                    "strength": 12,
                    "constitution": 15,
                    "intelligence": 10,
                    "wisdom": 11,
                    "charisma": 8,
                    "proficiency_bonus": 2,
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    combatants = created.json()["combatants"]
    npc = next(iter(combatants.values()))
    creature_id = npc["entity_id"]
    assert creature_id is not None
    assert npc["combatant_id"] == f"creature-{creature_id}"
    assert npc["current_hp"] == 13
    assert npc["strength"] == 12
    assert npc["constitution"] == 15
    assert npc["intelligence"] == 10

    reloaded = client.get("/encounters/persist-npc-first")
    assert reloaded.status_code == 200
    assert reloaded.json()["combatants"][f"creature-{creature_id}"]["wisdom"] == 11

    second = client.post(
        "/encounters",
        json={
            "encounter_id": "persist-npc-second",
            "participants": [{"creature_id": creature_id}],
        },
    )
    assert second.status_code == 201, second.text
    reused = second.json()["combatants"][f"creature-{creature_id}"]
    assert reused["current_hp"] == 13
    assert reused["max_hp"] == 18
    assert reused["armor_class"] == 16
    assert reused["charisma"] == 8


def test_encounter_rejects_creature_reference_from_another_campaign(client):
    created = client.post(
        "/encounters",
        json={
            "participants": [
                {
                    "name": "Orco",
                    "max_hp": 15,
                    "armor_class": 13,
                    "dexterity": 10,
                }
            ],
        },
    )
    assert created.status_code == 201
    creature_id = next(iter(created.json()["combatants"].values()))["entity_id"]

    from fastapi.testclient import TestClient

    from app import CampaignRepository, app

    other_campaign = CampaignRepository().create_campaign(name="NPC isolation")
    other_client = TestClient(app, headers={"X-Campaign-Id": str(other_campaign["id"])})
    response = other_client.post(
        "/encounters",
        json={"participants": [{"creature_id": creature_id}]},
    )
    assert response.status_code == 422
