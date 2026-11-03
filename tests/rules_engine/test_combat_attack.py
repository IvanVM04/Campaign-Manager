import pytest

from rules_engine.dnd5e_2014.combat.attack import resolve_attack
from rules_engine.dnd5e_2014.combat.damage import DamageAdjustment, DamageType
from rules_engine.dnd5e_2014.core.dice import DiceRoller


class FixedRandom:
    def __init__(self, values):
        self.values = iter(values)

    def randint(self, a, b):
        value = next(self.values)
        assert a <= value <= b
        return value


def test_attack_hits_when_total_meets_armor_class():
    result = resolve_attack(
        roller=DiceRoller(FixedRandom([12, 6])),
        attack_bonus=5,
        target_ac=17,
        damage_dice_count=1,
        damage_die_sides=8,
        damage_bonus=3,
        damage_type=DamageType.SLASHING,
    )

    assert result.hit is True
    assert result.critical is False
    assert result.raw_damage == 9


def test_natural_one_always_misses_even_with_large_attack_bonus():
    result = resolve_attack(
        roller=DiceRoller(FixedRandom([1])),
        attack_bonus=20,
        target_ac=10,
        damage_dice_count=1,
        damage_die_sides=8,
        damage_type=DamageType.PIERCING,
    )

    assert result.hit is False
    assert result.damage_roll is None


def test_natural_twenty_critically_hits_and_doubles_damage_dice_only():
    result = resolve_attack(
        roller=DiceRoller(FixedRandom([20, 4, 7])),
        attack_bonus=-5,
        target_ac=30,
        damage_dice_count=1,
        damage_die_sides=8,
        damage_bonus=3,
        damage_type=DamageType.SLASHING,
    )

    assert result.hit is True
    assert result.critical is True
    assert result.damage_roll.rolls == (4, 7)
    assert result.raw_damage == 14


def test_resistance_halves_damage_after_flat_modifiers():
    result = resolve_attack(
        roller=DiceRoller(FixedRandom([15, 5])),
        attack_bonus=0,
        target_ac=10,
        damage_dice_count=1,
        damage_die_sides=8,
        damage_bonus=3,
        damage_type=DamageType.FIRE,
        damage_adjustment=DamageAdjustment(resistant=True),
    )

    assert result.raw_damage == 8
    assert result.damage_after_defenses == 4


def test_manual_attack_and_damage_rolls_are_supported():
    result = resolve_attack(
        roller=DiceRoller(FixedRandom([])),
        attack_bonus=4,
        target_ac=15,
        damage_dice_count=1,
        damage_die_sides=8,
        damage_bonus=2,
        damage_type=DamageType.BLUDGEONING,
        manual_attack_rolls=(14,),
        manual_damage_rolls=(6,),
    )

    assert result.attack_roll.rolls == (14,)
    assert result.damage_roll.rolls == (6,)
    assert result.raw_damage == 8


def test_manual_critical_damage_requires_twice_the_damage_dice():
    with pytest.raises(ValueError):
        resolve_attack(
            roller=DiceRoller(FixedRandom([])),
            attack_bonus=0,
            target_ac=10,
            damage_dice_count=1,
            damage_die_sides=8,
            damage_type=DamageType.SLASHING,
            manual_attack_rolls=(20,),
            manual_damage_rolls=(6,),
        )


def test_missed_attack_rejects_damage_results():
    with pytest.raises(ValueError):
        resolve_attack(
            roller=DiceRoller(FixedRandom([])),
            attack_bonus=0,
            target_ac=20,
            damage_dice_count=1,
            damage_die_sides=8,
            damage_type=DamageType.SLASHING,
            manual_attack_rolls=(2,),
            manual_damage_rolls=(6,),
        )
