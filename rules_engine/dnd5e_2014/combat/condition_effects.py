"""Condition-derived combat restrictions for D&D 5e (2014)."""

from __future__ import annotations

from dataclasses import dataclass

from rules_engine.dnd5e_2014.combat.conditions import Condition, ConditionSet
from rules_engine.dnd5e_2014.core.abilities import Ability


@dataclass(frozen=True)
class ConditionEffects:
    speed_is_zero: bool
    cannot_take_actions: bool
    cannot_take_reactions: bool
    auto_fail_strength_saves: bool
    auto_fail_dexterity_saves: bool
    melee_attacks_against_have_advantage: bool
    attacks_against_have_advantage_within_5_feet: bool
    attacks_have_disadvantage: bool
    ability_checks_have_disadvantage: bool
    saving_throws_have_disadvantage: bool
    speed_halved: bool
    hit_point_maximum_halved: bool
    dies_at_exhaustion_six: bool


def derive_condition_effects(conditions: ConditionSet) -> ConditionEffects:
    if not isinstance(conditions, ConditionSet):
        raise TypeError("conditions must be a ConditionSet")
    return ConditionEffects(
        speed_is_zero=conditions.speed_is_zero,
        cannot_take_actions=conditions.is_incapacitated,
        cannot_take_reactions=conditions.is_incapacitated,
        auto_fail_strength_saves=conditions.automatically_fails_strength_and_dexterity_saves,
        auto_fail_dexterity_saves=conditions.automatically_fails_strength_and_dexterity_saves,
        melee_attacks_against_have_advantage=conditions.attacks_against_have_advantage,
        attacks_against_have_advantage_within_5_feet=conditions.attacks_against_have_advantage_within_5_feet,
        attacks_have_disadvantage=conditions.attacks_have_disadvantage,
        ability_checks_have_disadvantage=conditions.ability_checks_have_disadvantage,
        saving_throws_have_disadvantage=conditions.saving_throws_have_disadvantage,
        speed_halved=conditions.speed_halved,
        hit_point_maximum_halved=conditions.hit_point_maximum_halved,
        dies_at_exhaustion_six=conditions.dies_at_exhaustion_six,
    )


def saving_throw_auto_fails(conditions: ConditionSet, ability: Ability) -> bool:
    if not isinstance(conditions, ConditionSet):
        raise TypeError("conditions must be a ConditionSet")
    if not isinstance(ability, Ability):
        raise TypeError("ability must be an Ability")
    return (
        ability in {Ability.STRENGTH, Ability.DEXTERITY}
        and conditions.automatically_fails_strength_and_dexterity_saves
    )


def condition_imposes_disadvantage_on_check(conditions: ConditionSet) -> bool:
    if not isinstance(conditions, ConditionSet):
        raise TypeError("conditions must be a ConditionSet")
    return conditions.ability_checks_have_disadvantage


def is_charmed_by_target(conditions: ConditionSet) -> bool:
    """Whether the Charmed condition is present; target identity is external."""
    return conditions.has(Condition.CHARMED)
