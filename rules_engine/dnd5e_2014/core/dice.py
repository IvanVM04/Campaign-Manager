"""Dice primitives for the D&D 5e 2014 ruleset.

The roller accepts an injected random source so tests and simulations can
reproduce every result. Production callers may use the default SystemRandom.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class RandomSource(Protocol):
    """Minimal interface required from a random number source."""

    def randint(self, a: int, b: int) -> int:
        """Return an integer N such that a <= N <= b."""


class RollMode(str, Enum):
    NORMAL = "normal"
    ADVANTAGE = "advantage"
    DISADVANTAGE = "disadvantage"


@dataclass(frozen=True)
class DiceRoll:
    """Result of rolling one or more identical dice."""

    count: int
    sides: int
    rolls: tuple[int, ...]
    modifier: int
    total: int


@dataclass(frozen=True)
class D20Roll:
    """Auditable d20 result, including both dice when applicable."""

    rolls: tuple[int, ...]
    selected: int
    mode: RollMode
    modifier: int
    total: int


class DiceRoller:
    """Roll dice using an explicit, replaceable source of randomness."""

    def __init__(self, rng: RandomSource | None = None) -> None:
        self._rng = rng if rng is not None else random.SystemRandom()

    def roll(
        self,
        count: int,
        sides: int,
        *,
        modifier: int = 0,
        manual_rolls: tuple[int, ...] | None = None,
    ) -> DiceRoll:
        """Roll count dice with the given number of sides."""
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("count must be a positive integer")
        if isinstance(sides, bool) or not isinstance(sides, int) or sides < 2:
            raise ValueError("sides must be an integer of at least 2")
        if isinstance(modifier, bool) or not isinstance(modifier, int):
            raise TypeError("modifier must be an integer")

        if manual_rolls is None:
            rolls = tuple(self._rng.randint(1, sides) for _ in range(count))
        else:
            if not isinstance(manual_rolls, tuple):
                raise TypeError("manual_rolls must be a tuple of integers")
            if len(manual_rolls) != count:
                raise ValueError(f"this roll requires exactly {count} manual result(s)")
            if any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
                or value > sides
                for value in manual_rolls
            ):
                raise ValueError(f"manual results must be integers from 1 to {sides}")
            rolls = manual_rolls

        return DiceRoll(
            count=count,
            sides=sides,
            rolls=rolls,
            modifier=modifier,
            total=sum(rolls) + modifier,
        )

    def roll_d20(
        self,
        *,
        modifier: int = 0,
        advantage: bool = False,
        disadvantage: bool = False,
        manual_rolls: tuple[int, ...] | None = None,
    ) -> D20Roll:
        """Roll a d20, applying the 2014 advantage/disadvantage rule.

        Advantage and disadvantage cancel each other, regardless of how many
        sources impose either condition. Otherwise, exactly two d20s are
        rolled and the higher/lower result is selected.
        """
        if isinstance(modifier, bool) or not isinstance(modifier, int):
            raise TypeError("modifier must be an integer")
        if not isinstance(advantage, bool) or not isinstance(disadvantage, bool):
            raise TypeError("advantage and disadvantage must be booleans")

        if advantage and disadvantage:
            mode = RollMode.NORMAL
        elif advantage:
            mode = RollMode.ADVANTAGE
        elif disadvantage:
            mode = RollMode.DISADVANTAGE
        else:
            mode = RollMode.NORMAL

        dice_count = 2 if mode is not RollMode.NORMAL else 1
        if manual_rolls is None:
            rolls = tuple(
                self._rng.randint(1, 20) for _ in range(dice_count)
            )
        else:
            if not isinstance(manual_rolls, tuple):
                raise TypeError("manual_rolls must be a tuple of integers")
            if len(manual_rolls) != dice_count:
                raise ValueError(
                    f"this roll requires exactly {dice_count} manual d20 result(s)"
                )
            if any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
                or value > 20
                for value in manual_rolls
            ):
                raise ValueError("manual d20 results must be integers from 1 to 20")
            rolls = manual_rolls

        if mode is RollMode.ADVANTAGE:
            selected = max(rolls)
        elif mode is RollMode.DISADVANTAGE:
            selected = min(rolls)
        else:
            selected = rolls[0]

        return D20Roll(
            rolls=rolls,
            selected=selected,
            mode=mode,
            modifier=modifier,
            total=selected + modifier,
        )
