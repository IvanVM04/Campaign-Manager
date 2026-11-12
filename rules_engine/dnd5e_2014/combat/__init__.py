"""Deterministic D&D 5e (2014) combat primitives."""

from rules_engine.dnd5e_2014.combat.attack import AttackResult, resolve_attack
from rules_engine.dnd5e_2014.combat.conditions import (
    Condition,
    ConditionSet,
    attack_roll_advantage_state,
)
from rules_engine.dnd5e_2014.combat.damage import DamageType, apply_damage_modifiers
from rules_engine.dnd5e_2014.combat.death_saves import (
    DeathSaveResult,
    resolve_death_saving_throw,
)
from rules_engine.dnd5e_2014.combat.hit_points import (
    HitPointDamageState,
    apply_combatant_damage,
)
from rules_engine.dnd5e_2014.combat.initiative import InitiativeResult, roll_initiative
from rules_engine.dnd5e_2014.combat.movement import (
    GridPosition,
    can_move_along_path,
    grid_distance_feet,
    movement_path_cost_feet,
    movement_speed_feet,
    provokes_opportunity_attack,
)

__all__ = [
    "AttackResult",
    "Condition",
    "ConditionSet",
    "DamageType",
    "DeathSaveResult",
    "GridPosition",
    "HitPointDamageState",
    "InitiativeResult",
    "apply_combatant_damage",
    "apply_damage_modifiers",
    "attack_roll_advantage_state",
    "can_move_along_path",
    "grid_distance_feet",
    "movement_path_cost_feet",
    "movement_speed_feet",
    "provokes_opportunity_attack",
    "resolve_attack",
    "resolve_death_saving_throw",
    "roll_initiative",
]
