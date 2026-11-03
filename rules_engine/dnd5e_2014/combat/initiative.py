"""Initiative checks for D&D 5e (2014)."""

from __future__ import annotations

from dataclasses import dataclass

from rules_engine.dnd5e_2014.core.abilities import ability_modifier
from rules_engine.dnd5e_2014.core.dice import D20Roll, DiceRoller


@dataclass(frozen=True)
class InitiativeResult:
    combatant_id: str
    dexterity_score: int
    dexterity_modifier: int
    roll: D20Roll

    @property
    def total(self) -> int:
        return self.roll.total


def roll_initiative(
    *,
    combatant_id: str,
    dexterity_score: int,
    roller: DiceRoller,
    bonus: int = 0,
    advantage: bool = False,
    disadvantage: bool = False,
    manual_rolls: tuple[int, ...] | None = None,
) -> InitiativeResult:
    """Roll initiative as a Dexterity check; ties are left for the table to break."""
    if not isinstance(combatant_id, str) or not combatant_id.strip():
        raise ValueError("combatant_id must be a non-empty string")
    dex_mod = ability_modifier(dexterity_score)
    if isinstance(bonus, bool) or not isinstance(bonus, int):
        raise TypeError("bonus must be an integer")
    roll = roller.roll_d20(
        modifier=dex_mod + bonus,
        advantage=advantage,
        disadvantage=disadvantage,
        manual_rolls=manual_rolls,
    )
    return InitiativeResult(
        combatant_id=combatant_id,
        dexterity_score=dexterity_score,
        dexterity_modifier=dex_mod,
        roll=roll,
    )


def group_initiative_ties(
    results: tuple[InitiativeResult, ...],
) -> tuple[tuple[InitiativeResult, ...], ...]:
    """Group equal initiative totals without inventing a tie-break rule."""
    if not isinstance(results, tuple) or any(
        not isinstance(result, InitiativeResult) for result in results
    ):
        raise TypeError("results must be a tuple of InitiativeResult values")
    ordered = sorted(results, key=lambda result: result.total, reverse=True)
    groups: list[list[InitiativeResult]] = []
    for result in ordered:
        if not groups or groups[-1][0].total != result.total:
            groups.append([result])
        else:
            groups[-1].append(result)
    return tuple(tuple(group) for group in groups)
