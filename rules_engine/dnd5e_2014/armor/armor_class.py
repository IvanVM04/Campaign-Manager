"""Deterministic armor class calculation for D&D 5e (2014)."""

from dataclasses import dataclass

from rules_engine.dnd5e_2014.armor.catalog import ArmorCategory, get_armor


@dataclass(frozen=True)
class ArmorClassResult:
    armor_class: int
    armor_key: str | None
    shield_bonus: int
    dexterity_modifier: int
    dexterity_applied: int
    strength_requirement_met: bool
    speed_penalty_ft: int
    stealth_disadvantage: bool


def derive_armor_class(
    *,
    dexterity_score: int,
    armor_key: str | None = None,
    shield_equipped: bool = False,
    strength_score: int = 10,
) -> ArmorClassResult:
    """Calculate AC from one armor item and an optional shield.

    With no body armor, AC is 10 + Dexterity modifier. Light armor adds
    the full modifier, medium armor caps it at +2, and heavy armor adds none.
    A shield adds +2 independently of body armor.
    """
    for value, name in (
        (dexterity_score, "dexterity_score"),
        (strength_score, "strength_score"),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if not 1 <= value <= 30:
            raise ValueError(f"{name} must be between 1 and 30")
    if not isinstance(shield_equipped, bool):
        raise TypeError("shield_equipped must be a boolean")

    dexterity_modifier = (dexterity_score - 10) // 2
    armor = get_armor(armor_key) if armor_key is not None else None
    if armor is not None and armor.category is ArmorCategory.SHIELD:
        raise ValueError("a shield must be supplied through shield_equipped")

    if armor is None:
        base_ac = 10
        dexterity_applied = dexterity_modifier
        strength_met = True
        stealth_disadvantage = False
    else:
        base_ac = armor.base_armor_class
        if armor.category is ArmorCategory.LIGHT:
            dexterity_applied = dexterity_modifier
        elif armor.category is ArmorCategory.MEDIUM:
            dexterity_applied = min(dexterity_modifier, 2)
        else:
            dexterity_applied = 0
        strength_met = (
            armor.strength_requirement is None
            or strength_score >= armor.strength_requirement
        )
        stealth_disadvantage = armor.stealth_disadvantage

    shield_bonus = 2 if shield_equipped else 0
    return ArmorClassResult(
        armor_class=base_ac + dexterity_applied + shield_bonus,
        armor_key=armor_key,
        shield_bonus=shield_bonus,
        dexterity_modifier=dexterity_modifier,
        dexterity_applied=dexterity_applied,
        strength_requirement_met=strength_met,
        speed_penalty_ft=10 if not strength_met else 0,
        stealth_disadvantage=stealth_disadvantage,
    )


@dataclass(frozen=True)
class ArmorProficiencyResult:
    armor_proficient: bool
    unproficient_armor_keys: tuple[str, ...]
    strength_dexterity_disadvantage: bool
    spellcasting_blocked: bool


def derive_armor_proficiency(
    *,
    armor_key: str | None,
    shield_equipped: bool,
    proficiencies: frozenset[str] | set[str] | tuple[str, ...],
) -> ArmorProficiencyResult:
    """Apply the 2014 armor-training rule to equipped body armor and shield."""
    valid = {"light", "medium", "heavy", "shields"}
    normalized = frozenset(proficiencies)
    if not normalized.issubset(valid):
        raise ValueError("unknown armor proficiency")
    if not isinstance(shield_equipped, bool):
        raise TypeError("shield_equipped must be a boolean")

    unproficient: list[str] = []
    if armor_key is not None:
        armor = get_armor(armor_key)
        if armor.category is ArmorCategory.SHIELD:
            raise ValueError("a shield must be supplied through shield_equipped")
        if armor.category.value not in normalized:
            unproficient.append(armor_key)
    if shield_equipped and "shields" not in normalized:
        unproficient.append("shield")

    proficient = not unproficient
    return ArmorProficiencyResult(
        armor_proficient=proficient,
        unproficient_armor_keys=tuple(unproficient),
        strength_dexterity_disadvantage=not proficient,
        spellcasting_blocked=not proficient,
    )
