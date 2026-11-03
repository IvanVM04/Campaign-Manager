"""Server-derived attack profiles from character state and equipped weapons."""
from dataclasses import dataclass

from models.character_state import CharacterState
from rules_engine.dnd5e_2014.weapons.catalog import WeaponDefinition, WeaponProperty


@dataclass(frozen=True)
class AttackProfile:
    weapon_key: str
    attack_ability: str
    attack_bonus: int
    damage_dice: str
    damage_bonus: int
    damage_type: str
    proficient: bool
    properties: frozenset[WeaponProperty]


def derive_attack_profile(
    character: CharacterState,
    weapon: WeaponDefinition,
    *,
    versatile_two_handed: bool = False,
    finesse_ability: str | None = None,
) -> AttackProfile:
    """Derive numeric inputs from trusted character and weapon domain state.

    Finesse attackers may choose Strength or Dexterity; other weapon types
    constrain the ability according to the 2014 rules.
    """
    if not isinstance(character, CharacterState):
        raise TypeError("character must be a CharacterState")
    if not isinstance(weapon, WeaponDefinition):
        raise TypeError("weapon must be a WeaponDefinition")
    if not isinstance(versatile_two_handed, bool):
        raise TypeError("versatile_two_handed must be a boolean")
    if versatile_two_handed and weapon.versatile_damage_dice is None:
        raise ValueError("weapon does not have the versatile property")
    if weapon.damage_dice == "0":
        raise ValueError("weapon does not resolve through the ordinary damage-roll profile")

    finesse = WeaponProperty.FINESSE in weapon.properties
    if weapon.is_ranged:
        if finesse_ability not in (None, "dexterity"):
            raise ValueError("ranged weapon attacks use Dexterity")
        ability = "dexterity"
    elif finesse:
        ability = finesse_ability or "strength"
        if ability not in ("strength", "dexterity"):
            raise ValueError("finesse weapons allow Strength or Dexterity")
    else:
        if finesse_ability not in (None, "strength"):
            raise ValueError("this weapon attack uses Strength")
        ability = "strength"

    modifier = (getattr(character, ability) - 10) // 2
    proficient = (
        weapon.category.value in character.weapon_proficiencies
        or weapon.key in character.weapon_proficiencies
    )
    bonus = modifier + (character.proficiency_bonus if proficient else 0)
    dice = weapon.versatile_damage_dice if versatile_two_handed else weapon.damage_dice
    return AttackProfile(
        weapon_key=weapon.key, attack_ability=ability, attack_bonus=bonus,
        damage_dice=dice, damage_bonus=modifier, damage_type=weapon.damage_type,
        proficient=proficient, properties=weapon.properties,
    )
