from collections import deque

import pytest

from rules_engine.dnd5e_2014.core.dice import DiceRoller, RollMode


class SequenceRandom:
    def __init__(self, values):
        self.values = deque(values)

    def randint(self, a, b):
        value = self.values.popleft()
        assert a <= value <= b
        return value


def test_roll_returns_faces_and_total_with_modifier():
    result = DiceRoller(SequenceRandom([3, 5, 2])).roll(
        3,
        6,
        modifier=4,
    )

    assert result.rolls == (3, 5, 2)
    assert result.total == 14
    assert result.modifier == 4


def test_roll_d20_normal_uses_one_die():
    result = DiceRoller(SequenceRandom([14])).roll_d20(modifier=3)

    assert result.rolls == (14,)
    assert result.selected == 14
    assert result.total == 17
    assert result.mode is RollMode.NORMAL


def test_advantage_uses_higher_of_two_d20s():
    result = DiceRoller(SequenceRandom([4, 18])).roll_d20(advantage=True)

    assert result.rolls == (4, 18)
    assert result.selected == 18
    assert result.mode is RollMode.ADVANTAGE


def test_disadvantage_uses_lower_of_two_d20s():
    result = DiceRoller(SequenceRandom([17, 6])).roll_d20(disadvantage=True)

    assert result.rolls == (17, 6)
    assert result.selected == 6
    assert result.mode is RollMode.DISADVANTAGE


def test_advantage_and_disadvantage_cancel_to_one_die():
    result = DiceRoller(SequenceRandom([11])).roll_d20(
        advantage=True,
        disadvantage=True,
    )

    assert result.rolls == (11,)
    assert result.selected == 11
    assert result.mode is RollMode.NORMAL


@pytest.mark.parametrize(
    ("count", "sides"),
    [(0, 6), (-1, 6), (1, 1), (1.5, 6), (True, 6)],
)
def test_invalid_dice_parameters_are_rejected(count, sides):
    with pytest.raises((TypeError, ValueError)):
        DiceRoller(SequenceRandom([])).roll(count, sides)



def test_manual_d20_result_is_used_without_calling_random_source():
    result = DiceRoller(SequenceRandom([])).roll_d20(
        modifier=4,
        manual_rolls=(13,),
    )

    assert result.rolls == (13,)
    assert result.selected == 13
    assert result.total == 17


def test_manual_advantage_requires_two_valid_d20_results():
    result = DiceRoller(SequenceRandom([])).roll_d20(
        advantage=True,
        manual_rolls=(3, 19),
    )

    assert result.rolls == (3, 19)
    assert result.selected == 19
    assert result.total == 19


@pytest.mark.parametrize(
    "manual_rolls",
    [(), (1, 2), (0,), (21,), (True,), ("12",)],
)
def test_invalid_manual_d20_results_are_rejected(manual_rolls):
    with pytest.raises((TypeError, ValueError)):
        DiceRoller(SequenceRandom([])).roll_d20(
            manual_rolls=manual_rolls,
        )


def test_manual_d20_result_count_respects_advantage_and_disadvantage_cancellation():
    with pytest.raises(ValueError):
        DiceRoller(SequenceRandom([])).roll_d20(
            advantage=True,
            disadvantage=True,
            manual_rolls=(12, 18),
        )
