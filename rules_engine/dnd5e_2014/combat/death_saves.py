"""Death saving throws for D&D 5e (2014)."""

from dataclasses import dataclass

from rules_engine.dnd5e_2014.core.dice import DiceRoller


@dataclass(frozen=True)
class DeathSaveResult:
    """One death saving throw and the resulting death-save track."""

    rolls: tuple[int, ...]
    selected: int
    successes: int
    failures: int
    stable: bool
    dead: bool
    regained_hp: int


def resolve_death_saving_throw(
    *,
    roller: DiceRoller,
    successes: int = 0,
    failures: int = 0,
    manual_rolls: tuple[int, ...] | None = None,
) -> DeathSaveResult:
    """Resolve one unmodified death saving throw.

    A result of 10 or higher is a success. A natural 1 causes two failures;
    a natural 20 restores 1 hit point. Three successes stabilize the creature
    and three failures kill it. Death saves have no ability modifier or
    proficiency bonus.
    """
    if not isinstance(roller, DiceRoller):
        raise TypeError("roller must be a DiceRoller")
    for value, name in ((successes, "successes"), (failures, "failures")):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if not 0 <= value <= 3:
            raise ValueError(f"{name} must be between zero and three")
    if successes == 3 or failures == 3:
        raise ValueError("death saving throw track is already resolved")

    roll = roller.roll_d20(manual_rolls=manual_rolls)
    new_successes = successes
    new_failures = failures
    regained_hp = 0

    if roll.selected == 1:
        new_failures = min(3, new_failures + 2)
    elif roll.selected == 20:
        regained_hp = 1
    elif roll.selected >= 10:
        new_successes += 1
    else:
        new_failures += 1

    dead = new_failures >= 3
    stable = not dead and new_successes >= 3
    return DeathSaveResult(
        rolls=roll.rolls,
        selected=roll.selected,
        successes=new_successes,
        failures=new_failures,
        stable=stable,
        dead=dead,
        regained_hp=regained_hp,
    )
