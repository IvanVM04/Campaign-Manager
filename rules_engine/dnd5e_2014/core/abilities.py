"""Ability score primitives for D&D 5e (2014)."""

from enum import Enum


class Ability(str, Enum):
    STRENGTH = "strength"
    DEXTERITY = "dexterity"
    CONSTITUTION = "constitution"
    INTELLIGENCE = "intelligence"
    WISDOM = "wisdom"
    CHARISMA = "charisma"


def ability_modifier(score: int) -> int:
    """Return floor((score - 10) / 2), the 2014 ability modifier formula."""
    if isinstance(score, bool) or not isinstance(score, int):
        raise TypeError("ability score must be an integer")
    if not 1 <= score <= 30:
        raise ValueError("ability score must be between 1 and 30")
    return (score - 10) // 2
