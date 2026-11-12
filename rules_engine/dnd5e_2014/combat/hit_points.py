"""Deterministic hit-point and death-state transitions for D&D 5e (2014)."""

from __future__ import annotations

from dataclasses import dataclass

from rules_engine.dnd5e_2014.combat.damage import apply_hit_point_damage


@dataclass(frozen=True, slots=True)
class HitPointDamageState:
    """Combatant hit points and death-track state after one damage instance."""

    current_hp: int
    death_save_successes: int
    death_save_failures: int
    stable: bool
    dead: bool
    conscious: bool


def apply_combatant_damage(
    *,
    current_hp: int,
    max_hp: int,
    damage: int,
    death_save_successes: int = 0,
    death_save_failures: int = 0,
    stable: bool = False,
    dead: bool = False,
    conscious: bool = True,
    critical_hit: bool = False,
) -> HitPointDamageState:
    """Apply one damage instance and advance the 2014 death-save state.

    The caller supplies damage after immunity, resistance and vulnerability
    have been applied. This function owns the deterministic HP/death-state
    transition, but deliberately knows nothing about repositories, encounters,
    persistence or application services.
    """
    for value, name in (
        (current_hp, "current_hp"),
        (max_hp, "max_hp"),
        (damage, "damage"),
        (death_save_successes, "death_save_successes"),
        (death_save_failures, "death_save_failures"),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")

    if max_hp < 1:
        raise ValueError("max_hp must be positive")
    if not 0 <= current_hp <= max_hp:
        raise ValueError("current_hp must be between zero and max_hp")
    if damage < 0:
        raise ValueError("damage cannot be negative")
    if not 0 <= death_save_successes <= 3 or not 0 <= death_save_failures <= 3:
        raise ValueError("death saving throw counters must be between zero and three")

    for value, name in (
        (stable, "stable"),
        (dead, "dead"),
        (conscious, "conscious"),
        (critical_hit, "critical_hit"),
    ):
        if not isinstance(value, bool):
            raise TypeError(f"{name} must be a boolean")

    if stable and dead:
        raise ValueError("a combatant cannot be stable and dead")
    if (stable or dead) and (current_hp != 0 or conscious):
        raise ValueError("a stable or dead combatant must be unconscious at zero hit points")
    if stable and death_save_successes != 3:
        raise ValueError("a stable combatant must have three death save successes")
    if dead and death_save_failures != 3:
        raise ValueError("a dead combatant must have three death save failures")
    if death_save_successes == 3 and not stable:
        raise ValueError("three death save successes must stabilize the combatant")
    if death_save_failures == 3 and not dead:
        raise ValueError("three death save failures must kill the combatant")

    new_hp = apply_hit_point_damage(current_hp, damage)
    new_successes = death_save_successes
    new_failures = death_save_failures
    new_stable = stable
    new_dead = dead
    new_conscious = conscious

    if damage > 0 and current_hp == 0:
        was_stable = new_stable
        new_stable = False
        if was_stable:
            new_successes = 0
        new_failures = min(3, new_failures + (2 if critical_hit else 1))
        new_dead = new_failures >= 3
        new_conscious = False
    elif damage > 0 and new_hp == 0:
        # Massive damage kills outright when the excess damage equals or
        # exceeds the creature's hit point maximum.
        new_dead = damage - current_hp >= max_hp
        new_successes = 0
        new_failures = 3 if new_dead else 0
        new_stable = False
        new_conscious = False

    if new_dead:
        new_hp = 0
        new_conscious = False

    return HitPointDamageState(
        current_hp=new_hp,
        death_save_successes=new_successes,
        death_save_failures=new_failures,
        stable=new_stable,
        dead=new_dead,
        conscious=new_conscious,
    )
