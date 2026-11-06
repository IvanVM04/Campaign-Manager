def test_character_sheet_read_api_returns_player_facing_projection(client):
    created = client.post(
        "/characters",
        json={
            "name": "Aria",
            "class_name": "Wizard",
            "level": 3,
            "max_hp": 18,
            "current_hp": 12,
            "intelligence": 16,
            "skill_proficiencies": ["arcana"],
            "saving_throw_proficiencies": ["intelligence", "wisdom"],
        },
    )
    assert created.status_code == 200, created.text
    character_id = created.json()["character"]["entity_id"]

    response = client.get(f"/characters/{character_id}/sheet")

    assert response.status_code == 200, response.text
    sheet = response.json()
    assert sheet["name"] == "Aria"
    assert sheet["class_name"] == "Wizard"
    assert sheet["level"] == 3
    assert sheet["current_hp"] == 12
    assert sheet["max_hp"] == 18
    assert len(sheet["abilities"]) == 6
    assert len(sheet["saving_throws"]) == 6
    assert len(sheet["skills"]) == 18
    assert next(
        skill for skill in sheet["skills"] if skill["skill"] == "arcana"
    )["modifier"] == 5
    assert "metadata" not in sheet
    assert "notes" not in sheet


def test_character_sheet_read_api_returns_not_found_for_unknown_character(client):
    response = client.get("/characters/999999/sheet")
    assert response.status_code == 404
