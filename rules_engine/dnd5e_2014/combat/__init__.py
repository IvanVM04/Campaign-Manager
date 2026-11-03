"""Deterministic D&D 5e (2014) combat primitives."""

from rules_engine.dnd5e_2014.combat.attack import AttackResult, resolve_attack
from rules_engine.dnd5e_2014.combat.conditions import Condition, ConditionSet, attack_roll_advantage_state
from rules_engine.dnd5e_2014.combat.damage import DamageType, apply_damage_modifiers
from rules_engine.dnd5e_2014.combat.initiative import InitiativeResult, roll_initiative

__all__ = [
    "AttackResult",
    "Condition",
    "ConditionSet",
    "DamageType",
    "InitiativeResult",
    "apply_damage_modifiers",
    "attack_roll_advantage_state",
    "resolve_attack",
    "roll_initiative",
]
