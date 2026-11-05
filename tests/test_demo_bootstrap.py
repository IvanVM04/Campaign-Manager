from scripts.bootstrap_demo import build_demo_payloads


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
