# ruff: noqa: I001
"""Character-aware ability checks for D&D 5e (2014)."""

from models.character_state import CharacterState
from rules_engine.dnd5e_2014.checks import (
    CheckResult,
    ability_check,
    saving_throw,
)
from rules_engine.dnd5e_2014.core.abilities import Ability
from rules_engine.dnd5e_2014.core.dice import DiceRoller
from rules_engine.dnd5e_2014.core.skills import Skill, ability_for_skill


ABILITY_FIELDS: dict[Ability, str] = {
    Ability.STRENGTH: "strength",
    Ability.DEXTERITY: "dexterity",
    Ability.CONSTITUTION: "constitution",
    Ability.INTELLIGENCE: "intelligence",
    Ability.WISDOM: "wisdom",
    Ability.CHARISMA: "charisma",
}


def ability_check_for_character(
    *,
    character: CharacterState,
    roller: DiceRoller,
    skill: Skill,
    dc: int,
    advantage: bool = False,
    disadvantage: bool = False,
    situational_modifier: int = 0,
    ability_override: Ability | None = None,
) -> CheckResult:
    """Resolve a skill check from a character's actual ability/proficiency data.

    The DM may request a non-standard governing ability (for example,
    Strength (Intimidation)); this changes the ability only, not proficiency.
    """
    if not isinstance(character, CharacterState):
        raise TypeError("character must be a CharacterState")
    if not isinstance(skill, Skill):
        raise TypeError("skill must be a Skill")
    if ability_override is not None and not isinstance(ability_override, Ability):
        raise TypeError("ability_override must be an Ability or None")

    ability = ability_override or ability_for_skill(skill)
    ability_score = getattr(character, ABILITY_FIELDS[ability])
    proficient = skill in character.skill_proficiencies
    expertise = skill in character.skill_expertise

    return ability_check(
        roller=roller,
        ability=ability,
        ability_score=ability_score,
        dc=dc,
        level=character.level,
        proficient=proficient,
        expertise=expertise,
        advantage=advantage,
        disadvantage=disadvantage,
        situational_modifier=situational_modifier,
    )


def saving_throw_for_character(
    *,
    character: CharacterState,
    roller: DiceRoller,
    ability: Ability,
    dc: int,
    advantage: bool = False,
    disadvantage: bool = False,
    situational_modifier: int = 0,
) -> CheckResult:
    """Resolve a saving throw from a character's saving-throw proficiencies."""
    if not isinstance(character, CharacterState):
        raise TypeError("character must be a CharacterState")
    if not isinstance(ability, Ability):
        raise TypeError("ability must be an Ability")

    return saving_throw(
        roller=roller,
        ability=ability,
        ability_score=getattr(character, ABILITY_FIELDS[ability]),
        dc=dc,
        level=character.level,
        proficient=ability in character.saving_throw_proficiencies,
        advantage=advantage,
        disadvantage=disadvantage,
        situational_modifier=situational_modifier,
    )


def raw_ability_check_for_character(
    *,
    character: CharacterState,
    roller: DiceRoller,
    ability: Ability,
    dc: int,
    advantage: bool = False,
    disadvantage: bool = False,
    situational_modifier: int = 0,
) -> CheckResult:
    """Resolve an unskilled ability check using the character's ability score."""
    if not isinstance(character, CharacterState):
        raise TypeError("character must be a CharacterState")
    if not isinstance(ability, Ability):
        raise TypeError("ability must be an Ability")

    return ability_check(
        roller=roller,
        ability=ability,
        ability_score=getattr(character, ABILITY_FIELDS[ability]),
        dc=dc,
        level=character.level,
        proficient=False,
        advantage=advantage,
        disadvantage=disadvantage,
        situational_modifier=situational_modifier,
    )
