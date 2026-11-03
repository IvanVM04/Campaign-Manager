"""Ability checks and saving throws for D&D 5e (2014)."""

from __future__ import annotations

from dataclasses import dataclass

from rules_engine.dnd5e_2014.core.abilities import Ability, ability_modifier
from rules_engine.dnd5e_2014.core.dice import D20Roll, DiceRoller
from rules_engine.dnd5e_2014.core.proficiency import proficiency_bonus_for_level


@dataclass(frozen=True)
class CheckResult:
    """Complete, inspectable result of an ability check or saving throw."""

    kind: str
    ability: Ability
    ability_score: int
    ability_modifier: int
    proficiency_bonus: int
    proficiency_applied: int
    situational_modifier: int
    roll: D20Roll
    dc: int
    success: bool

    @property
    def total(self) -> int:
        return self.roll.total


def _resolve_d20_test(
    *,
    kind: str,
    roller: DiceRoller,
    ability: Ability,
    ability_score: int,
    dc: int,
    level: int,
    proficient: bool,
    expertise: bool,
    advantage: bool,
    disadvantage: bool,
    situational_modifier: int,
) -> CheckResult:
    if not isinstance(roller, DiceRoller):
        raise TypeError("roller must be a DiceRoller")
    if not isinstance(ability, Ability):
        raise TypeError("ability must be an Ability")
    if isinstance(dc, bool) or not isinstance(dc, int):
        raise TypeError("dc must be an integer")
    if not isinstance(proficient, bool):
        raise TypeError("proficient must be a boolean")
    if not isinstance(expertise, bool):
        raise TypeError("expertise must be a boolean")
    if not isinstance(advantage, bool) or not isinstance(disadvantage, bool):
        raise TypeError("advantage and disadvantage must be booleans")
    if expertise and not proficient:
        raise ValueError("expertise requires proficiency")
    if isinstance(situational_modifier, bool) or not isinstance(
        situational_modifier, int
    ):
        raise TypeError("situational_modifier must be an integer")

    score_modifier = ability_modifier(ability_score)
    base_proficiency = proficiency_bonus_for_level(level)
    proficiency = base_proficiency if proficient else 0
    applied_proficiency = proficiency * (2 if expertise else 1)
    total_modifier = (
        score_modifier + applied_proficiency + situational_modifier
    )
    roll = roller.roll_d20(
        modifier=total_modifier,
        advantage=advantage,
        disadvantage=disadvantage,
    )

    return CheckResult(
        kind=kind,
        ability=ability,
        ability_score=ability_score,
        ability_modifier=score_modifier,
        proficiency_bonus=base_proficiency,
        proficiency_applied=applied_proficiency,
        situational_modifier=situational_modifier,
        roll=roll,
        dc=dc,
        success=roll.total >= dc,
    )


def ability_check(
    *,
    roller: DiceRoller,
    ability: Ability,
    ability_score: int,
    dc: int,
    level: int,
    proficient: bool = False,
    expertise: bool = False,
    advantage: bool = False,
    disadvantage: bool = False,
    situational_modifier: int = 0,
) -> CheckResult:
    """Resolve an ability check, optionally applying skill/tool proficiency."""
    return _resolve_d20_test(
        kind="ability_check",
        roller=roller,
        ability=ability,
        ability_score=ability_score,
        dc=dc,
        level=level,
        proficient=proficient,
        expertise=expertise,
        advantage=advantage,
        disadvantage=disadvantage,
        situational_modifier=situational_modifier,
    )


def saving_throw(
    *,
    roller: DiceRoller,
    ability: Ability,
    ability_score: int,
    dc: int,
    level: int,
    proficient: bool = False,
    advantage: bool = False,
    disadvantage: bool = False,
    situational_modifier: int = 0,
) -> CheckResult:
    """Resolve a saving throw; expertise is not applied to saving throws."""
    return _resolve_d20_test(
        kind="saving_throw",
        roller=roller,
        ability=ability,
        ability_score=ability_score,
        dc=dc,
        level=level,
        proficient=proficient,
        expertise=False,
        advantage=advantage,
        disadvantage=disadvantage,
        situational_modifier=situational_modifier,
    )
