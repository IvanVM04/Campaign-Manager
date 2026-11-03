import pytest

from rules_engine.dnd5e_2014.checks import ability_check, saving_throw
from rules_engine.dnd5e_2014.core.abilities import Ability, ability_modifier
from rules_engine.dnd5e_2014.core.dice import DiceRoller
from rules_engine.dnd5e_2014.core.proficiency import proficiency_bonus_for_level


class SequenceRandom:
    def __init__(self, *values):
        self.values = iter(values)

    def randint(self, a, b):
        value = next(self.values)
        assert a <= value <= b
        return value


@pytest.mark.parametrize(
    ("score", "expected"),
    [(1, -5), (8, -1), (9, -1), (10, 0), (11, 0), (12, 1), (20, 5), (30, 10)],
)
def test_ability_modifier(score, expected):
    assert ability_modifier(score) == expected


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (1, 2),
        (4, 2),
        (5, 3),
        (8, 3),
        (9, 4),
        (12, 4),
        (13, 5),
        (16, 5),
        (17, 6),
        (20, 6),
    ],
)
def test_proficiency_bonus_progression(level, expected):
    assert proficiency_bonus_for_level(level) == expected


def test_proficient_ability_check_adds_ability_and_proficiency_once():
    result = ability_check(
        roller=DiceRoller(SequenceRandom(10)),
        ability=Ability.STRENGTH,
        ability_score=16,
        dc=15,
        level=5,
        proficient=True,
    )

    assert result.ability_modifier == 3
    assert result.proficiency_bonus == 3
    assert result.proficiency_applied == 3
    assert result.total == 16
    assert result.success is True


def test_expertise_doubles_proficiency_on_ability_check():
    result = ability_check(
        roller=DiceRoller(SequenceRandom(10)),
        ability=Ability.DEXTERITY,
        ability_score=14,
        dc=18,
        level=5,
        proficient=True,
        expertise=True,
    )

    assert result.proficiency_applied == 6
    assert result.total == 18
    assert result.success is True


def test_unproficient_saving_throw_does_not_add_proficiency():
    result = saving_throw(
        roller=DiceRoller(SequenceRandom(12)),
        ability=Ability.WISDOM,
        ability_score=8,
        dc=12,
        level=9,
        proficient=False,
    )

    assert result.ability_modifier == -1
    assert result.proficiency_applied == 0
    assert result.total == 11
    assert result.success is False


def test_proficient_saving_throw_adds_proficiency():
    result = saving_throw(
        roller=DiceRoller(SequenceRandom(10)),
        ability=Ability.CONSTITUTION,
        ability_score=14,
        dc=14,
        level=1,
        proficient=True,
    )

    assert result.total == 14
    assert result.success is True


def test_expertise_requires_proficiency():
    with pytest.raises(ValueError, match="expertise requires proficiency"):
        ability_check(
            roller=DiceRoller(SequenceRandom(10)),
            ability=Ability.CHARISMA,
            ability_score=10,
            dc=10,
            level=1,
            expertise=True,
        )


@pytest.mark.parametrize("invalid_level", [0, 21, True, 1.5])
def test_invalid_character_level_is_rejected(invalid_level):
    with pytest.raises((TypeError, ValueError)):
        proficiency_bonus_for_level(invalid_level)
