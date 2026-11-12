from __future__ import annotations

import pytest

from rules_engine.dnd5e_2014.combat.hit_points import apply_combatant_damage


def test_damage_above_zero_hit_points_preserves_death_track():
    result = apply_combatant_damage(
        current_hp=12,
        max_hp=20,
        damage=5,
        death_save_successes=1,
        death_save_failures=2,
    )

    assert result.current_hp == 7
    assert result.death_save_successes == 1
    assert result.death_save_failures == 2
    assert not result.stable
    assert not result.dead
    assert result.conscious


def test_damage_reducing_hit_points_to_zero_starts_an_unconscious_state():
    result = apply_combatant_damage(
        current_hp=5,
        max_hp=10,
        damage=5,
        death_save_successes=2,
        death_save_failures=1,
    )

    assert result.current_hp == 0
    assert result.death_save_successes == 0
    assert result.death_save_failures == 0
    assert not result.stable
    assert not result.dead
    assert not result.conscious


def test_massive_damage_kills_when_excess_damage_reaches_maximum_hit_points():
    result = apply_combatant_damage(
        current_hp=5,
        max_hp=10,
        damage=15,
    )

    assert result.current_hp == 0
    assert result.death_save_failures == 3
    assert result.dead
    assert not result.stable
    assert not result.conscious


def test_non_massive_damage_does_not_kill_outright():
    result = apply_combatant_damage(
        current_hp=5,
        max_hp=10,
        damage=14,
    )

    assert result.current_hp == 0
    assert result.death_save_successes == 0
    assert result.death_save_failures == 0
    assert not result.dead
    assert not result.stable
    assert not result.conscious


def test_damage_to_a_downed_combatant_adds_one_failure():
    result = apply_combatant_damage(
        current_hp=0,
        max_hp=10,
        damage=3,
        death_save_successes=1,
        death_save_failures=1,
        conscious=False,
    )

    assert result.death_save_successes == 1
    assert result.death_save_failures == 2
    assert not result.dead


def test_critical_damage_to_a_downed_combatant_adds_two_failures():
    result = apply_combatant_damage(
        current_hp=0,
        max_hp=10,
        damage=3,
        death_save_successes=1,
        death_save_failures=1,
        conscious=False,
        critical_hit=True,
    )

    assert result.death_save_failures == 3
    assert result.dead
    assert result.current_hp == 0


def test_damage_to_a_stable_combatant_resets_successes_and_makes_them_unstable():
    result = apply_combatant_damage(
        current_hp=0,
        max_hp=10,
        damage=1,
        death_save_successes=3,
        conscious=False,
        stable=True,
    )

    assert result.death_save_successes == 0
    assert result.death_save_failures == 1
    assert not result.stable
    assert not result.dead


def test_third_failure_from_damage_kills_a_downed_combatant():
    result = apply_combatant_damage(
        current_hp=0,
        max_hp=10,
        damage=1,
        death_save_failures=2,
        conscious=False,
    )

    assert result.death_save_failures == 3
    assert result.dead
    assert result.current_hp == 0


def test_zero_damage_preserves_all_hit_point_state():
    result = apply_combatant_damage(
        current_hp=0,
        max_hp=10,
        damage=0,
        death_save_successes=2,
        death_save_failures=1,
        conscious=False,
    )

    assert result.current_hp == 0
    assert result.death_save_successes == 2
    assert result.death_save_failures == 1
    assert not result.stable
    assert not result.dead
    assert not result.conscious


@pytest.mark.parametrize(
    "kwargs",
    [
        {"current_hp": True, "max_hp": 10, "damage": 1},
        {"current_hp": 1, "max_hp": 0, "damage": 1},
        {"current_hp": 1, "max_hp": 10, "damage": -1},
        {"current_hp": 1, "max_hp": 10, "damage": 1, "critical_hit": 1},
        {"current_hp": 0, "max_hp": 10, "damage": 1, "stable": True},
        {"current_hp": 0, "max_hp": 10, "damage": 1, "dead": True, "conscious": False},
    ],
)
def test_invalid_damage_states_are_rejected(kwargs):
    with pytest.raises((TypeError, ValueError)):
        apply_combatant_damage(**kwargs)
