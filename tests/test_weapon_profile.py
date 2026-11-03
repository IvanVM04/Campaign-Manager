import pytest

from models.character_state import CharacterState
from rules_engine.dnd5e_2014.weapons.catalog import get_weapon
from rules_engine.dnd5e_2014.weapons.attack_profile import derive_attack_profile


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
