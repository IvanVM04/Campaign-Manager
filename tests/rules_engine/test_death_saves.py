from collections import deque

import pytest

from rules_engine.dnd5e_2014.combat.death_saves import resolve_death_saving_throw
from rules_engine.dnd5e_2014.core.dice import DiceRoller


class SequenceRandom:
    def __init__(self, values):
        self.values = deque(values)

    def randint(self, a, b):
        value = self.values.popleft()
        assert a <= value <= b
        return value


def test_roll_of_ten_or_more_adds_one_success():
    result = resolve_death_saving_throw(
        roller=DiceRoller(SequenceRandom([10])),
    )
    assert (result.successes, result.failures) == (1, 0)
    assert not result.stable
    assert not result.dead
    assert result.regained_hp == 0


def test_roll_below_ten_adds_one_failure():
    result = resolve_death_saving_throw(
        roller=DiceRoller(SequenceRandom([9])),
        successes=1,
    )
    assert (result.successes, result.failures) == (1, 1)


def test_natural_one_adds_two_failures_and_can_be_fatal():
    result = resolve_death_saving_throw(
        roller=DiceRoller(SequenceRandom([1])),
        failures=1,
    )
    assert result.failures == 3
    assert result.dead


def test_natural_twenty_restores_one_hit_point_without_a_save_success():
    result = resolve_death_saving_throw(
        roller=DiceRoller(SequenceRandom([20])),
        successes=2,
        failures=1,
    )
    assert result.successes == 2
    assert result.failures == 1
    assert result.regained_hp == 1
    assert not result.stable
    assert not result.dead


def test_third_success_stabilizes():
    result = resolve_death_saving_throw(
        roller=DiceRoller(SequenceRandom([10])),
        successes=2,
    )
    assert result.successes == 3
    assert result.stable
    assert not result.dead


def test_invalid_or_already_resolved_tracks_are_rejected():
    roller = DiceRoller(SequenceRandom([10]))
    with pytest.raises(ValueError, match="between zero and three"):
        resolve_death_saving_throw(roller=roller, successes=4)
    with pytest.raises(ValueError, match="already resolved"):
        resolve_death_saving_throw(roller=roller, failures=3)
    with pytest.raises(TypeError, match="must be an integer"):
        resolve_death_saving_throw(roller=roller, failures=True)
