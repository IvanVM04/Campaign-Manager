"""Damage types and resistance/vulnerability handling for 5e 2014."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DamageType(str, Enum):
    ACID = "acid"
    BLUDGEONING = "bludgeoning"
    COLD = "cold"
    FIRE = "fire"
    FORCE = "force"
    LIGHTNING = "lightning"
    NECROTIC = "necrotic"
    PIERCING = "piercing"
    POISON = "poison"
    PSYCHIC = "psychic"
    RADIANT = "radiant"
    SLASHING = "slashing"
    THUNDER = "thunder"


@dataclass(frozen=True)
class DamageAdjustment:
    """A target's defenses against one damage instance."""

    immune: bool = False
    resistant: bool = False
    vulnerable: bool = False

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, bool)
            for value in (self.immune, self.resistant, self.vulnerable)
        ):
            raise TypeError("damage adjustment flags must be booleans")


def apply_damage_modifiers(
    damage: int,
    adjustment: DamageAdjustment | None = None,
) -> int:
    """Apply immunity, then resistance/vulnerability after other modifiers.

    A creature's simultaneous resistance and vulnerability to the same damage
    cancel each other. Multiple sources of either are represented by one flag.
    """
    if isinstance(damage, bool) or not isinstance(damage, int):
        raise TypeError("damage must be an integer")
    if damage < 0:
        raise ValueError("damage cannot be negative")
    if adjustment is None:
        adjustment = DamageAdjustment()
    elif not isinstance(adjustment, DamageAdjustment):
        raise TypeError("adjustment must be a DamageAdjustment or None")
    if adjustment.immune:
        return 0
    if adjustment.resistant and adjustment.vulnerable:
        return damage
    if adjustment.resistant:
        return damage // 2
    if adjustment.vulnerable:
        return damage * 2
    return damage


def apply_hit_point_damage(current_hp: int, damage: int) -> int:
    """Subtract damage without allowing hit points to fall below zero."""
    for value, name in ((current_hp, "current_hp"), (damage, "damage")):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value < 0:
            raise ValueError(f"{name} cannot be negative")
    return max(0, current_hp - damage)
