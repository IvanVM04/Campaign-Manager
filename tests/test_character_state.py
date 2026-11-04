from models.character_state import CharacterState


def test_character_state_has_dnd_defaults():
    character = CharacterState(entity_id=1)

    assert character.entity_id == 1
    assert character.level == 1
    assert character.class_name is None

    assert character.current_hp == 0
    assert character.max_hp == 0
    assert character.armor_class == 10

    assert character.strength == 10
    assert character.dexterity == 10
    assert character.constitution == 10
    assert character.intelligence == 10
    assert character.wisdom == 10
    assert character.charisma == 10

    assert character.proficiency_bonus == 2
    assert character.metadata == {}


def test_character_state_stores_mechanical_state():
    character = CharacterState(
        entity_id=7,
        level=3,
        class_name="Fighter",
        current_hp=18,
        max_hp=24,
        armor_class=16,
        strength=16,
        dexterity=14,
        constitution=15,
        intelligence=10,
        wisdom=12,
        charisma=8,
        proficiency_bonus=2,
    )

    assert character.entity_id == 7
    assert character.level == 3
    assert character.class_name == "Fighter"

    assert character.current_hp == 18
    assert character.max_hp == 24
    assert character.armor_class == 16

    assert character.strength == 16
    assert character.dexterity == 14
    assert character.constitution == 15
    assert character.intelligence == 10
    assert character.wisdom == 12
    assert character.charisma == 8

    assert character.proficiency_bonus == 2


def test_character_state_metadata_is_independent():
    first = CharacterState(entity_id=1)
    second = CharacterState(entity_id=2)

    first.metadata["origin"] = "Vorder's Hold"

    assert first.metadata == {"origin": "Vorder's Hold"}
    assert second.metadata == {}


def test_character_state_can_represent_player_character():
    character = CharacterState(
        entity_id=1,
        level=1,
        class_name="Rogue",
        current_hp=10,
        max_hp=10,
        armor_class=14,
        strength=10,
        dexterity=16,
        constitution=12,
        intelligence=13,
        wisdom=11,
        charisma=14,
        proficiency_bonus=2,
    )

    assert character.level == 1
    assert character.class_name == "Rogue"
    assert character.dexterity == 16
    assert character.current_hp == character.max_hp


def test_character_state_validates_armor_proficiency_categories():
    import pytest

    character = CharacterState(entity_id=9, armor_proficiencies={"light", "shields"})
    assert character.armor_proficiencies == frozenset({"light", "shields"})
    with pytest.raises(ValueError, match="armor proficiencies"):
        CharacterState(entity_id=10, armor_proficiencies={"plate"})
