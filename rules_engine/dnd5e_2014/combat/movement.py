"""Grid movement and opportunity-attack rules for D&D 5e (2014).

This module is deliberately pure: callers own encounter state, persistence,
visibility, and reaction consumption. Distances use the optional 5-foot grid
rule where every diagonal square costs 5 feet.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from rules_engine.dnd5e_2014.combat.conditions import ConditionSet

FEET_PER_SQUARE = 5


@dataclass(frozen=True)
class GridPosition:
    """A combatant's integer coordinate on a 5-foot square grid."""

    x: int
    y: int

    def __post_init__(self) -> None:
        for value, name in ((self.x, "x"), (self.y, "y")):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")


def grid_distance_feet(first: GridPosition, second: GridPosition) -> int:
    """Return 5e grid distance in feet (diagonals cost 5 feet)."""
    if not isinstance(first, GridPosition) or not isinstance(second, GridPosition):
        raise TypeError("positions must be GridPosition values")
    return max(abs(first.x - second.x), abs(first.y - second.y)) * FEET_PER_SQUARE


def movement_speed_feet(base_speed: int, conditions: ConditionSet) -> int:
    """Apply the 2014 condition/exhaustion movement restrictions to base speed."""
    if isinstance(base_speed, bool) or not isinstance(base_speed, int):
        raise TypeError("base_speed must be an integer")
    if base_speed < 0 or base_speed % FEET_PER_SQUARE:
        raise ValueError("base_speed must be a non-negative multiple of 5 feet")
    if not isinstance(conditions, ConditionSet):
        raise TypeError("conditions must be a ConditionSet")
    if conditions.speed_is_zero:
        return 0
    if conditions.speed_halved:
        return (base_speed // 2 // FEET_PER_SQUARE) * FEET_PER_SQUARE
    return base_speed


def movement_path_cost_feet(path: tuple[GridPosition, ...]) -> int:
    """Return cost for a path of adjacent 5-foot grid squares.

    The path includes the starting square. Each subsequent square must be
    adjacent (including diagonally); teleportation is not movement through
    this function and must be represented by a separate game effect.
    """
    if not isinstance(path, tuple) or not path:
        raise ValueError("path must be a non-empty tuple of GridPosition values")
    if any(not isinstance(position, GridPosition) for position in path):
        raise TypeError("path must contain GridPosition values")
    cost = 0
    for previous, current in pairwise(path):
        dx = abs(current.x - previous.x)
        dy = abs(current.y - previous.y)
        if max(dx, dy) != 1:
            raise ValueError("each movement step must enter one adjacent square")
        cost += FEET_PER_SQUARE
    return cost


def can_move_along_path(
    *,
    path: tuple[GridPosition, ...],
    base_speed: int,
    conditions: ConditionSet,
) -> bool:
    """Whether a combatant has enough movement for the supplied path."""
    return movement_path_cost_feet(path) <= movement_speed_feet(base_speed, conditions)


def provokes_opportunity_attack(
    *,
    attacker_position: GridPosition,
    mover_previous_position: GridPosition,
    mover_next_position: GridPosition,
    reach_feet: int = 5,
    voluntary: bool = True,
    disengaging: bool = False,
    attacker_incapacitated: bool = False,
    attacker_dead: bool = False,
    attacker_reaction_available: bool = True,
) -> bool:
    """Whether one movement step provokes from one potential attacker.

    An opportunity attack is triggered when a creature the attacker can see
    moves out of the attacker's reach. Forced movement and teleportation do
    not trigger it; Disengage prevents it. The caller must establish visibility
    and consume the reaction only after the player/NPC chooses to attack.
    """
    for value, name in (
        (voluntary, "voluntary"),
        (disengaging, "disengaging"),
        (attacker_incapacitated, "attacker_incapacitated"),
        (attacker_dead, "attacker_dead"),
        (attacker_reaction_available, "attacker_reaction_available"),
    ):
        if not isinstance(value, bool):
            raise TypeError(f"{name} must be a boolean")
    if isinstance(reach_feet, bool) or not isinstance(reach_feet, int):
        raise TypeError("reach_feet must be an integer")
    if reach_feet < 0 or reach_feet % FEET_PER_SQUARE:
        raise ValueError("reach_feet must be a non-negative multiple of 5 feet")
    for position in (attacker_position, mover_previous_position, mover_next_position):
        if not isinstance(position, GridPosition):
            raise TypeError("positions must be GridPosition values")
    if (
        not voluntary
        or disengaging
        or attacker_incapacitated
        or attacker_dead
        or not attacker_reaction_available
    ):
        return False
    was_within_reach = grid_distance_feet(attacker_position, mover_previous_position) <= reach_feet
    remains_within_reach = grid_distance_feet(attacker_position, mover_next_position) <= reach_feet
    return was_within_reach and not remains_within_reach
