from scripts.bootstrap_demo import build_demo_payloads


def test_demo_payloads_create_a_level_one_fighter_campaign():
    payloads = build_demo_payloads(
        "Test campaign",
        "Test hero",
        "Classic fantasy",
    )

    assert payloads["campaign"]["name"] == "Test campaign"
    assert payloads["campaign"]["system"] == "D&D 5e 2014"
    assert payloads["session"]["number"] == 1
    assert payloads["character"]["name"] == "Test hero"
    assert payloads["character"]["class_name"] == "Fighter"
    assert payloads["character"]["level"] == 1
    assert payloads["character"]["current_hp"] == payloads["character"]["max_hp"]
    assert payloads["character"]["skill_expertise"] if "skill_expertise" in payloads["character"] else True


def test_demo_character_proficiencies_are_valid_and_unique():
    character = build_demo_payloads("Test", "Hero", "")["character"]

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
