import pytest

from rules_engine.dnd5e_2014.combat.conditions import Condition, ConditionSet
from rules_engine.dnd5e_2014.combat.movement import (
    GridPosition,
    can_move_along_path,
    grid_distance_feet,
    movement_path_cost_feet,
    movement_speed_feet,
    provokes_opportunity_attack,
)


def test_grid_distance_counts_diagonal_as_five_feet():
    assert grid_distance_feet(GridPosition(0, 0), GridPosition(3, 3)) == 15
    assert grid_distance_feet(GridPosition(0, 0), GridPosition(3, 1)) == 15


def test_movement_path_cost_requires_adjacent_steps():
    assert movement_path_cost_feet(
        (GridPosition(0, 0), GridPosition(1, 0), GridPosition(2, 1))
    ) == 10
    with pytest.raises(ValueError, match="adjacent"):
        movement_path_cost_feet((GridPosition(0, 0), GridPosition(2, 0)))


def test_speed_respects_zero_speed_conditions_and_exhaustion():
    assert movement_speed_feet(30, ConditionSet()) == 30
    assert movement_speed_feet(30, ConditionSet(exhaustion_level=2)) == 15
    assert movement_speed_feet(
        30, ConditionSet(frozenset({Condition.GRAPPLED}))
    ) == 0
    assert movement_speed_feet(30, ConditionSet(exhaustion_level=5)) == 0


def test_movement_budget_checks_path_cost():
    path = (GridPosition(0, 0), GridPosition(1, 0), GridPosition(2, 0))
    assert can_move_along_path(path=path, base_speed=10, conditions=ConditionSet())
    assert not can_move_along_path(path=path, base_speed=5, conditions=ConditionSet())
    assert not can_move_along_path(
        path=path, base_speed=10, conditions=ConditionSet(exhaustion_level=2)
    )


def test_leaving_reach_provokes_opportunity_attack():
    assert provokes_opportunity_attack(
        attacker_position=GridPosition(0, 0),
        mover_previous_position=GridPosition(1, 0),
        mover_next_position=GridPosition(2, 0),
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"voluntary": False},
        {"disengaging": True},
        {"attacker_incapacitated": True},
        {"attacker_dead": True},
        {"attacker_reaction_available": False},
    ],
)
def test_opportunity_attack_is_suppressed_by_exceptions(overrides):
    args = {
        "attacker_position": GridPosition(0, 0),
        "mover_previous_position": GridPosition(1, 0),
        "mover_next_position": GridPosition(2, 0),
    }
    args.update(overrides)
    assert not provokes_opportunity_attack(**args)


def test_moving_within_reach_does_not_provoke():
    assert not provokes_opportunity_attack(
        attacker_position=GridPosition(0, 0),
        mover_previous_position=GridPosition(1, 0),
        mover_next_position=GridPosition(1, 1),
    )


def test_reach_can_be_longer_than_five_feet():
    assert provokes_opportunity_attack(
        attacker_position=GridPosition(0, 0),
        mover_previous_position=GridPosition(2, 0),
        mover_next_position=GridPosition(3, 0),
        reach_feet=10,
    )


def test_grid_positions_and_speeds_reject_invalid_values():
    with pytest.raises(TypeError):
        GridPosition(True, 0)
    with pytest.raises(ValueError):
        movement_speed_feet(31, ConditionSet())
    with pytest.raises(TypeError):
        movement_speed_feet(30, object())
