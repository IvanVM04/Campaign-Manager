from fastapi.testclient import TestClient

def test_character_rest_endpoints_update_sheet_and_campaign_clock(client):
    created = client.post(
        "/characters",
        json={
            "name": "Rest API Hero",
            "class_name": "Fighter",
            "level": 4,
            "current_hp": 5,
            "max_hp": 40,
            "constitution": 14,
        },
    )
    assert created.status_code == 200, created.text
    character_id = created.json()["character"]["entity_id"]

    short = client.post(
        f"/characters/{character_id}/rest/short",
        json={
            "expected_elapsed_minutes": 0,
            "hit_dice_to_spend": 1,
            "dice_mode": "manual",
            "manual_rolls": [8],
        },
    )
    assert short.status_code == 200, short.text
    short_data = short.json()
    assert short_data["hit_die_sides"] == 10
    assert short_data["hit_dice_total"] == 4
    assert short_data["hit_dice_used"] == 1
    assert short_data["hit_dice_available"] == 3
    assert short_data["hp_recovered"] == 10
    assert short_data["campaign_elapsed_minutes"] == 60

    sheet = client.get(f"/characters/{character_id}/sheet")
    assert sheet.status_code == 200, sheet.text
    sheet_data = sheet.json()
    assert sheet_data["hit_die_sides"] == 10
    assert sheet_data["hit_dice_used"] == 1
    assert sheet_data["hit_dice_available"] == 3

    long = client.post(
        f"/characters/{character_id}/rest/long",
        json={"expected_elapsed_minutes": 60},
    )
    assert long.status_code == 200, long.text
    long_data = long.json()
    assert long_data["current_hp"] == 40
    assert long_data["hit_dice_used"] == 0
    assert long_data["hit_dice_recovered"] == 1
    assert long_data["campaign_elapsed_minutes"] == 540

    clock = client.get("/campaign/clock")
    assert clock.status_code == 200
    assert clock.json()["elapsed_minutes"] == 540


def test_character_rest_endpoint_rejects_stale_campaign_clock(client):
    created = client.post(
        "/characters",
        json={"name": "Stale Rest Hero", "max_hp": 10},
    )
    character_id = created.json()["character"]["entity_id"]
    client.post(
        "/campaign/clock/advance",
        json={"minutes": 15, "expected_elapsed_minutes": 0},
    )

    response = client.post(
        f"/characters/{character_id}/rest/short",
        json={"expected_elapsed_minutes": 0},
    )
    assert response.status_code == 409
    assert "clock changed" in response.json()["detail"]


def test_rest_api_rejects_malformed_manual_hit_dice(client):
    created = client.post(
        "/characters",
        json={"name": "Manual Dice Hero", "class_name": "Wizard", "max_hp": 12},
    )
    character_id = created.json()["character"]["entity_id"]

    response = client.post(
        f"/characters/{character_id}/rest/short",
        json={
            "expected_elapsed_minutes": 0,
            "hit_dice_to_spend": 2,
            "dice_mode": "manual",
            "manual_rolls": [6],
        },
    )
    assert response.status_code == 422
