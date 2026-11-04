def test_encounter_movement_persists_position_and_enforces_turn_budget(client):
    created = client.post(
        "/encounters",
        json={
            "encounter_id": "tactical-movement",
            "participants": [
                {
                    "name": "Hero", "max_hp": 12, "current_hp": 12,
                    "armor_class": 16, "dexterity": 18,
                    "position_x": 0, "position_y": 0, "speed_feet": 15,
                },
                {
                    "name": "Goblin", "max_hp": 7, "current_hp": 7,
                    "armor_class": 12, "dexterity": 10,
                    "position_x": 5, "position_y": 0,
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    hero_id = next(
        key for key, value in created.json()["combatants"].items()
        if value["name"] == "Hero"
    )
    goblin_id = next(key for key in created.json()["combatants"] if key != hero_id)

    started = client.post(
        "/encounters/tactical-movement/start",
        json={
            "dice_mode": "manual",
            "manual_rolls": {hero_id: 18, goblin_id: 10},
            "initiative_order": [hero_id, goblin_id],
        },
    )
    assert started.status_code == 200, started.text

    moved = client.post(
        "/encounters/tactical-movement/move",
        json={
            "combatant_id": hero_id,
            "expected_round": 1,
            "expected_turn_index": 0,
            "path": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 2, "y": 0}],
        },
    )
    assert moved.status_code == 200, moved.text
    hero = moved.json()["combatants"][hero_id]
    assert (hero["position_x"], hero["position_y"]) == (2, 0)
    assert hero["movement_used_feet"] == 10

    exhausted = client.post(
        "/encounters/tactical-movement/move",
        json={
            "combatant_id": hero_id,
            "expected_round": 1,
            "expected_turn_index": 0,
            "path": [{"x": 2, "y": 0}, {"x": 3, "y": 0}],
        },
    )
    assert exhausted.status_code == 409
    assert "remaining movement" in exhausted.json()["detail"]

    # The movement budget is refreshed when this combatant's next turn begins.
    next_turn = client.post(
        "/encounters/tactical-movement/advance",
        json={"expected_round": 1, "expected_turn_index": 0},
    )
    assert next_turn.status_code == 200, next_turn.text
    hero_turn = client.post(
        "/encounters/tactical-movement/advance",
        json={"expected_round": 1, "expected_turn_index": 1},
    )
    assert hero_turn.status_code == 200, hero_turn.text
    assert hero_turn.json()["active_combatant_id"] == hero_id
    assert hero_turn.json()["combatants"][hero_id]["movement_used_feet"] == 0

    reloaded = client.get("/encounters/tactical-movement")
    assert reloaded.status_code == 200
    assert reloaded.json()["combatants"][hero_id]["position_x"] == 2


def test_encounter_movement_requires_current_position_and_path_origin(client):
    created = client.post(
        "/encounters",
        json={
            "encounter_id": "movement-origin",
            "participants": [
                {"name": "Hero", "max_hp": 10, "current_hp": 10, "armor_class": 12, "dexterity": 12},
            ],
        },
    )
    assert created.status_code == 201
    hero_id = next(iter(created.json()["combatants"]))
    started = client.post(
        "/encounters/movement-origin/start",
        json={"initiative_order": [hero_id]},
    )
    assert started.status_code == 200
    missing_position = client.post(
        "/encounters/movement-origin/move",
        json={
            "combatant_id": hero_id, "expected_round": 1, "expected_turn_index": 0,
            "path": [{"x": 0, "y": 0}, {"x": 1, "y": 0}],
        },
    )
    assert missing_position.status_code == 409


def test_encounter_movement_validates_coordinate_pairs(client):
    response = client.post(
        "/encounters",
        json={
            "participants": [{
                "name": "Hero", "max_hp": 10, "current_hp": 10,
                "armor_class": 12, "dexterity": 12, "position_x": 1,
            }],
        },
    )
    assert response.status_code == 422
