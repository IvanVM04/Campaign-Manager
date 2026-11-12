import pytest

from models.character_state import CharacterState
from rules_engine.dnd5e_2014.weapons.attack_profile import (
    derive_attack_profile,
    derive_natural_attack_profile,
)
from rules_engine.dnd5e_2014.weapons.catalog import get_weapon


def test_finesse_allows_player_to_choose_strength_or_dexterity():
    character = CharacterState(entity_id=1, strength=18, dexterity=12)
    strength_profile = derive_attack_profile(
        character, get_weapon("rapier"), finesse_ability="strength"
    )
    dexterity_profile = derive_attack_profile(
        character, get_weapon("rapier"), finesse_ability="dexterity"
    )
    assert strength_profile.attack_ability == "strength"
    assert strength_profile.attack_bonus == 4
    assert dexterity_profile.attack_ability == "dexterity"
    assert dexterity_profile.attack_bonus == 1
    with pytest.raises(ValueError):
        derive_attack_profile(character, get_weapon("longsword"), finesse_ability="dexterity")


def test_finesse_property_also_applies_to_ranged_dart():
    character = CharacterState(entity_id=1, strength=18, dexterity=10)
    profile = derive_attack_profile(
        character, get_weapon("dart"), finesse_ability="strength"
    )
    assert profile.attack_ability == "strength"
    assert profile.attack_bonus == 4


def test_natural_attack_profile_derives_strength_bonus_and_proficiency():
    character = CharacterState(
        entity_id=1,
        strength=18,
        dexterity=12,
        proficiency_bonus=3,
    )
    profile = derive_natural_attack_profile(
        character,
        attack_ability="strength",
        damage_dice="2d6",
        damage_type="piercing",
        proficient=True,
    )

    assert profile.attack_ability == "strength"
    assert profile.attack_bonus == 7
    assert profile.damage_bonus == 4
    assert profile.damage_dice == "2d6"
    assert profile.damage_type == "piercing"
    assert profile.proficient is True


def test_natural_attack_profile_can_be_unproficient_and_use_dexterity():
    character = CharacterState(
        entity_id=1,
        strength=18,
        dexterity=14,
        proficiency_bonus=4,
    )
    profile = derive_natural_attack_profile(
        character,
        attack_ability="dexterity",
        damage_dice="1d4",
        damage_type="slashing",
        proficient=False,
    )

    assert profile.attack_bonus == 2
    assert profile.damage_bonus == 2
    assert profile.proficient is False


@pytest.mark.parametrize(
    ("overrides", "exception", "message"),
    [
        ({"attack_ability": "wisdom"}, ValueError, "Strength or Dexterity"),
        ({"proficient": 1}, TypeError, "proficiency must be a boolean"),
        ({"damage_dice": "1d3"}, ValueError, "damage dice are not supported"),
        ({"damage_dice": "0d6"}, ValueError, "damage dice are not supported"),
        ({"damage_type": ""}, ValueError, "damage type must be a non-empty string"),
    ],
)
def test_natural_attack_profile_rejects_unsupported_inputs(
    overrides,
    exception,
    message,
):
    values = {
        "attack_ability": "strength",
        "damage_dice": "1d6",
        "damage_type": "piercing",
        "proficient": True,
    }
    values.update(overrides)

    with pytest.raises(exception, match=message):
        derive_natural_attack_profile(
            CharacterState(entity_id=1),
            **values,
        )
