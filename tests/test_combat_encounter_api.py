from database import get_conn


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
            "initiative_order": (
                [hero_id, goblin_id] if hero_first else [goblin_id, hero_id]
            ),
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



def test_encounter_turn_mutations_require_complete_expected_position(client):
    for action in ("advance", "complete"):
        missing = client.post(f"/encounters/missing-position/{action}", json={})
        assert missing.status_code == 422

        missing_round = client.post(
            f"/encounters/missing-round/{action}",
            json={"expected_turn_index": 0},
        )
        assert missing_round.status_code == 422

        missing_turn = client.post(
            f"/encounters/missing-turn/{action}",
            json={"expected_round": 1},
        )
        assert missing_turn.status_code == 422


def test_encounter_turn_mutations_reject_boolean_position_values(client):
    for action in ("advance", "complete"):
        response = client.post(
            f"/encounters/invalid-position/{action}",
            json={"expected_round": True, "expected_turn_index": False},
        )
        assert response.status_code == 422


def _create_downed_character_encounter(
    client, encounter_id, *, hero_first=False, return_start=False
):
    character = client.post(
        "/characters",
        json={
            "name": "Aventurero caído",
            "max_hp": 12,
            "current_hp": 0,
            "armor_class": 12,
            "dexterity": 10,
        },
    )
    assert character.status_code == 200, character.text
    character_id = character.json()["character"]["entity_id"]
    hero_id = f"character-{character_id}"
    created = client.post(
        "/encounters",
        json={
            "encounter_id": encounter_id,
            "participants": [
                {"character_id": character_id},
                {
                    "name": "Goblin",
                    "max_hp": 7,
                    "current_hp": 7,
                    "armor_class": 12,
                    "dexterity": 10,
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    goblin_id = next(key for key in created.json()["combatants"] if key != hero_id)
    started = client.post(
        f"/encounters/{encounter_id}/start",
        json={
            "dice_mode": "manual",
            "manual_rolls": {hero_id: 18, goblin_id: 10},
            "initiative_order": [hero_id, goblin_id],
        },
    )
    assert started.status_code == 200, started.text
    if return_start:
        return character_id, hero_id, goblin_id, started.json()
    return character_id, hero_id, goblin_id


def _advance_back_to_hero(client, encounter_id, current_round=1):
    # Encounters created by the helper put the NPC first and the downed PC second.
    npc_turn = client.post(
        f"/encounters/{encounter_id}/advance",
        json={"expected_round": current_round, "expected_turn_index": 1},
    )
    assert npc_turn.status_code == 200, npc_turn.text
    hero_turn = client.post(
        f"/encounters/{encounter_id}/advance",
        json={"expected_round": current_round + 1, "expected_turn_index": 0},
    )
    assert hero_turn.status_code == 200, hero_turn.text
    assert hero_turn.json()["round_number"] == current_round + 1
    assert hero_turn.json()["turn_index"] == 1


def test_death_save_persists_failure_and_rejects_second_save_in_same_turn(client):
    _character_id, hero_id, _goblin_id = _create_downed_character_encounter(
        client, "death-save-once"
    )
    payload = {
        "expected_round": 1,
        "expected_turn_index": 1,
        "dice_mode": "manual",
        "manual_roll": 7,
    }
    response = client.post("/encounters/death-save-once/death-save", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["death_save"]["failures"] == 1
    assert response.json()["encounter"]["combatants"][hero_id]["death_save_failures"] == 1

    repeated = client.post("/encounters/death-save-once/death-save", json=payload)
    assert repeated.status_code == 409
    reloaded = client.get("/encounters/death-save-once")
    assert reloaded.json()["combatants"][hero_id]["death_save_failures"] == 1


def test_natural_twenty_recovers_character_and_clears_death_save_track(client, monkeypatch):
    _patch_death_save_roll(monkeypatch, 20)
    character_id, hero_id, _goblin_id = _create_downed_character_encounter(
        client, "death-save-recovery"
    )
    first = client.post(
        "/encounters/death-save-recovery/death-save",
        json={
            "expected_round": 1,
            "expected_turn_index": 1,
            "dice_mode": "manual",
            "manual_roll": 4,
        },
    )
    assert first.status_code == 200, first.text
    _advance_back_to_hero(client, "death-save-recovery")

    current = client.get("/encounters/death-save-recovery")
    assert current.status_code == 200, current.text
    combatant = current.json()["combatants"][hero_id]
    assert combatant["current_hp"] == 1
    assert combatant["conscious"] is True
    assert combatant["death_save_successes"] == 0
    assert combatant["death_save_failures"] == 0

    with get_conn() as conn:
        row = conn.execute(
            "SELECT current_hp FROM character_states WHERE entity_id = ? AND campaign_id = 1",
            (character_id,),
        ).fetchone()
    assert row["current_hp"] == 1


def test_third_death_save_success_stabilizes_and_prevents_more_saves(client, monkeypatch):
    _patch_death_save_roll(monkeypatch, [15, 10])
    _character_id, hero_id, _goblin_id = _create_downed_character_encounter(
        client, "death-save-stable"
    )
    first = client.post(
        "/encounters/death-save-stable/death-save",
        json={
            "expected_round": 1,
            "expected_turn_index": 1,
            "dice_mode": "manual",
            "manual_roll": 15,
        },
    )
    assert first.status_code == 200, first.text

    _advance_back_to_hero(client, "death-save-stable", current_round=1)
    _advance_back_to_hero(client, "death-save-stable", current_round=2)

    current = client.get("/encounters/death-save-stable")
    assert current.status_code == 200, current.text
    combatant = current.json()["combatants"][hero_id]
    assert combatant["stable"] is True
    assert combatant["death_save_successes"] == 3

    blocked = client.post(
        "/encounters/death-save-stable/death-save",
        json={
            "expected_round": 3,
            "expected_turn_index": 1,
            "dice_mode": "manual",
            "manual_roll": 10,
        },
    )
    assert blocked.status_code == 409



def _patch_death_save_roll(monkeypatch, value):
    from rules_engine.dnd5e_2014.core.dice import D20Roll, DiceRoller, RollMode

    values = iter(value if isinstance(value, (list, tuple)) else [value])
    original_roll = DiceRoller.roll_d20

    def fixed_roll(self, **kwargs):
        # Keep explicitly supplied initiative rolls untouched; only replace
        # the automatic d20 used by the death-save resolver.
        if kwargs.get("manual_rolls") is not None:
            return original_roll(self, **kwargs)
        roll = next(values)
        return D20Roll(
            rolls=(roll,),
            selected=roll,
            mode=RollMode.NORMAL,
            modifier=0,
            total=roll,
        )

    monkeypatch.setattr(DiceRoller, "roll_d20", fixed_roll)

def test_down_player_character_makes_automatic_save_when_its_turn_begins(client, monkeypatch):
    _patch_death_save_roll(monkeypatch, 10)
    _character_id, hero_id, _goblin_id = _create_downed_character_encounter(
        client, "automatic-death-save"
    )

    started = client.get("/encounters/automatic-death-save")
    assert started.status_code == 200
    # The NPC is first, so starting the encounter must not roll for the PC.
    start_response = client.post(
        "/encounters/automatic-death-save/advance",
        json={"expected_round": 1, "expected_turn_index": 0},
    )
    assert start_response.status_code == 200, start_response.text
    payload = start_response.json()
    assert payload["round_number"] == 1
    assert payload["turn_index"] == 1
    assert payload["active_combatant_id"] == hero_id
    assert payload["turn_start_death_save"]["selected"] == 10
    assert payload["turn_start_death_save"]["successes"] == 1
    assert payload["combatants"][hero_id]["death_save_successes"] == 1
    assert payload["combatants"][hero_id]["death_save_last_round"] == 1
    assert payload["combatants"][hero_id]["death_save_last_turn_index"] == 1

    repeated = client.post(
        "/encounters/automatic-death-save/death-save",
        json={
            "expected_round": 1,
            "expected_turn_index": 1,
            "dice_mode": "manual",
            "manual_roll": 15,
        },
    )
    assert repeated.status_code == 409


def test_first_combatant_makes_death_save_during_encounter_start(client, monkeypatch):
    _patch_death_save_roll(monkeypatch, 10)
    _character_id, hero_id, _goblin_id, started = _create_downed_character_encounter(
        client,
        "automatic-death-save-first",
        hero_first=True,
        return_start=True,
    )

    assert started["active_combatant_id"] == hero_id
    assert started["turn_start_death_save"]["selected"] == 10
    assert started["turn_start_death_save"]["successes"] == 1
    combatant = started["combatants"][hero_id]
    assert combatant["death_save_successes"] == 1
    assert combatant["death_save_last_round"] == 1
    assert combatant["death_save_last_turn_index"] == 0


def test_first_turn_natural_twenty_recovers_and_persists_hp(client, monkeypatch):
    _patch_death_save_roll(monkeypatch, 20)
    character_id, hero_id, _goblin_id, started = _create_downed_character_encounter(
        client,
        "automatic-death-save-first-recovery",
        hero_first=True,
        return_start=True,
    )

    assert started["turn_start_death_save"]["selected"] == 20
    assert started["turn_start_death_save"]["regained_hp"] == 1
    combatant = started["combatants"][hero_id]
    assert combatant["current_hp"] == 1
    assert combatant["conscious"] is True
    assert combatant["death_save_successes"] == 0
    assert combatant["death_save_failures"] == 0

    with get_conn() as conn:
        row = conn.execute(
            "SELECT current_hp FROM character_states WHERE entity_id = ? AND campaign_id = 1",
            (character_id,),
        ).fetchone()
    assert row["current_hp"] == 1


def test_non_first_downed_character_waits_until_its_turn_starts(client, monkeypatch):
    _patch_death_save_roll(monkeypatch, 10)
    _character_id, hero_id, _goblin_id, started = _create_downed_character_encounter(
        client,
        "automatic-death-save-not-first",
        return_start=True,
    )

    assert started["active_combatant_id"] != hero_id
    assert started["turn_start_death_save"] is None
    assert started["combatants"][hero_id]["death_save_successes"] == 0

    hero_turn = client.post(
        "/encounters/automatic-death-save-not-first/advance",
        json={"expected_round": 1, "expected_turn_index": 0},
    )
    assert hero_turn.status_code == 200, hero_turn.text
    assert hero_turn.json()["active_combatant_id"] == hero_id
    assert hero_turn.json()["turn_start_death_save"]["selected"] == 10


def test_automatic_natural_twenty_recovers_character_and_persists_hp(client, monkeypatch):
    _patch_death_save_roll(monkeypatch, 20)
    character_id, hero_id, _goblin_id = _create_downed_character_encounter(
        client, "automatic-death-save-recovery"
    )

    recovery = client.post(
        "/encounters/automatic-death-save-recovery/advance",
        json={"expected_round": 1, "expected_turn_index": 0},
    )
    assert recovery.status_code == 200, recovery.text
    payload = recovery.json()
    assert payload["turn_start_death_save"]["selected"] == 20
    assert payload["turn_start_death_save"]["regained_hp"] == 1
    combatant = payload["combatants"][hero_id]
    assert combatant["current_hp"] == 1
    assert combatant["conscious"] is True
    assert combatant["death_save_successes"] == 0
    assert combatant["death_save_failures"] == 0

    with get_conn() as conn:
        row = conn.execute(
            "SELECT current_hp FROM character_states WHERE entity_id = ? AND campaign_id = 1",
            (character_id,),
        ).fetchone()
    assert row["current_hp"] == 1


def test_automatic_natural_one_adds_two_death_save_failures(client, monkeypatch):
    _patch_death_save_roll(monkeypatch, 1)
    _character_id, hero_id, _goblin_id = _create_downed_character_encounter(
        client, "automatic-death-save-natural-one"
    )
    response = client.post(
        "/encounters/automatic-death-save-natural-one/advance",
        json={"expected_round": 1, "expected_turn_index": 0},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["turn_start_death_save"]["selected"] == 1
    assert payload["combatants"][hero_id]["death_save_failures"] == 2
