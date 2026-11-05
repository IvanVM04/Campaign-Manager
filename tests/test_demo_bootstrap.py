from scripts.bootstrap_demo import (
    DEMO_CAMPAIGN_SUMMARY,
    DEMO_SESSION_NOTES,
    DEMO_SESSION_SUMMARY,
    DEMO_WORLD_ENTITIES,
    build_demo_payloads,
)


def test_demo_payloads_create_a_level_one_fighter_campaign():
    payloads = build_demo_payloads(
        "Test campaign",
        "Test hero",
        "Classic fantasy",
    )

    assert payloads["campaign"]["name"] == "Test campaign"
    assert payloads["campaign"]["system"] == "D&D 5e 2014"
    assert payloads["campaign"]["tone"] == "Classic fantasy"
    assert payloads["session"]["number"] == 1
    assert payloads["character"]["name"] == "Test hero"
    assert payloads["character"]["class_name"] == "Fighter"
    assert payloads["character"]["level"] == 1
    assert payloads["character"]["current_hp"] == 12
    assert payloads["character"]["max_hp"] == 12


def test_demo_character_proficiencies_are_valid_and_unique():
    character = build_demo_payloads("Test", "Hero", "")["character"]

    assert character["skill_proficiencies"] == ["athletics", "perception"]
    assert character["saving_throw_proficiencies"] == [
        "strength",
        "constitution",
    ]
    assert len(character["skill_proficiencies"]) == len(
        set(character["skill_proficiencies"])
    )
    assert len(character["saving_throw_proficiencies"]) == len(
        set(character["saving_throw_proficiencies"])
    )
    assert set(character["armor_proficiencies"]) == {
        "light",
        "medium",
        "heavy",
        "shields",
    }


def test_demo_campaign_contains_a_playable_open_ended_adventure():
    payloads = build_demo_payloads("Test", "Hero", "")

    assert payloads["campaign"]["summary"] == DEMO_CAMPAIGN_SUMMARY
    assert "Mara" in DEMO_CAMPAIGN_SUMMARY
    assert "Bram" in DEMO_CAMPAIGN_SUMMARY
    assert "Nilo" in DEMO_CAMPAIGN_SUMMARY
    assert "No fuerces combate" in DEMO_CAMPAIGN_SUMMARY
    assert "No reveles la verdad oculta" in DEMO_CAMPAIGN_SUMMARY

    session = payloads["session"]
    assert session["title"] == "Las campanas de Puenteviejo"
    assert session["summary"] == DEMO_SESSION_SUMMARY
    assert session["notes"] == DEMO_SESSION_NOTES
    assert "pistas" in DEMO_SESSION_NOTES.lower()


def test_demo_payloads_seed_npcs_and_locations():
    world = build_demo_payloads("Test", "Hero", "")["world"]

    assert world["entities"] == DEMO_WORLD_ENTITIES
    assert {entity["name"] for entity in world["entities"]} >= {
        "Mara",
        "Bram",
        "Nilo",
        "Posada del Camino",
        "Puenteviejo",
        "Viejo puente",
    }
    assert all(entity["entity_type"] in {"npc", "location"} for entity in world["entities"])
