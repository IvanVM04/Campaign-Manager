from rules_engine.dnd5e_2014.combat.initiative import (
    group_initiative_ties,
    roll_initiative,
)
from rules_engine.dnd5e_2014.core.dice import DiceRoller


class FixedRandom:
    def __init__(self, values):
        self.values = iter(values)

    def randint(self, a, b):
        value = next(self.values)
        assert a <= value <= b
        return value


def test_initiative_is_d20_plus_dexterity_modifier_and_bonus():
    result = roll_initiative(
        combatant_id="hero",
        dexterity_score=16,
        roller=DiceRoller(FixedRandom([12])),
        bonus=1,
    )

    assert result.dexterity_modifier == 3
    assert result.total == 16


def test_initiative_ties_are_grouped_not_arbitrarily_broken():
    results = (
        roll_initiative(
            combatant_id="hero",
            dexterity_score=14,
            roller=DiceRoller(FixedRandom([12])),
        ),
        roll_initiative(
            combatant_id="goblin",
            dexterity_score=10,
            roller=DiceRoller(FixedRandom([14])),
        ),
        roll_initiative(
            combatant_id="guard",
            dexterity_score=12,
            roller=DiceRoller(FixedRandom([9])),
        ),
    )

    groups = group_initiative_ties(results)

    assert [[item.combatant_id for item in group] for group in groups] == [
        ["hero", "goblin"],
        ["guard"],
    ]
