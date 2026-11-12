"""Character hit-die rules for D&D 5e (2014)."""

from __future__ import annotations

HIT_DIE_SIDES_BY_CLASS: dict[str, int] = {
    "barbarian": 12,
    "fighter": 10,
    "paladin": 10,
    "ranger": 10,
    "bard": 8,
    "cleric": 8,
    "druid": 8,
    "monk": 8,
    "rogue": 8,
    "warlock": 8,
    "sorcerer": 6,
    "wizard": 6,
}

DEFAULT_HIT_DIE_SIDES = 8


def hit_die_sides_for_class(class_name: str | None) -> int:
    """Return the class Hit Die size.

    The current character model still accepts a free-text class name. Unknown
    or multi-class labels therefore use the documented d8 fallback until
    class selection and multiclass progression become typed mechanics.
    """
    if class_name is None:
        return DEFAULT_HIT_DIE_SIDES
    if not isinstance(class_name, str):
        raise TypeError("class_name must be a string or None")
    normalized = " ".join(class_name.casefold().split())
    return HIT_DIE_SIDES_BY_CLASS.get(normalized, DEFAULT_HIT_DIE_SIDES)
