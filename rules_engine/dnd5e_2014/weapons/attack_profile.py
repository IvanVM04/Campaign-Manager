"""Server-derived weapon and natural-attack profiles for D&D 5e (2014)."""

import re
from dataclasses import dataclass

from rules_engine.dnd5e_2014.character import CharacterRulesInput
from rules_engine.dnd5e_2014.core.abilities import ability_modifier
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


@dataclass(frozen=True)
class NaturalAttackProfile:
    """Derived mechanics for a configured NPC natural attack."""

    attack_ability: str
    attack_bonus: int
    damage_dice: str
    damage_bonus: int
    damage_type: str
    proficient: bool


_NATURAL_DAMAGE_DICE = re.compile(r"^([1-9][0-9]*)d(4|6|8|10|12|20)$")


def derive_natural_attack_profile(
    character: CharacterRulesInput,
    *,
    attack_ability: str,
    damage_dice: str,
    damage_type: str,
    proficient: bool,
) -> NaturalAttackProfile:
    """Derive NPC natural-attack bonuses through the deterministic rules layer."""
    if attack_ability not in ("strength", "dexterity"):
        raise ValueError("natural attacks use Strength or Dexterity")
    if not isinstance(proficient, bool):
        raise TypeError("natural attack proficiency must be a boolean")
    if (
        not isinstance(damage_dice, str)
        or _NATURAL_DAMAGE_DICE.fullmatch(damage_dice) is None
    ):
        raise ValueError("natural attack damage dice are not supported")
    if not isinstance(damage_type, str) or not damage_type.strip():
        raise ValueError("natural attack damage type must be a non-empty string")

    modifier = ability_modifier(getattr(character, attack_ability))
    proficiency_bonus = character.proficiency_bonus if proficient else 0
    return NaturalAttackProfile(
        attack_ability=attack_ability,
        attack_bonus=modifier + proficiency_bonus,
        damage_dice=damage_dice,
        damage_bonus=modifier,
        damage_type=damage_type,
        proficient=proficient,
    )


def derive_attack_profile(
    character: CharacterRulesInput,
    weapon: WeaponDefinition,
    *,
    versatile_two_handed: bool = False,
    finesse_ability: str | None = None,
) -> AttackProfile:
    """Derive numeric inputs from trusted character and weapon domain state.

    Finesse attackers may choose Strength or Dexterity; other weapon types
    constrain the ability according to the 2014 rules.
    """
    if not isinstance(weapon, WeaponDefinition):
        raise TypeError("weapon must be a WeaponDefinition")
    if not isinstance(versatile_two_handed, bool):
        raise TypeError("versatile_two_handed must be a boolean")
    if weapon.damage_dice == "0":
        raise ValueError("weapon does not resolve through the ordinary damage-roll profile")

    finesse = WeaponProperty.FINESSE in weapon.properties
    if finesse:
        ability = finesse_ability or ("dexterity" if character.dexterity > character.strength else "strength")
        if ability not in ("strength", "dexterity"):
            raise ValueError("finesse weapons allow Strength or Dexterity")
    elif weapon.is_ranged:
        if finesse_ability not in (None, "dexterity"):
            raise ValueError("ranged weapon attacks use Dexterity")
        ability = "dexterity"
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

    if versatile_two_handed:
        dice = weapon.versatile_damage_dice
        if dice is None:
            raise ValueError("weapon does not have the versatile property")
    else:
        dice = weapon.damage_dice

    return AttackProfile(
        weapon_key=weapon.key, attack_ability=ability, attack_bonus=bonus,
        damage_dice=dice, damage_bonus=modifier, damage_type=weapon.damage_type,
        proficient=proficient, properties=weapon.properties,
    )
