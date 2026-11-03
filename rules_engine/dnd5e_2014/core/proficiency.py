"""Proficiency bonus progression for D&D 5e (2014)."""


def proficiency_bonus_for_level(level: int) -> int:
    """Return the character proficiency bonus for levels 1 through 20."""
    if isinstance(level, bool) or not isinstance(level, int):
        raise TypeError("level must be an integer")
    if not 1 <= level <= 20:
        raise ValueError("level must be between 1 and 20")
    return 2 + (level - 1) // 4
