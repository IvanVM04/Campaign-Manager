"""SRD 5.1 (D&D 5e 2014) armor data and deterministic AC derivation.

This module contains rules data only. It has no persistence or application
service dependencies.
"""
from dataclasses import dataclass
from enum import Enum


class ArmorCategory(str, Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    SHIELD = "shield"


@dataclass(frozen=True)
class ArmorDefinition:
    key: str
    name: str
    category: ArmorCategory
    base_armor_class: int
    dexterity_bonus_cap: int | None = None
    strength_requirement: int | None = None
    stealth_disadvantage: bool = False

    def __post_init__(self) -> None:
        if not self.key or not self.name:
            raise ValueError("armor key and name must be non-empty")
        if self.base_armor_class < 0:
            raise ValueError("base armor class must be non-negative")
        if self.dexterity_bonus_cap is not None and self.dexterity_bonus_cap < 0:
            raise ValueError("dexterity bonus cap must be non-negative")
        if self.strength_requirement is not None and self.strength_requirement < 1:
            raise ValueError("strength requirement must be positive")
        if self.category is ArmorCategory.SHIELD and self.dexterity_bonus_cap is not None:
            raise ValueError("shields cannot define a Dexterity cap")


def _armor(key, name, category, ac, dex_cap=None, strength=None, stealth=False):
    return ArmorDefinition(key, name, category, ac, dex_cap, strength, stealth)


A = ArmorCategory
_ARMOR = (
    _armor("padded", "Padded", A.LIGHT, 11, stealth=True),
    _armor("leather", "Leather", A.LIGHT, 11),
    _armor("studded_leather", "Studded leather", A.LIGHT, 12),
    _armor("hide", "Hide", A.MEDIUM, 12, 2),
    _armor("chain_shirt", "Chain shirt", A.MEDIUM, 13, 2),
    _armor("scale_mail", "Scale mail", A.MEDIUM, 14, 2, stealth=True),
    _armor("breastplate", "Breastplate", A.MEDIUM, 14, 2),
    _armor("half_plate", "Half plate", A.MEDIUM, 15, 2, stealth=True),
    _armor("ring_mail", "Ring mail", A.HEAVY, 14, strength=None, stealth=True),
    _armor("chain_mail", "Chain mail", A.HEAVY, 16, strength=13, stealth=True),
    _armor("splint", "Splint", A.HEAVY, 17, strength=15, stealth=True),
    _armor("plate", "Plate", A.HEAVY, 18, strength=15, stealth=True),
    _armor("shield", "Shield", A.SHIELD, 2),
)

ARMOR_CATALOG = {armor.key: armor for armor in _ARMOR}


def get_armor(key: str) -> ArmorDefinition:
    try:
        return ARMOR_CATALOG[key]
    except KeyError as exc:
        raise LookupError(f"unknown SRD armor: {key}") from exc


def list_armor() -> tuple[ArmorDefinition, ...]:
    return _ARMOR
