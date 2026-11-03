"""Weapon and spell attack roll resolution for D&D 5e (2014)."""

from __future__ import annotations

from dataclasses import dataclass

from rules_engine.dnd5e_2014.combat.damage import (
    DamageAdjustment,
    DamageType,
    apply_damage_modifiers,
)
from rules_engine.dnd5e_2014.core.dice import D20Roll, DiceRoll, DiceRoller


@dataclass(frozen=True)
class AttackResult:
    attack_roll: D20Roll
    target_ac: int
    hit: bool
    critical: bool
    damage_type: DamageType
    damage_roll: DiceRoll | None
    raw_damage: int
    damage_after_defenses: int


def resolve_attack(
    *,
    roller: DiceRoller,
    attack_bonus: int,
    target_ac: int,
    damage_dice_count: int,
    damage_die_sides: int,
    damage_bonus: int = 0,
    damage_type: DamageType,
    advantage: bool = False,
    disadvantage: bool = False,
    damage_adjustment: DamageAdjustment = DamageAdjustment(),
    manual_attack_rolls: tuple[int, ...] | None = None,
    manual_damage_rolls: tuple[int, ...] | None = None,
) -> AttackResult:
    """Resolve one attack, including natural 1/20 and critical damage dice.

    The caller supplies attack/damage bonuses from the weapon, character and
    effects. On a critical hit all damage dice are doubled; flat modifiers are
    added once. Manual damage input must therefore contain twice as many dice
    on a critical hit.
    """
    if not isinstance(roller, DiceRoller):
        raise TypeError("roller must be a DiceRoller")
    for value, name in (
        (attack_bonus, "attack_bonus"),
        (target_ac, "target_ac"),
        (damage_bonus, "damage_bonus"),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
    if isinstance(damage_dice_count, bool) or not isinstance(damage_dice_count, int) or damage_dice_count < 1:
        raise ValueError("damage_dice_count must be a positive integer")
    if isinstance(damage_die_sides, bool) or not isinstance(damage_die_sides, int) or damage_die_sides < 2:
        raise ValueError("damage_die_sides must be at least 2")
    if not isinstance(damage_type, DamageType):
        raise TypeError("damage_type must be a DamageType")
    if not isinstance(advantage, bool) or not isinstance(disadvantage, bool):
        raise TypeError("advantage and disadvantage must be booleans")

    attack_roll = roller.roll_d20(
        modifier=attack_bonus,
        advantage=advantage,
        disadvantage=disadvantage,
        manual_rolls=manual_attack_rolls,
    )
    natural = attack_roll.selected
    critical = natural == 20
    hit = critical or (natural != 1 and attack_roll.total >= target_ac)

    if not hit:
        if manual_damage_rolls is not None:
            raise ValueError("damage rolls must not be supplied for a missed attack")
        return AttackResult(
            attack_roll=attack_roll,
            target_ac=target_ac,
            hit=False,
            critical=False,
            damage_type=damage_type,
            damage_roll=None,
            raw_damage=0,
            damage_after_defenses=0,
        )

    dice_count = damage_dice_count * (2 if critical else 1)
    damage_roll = roller.roll(
        dice_count,
        damage_die_sides,
        modifier=damage_bonus,
        manual_rolls=manual_damage_rolls,
    )
    raw_damage = max(0, damage_roll.total)
    adjusted_damage = apply_damage_modifiers(raw_damage, damage_adjustment)
    return AttackResult(
        attack_roll=attack_roll,
        target_ac=target_ac,
        hit=True,
        critical=critical,
        damage_type=damage_type,
        damage_roll=damage_roll,
        raw_damage=raw_damage,
        damage_after_defenses=adjusted_damage,
    )
