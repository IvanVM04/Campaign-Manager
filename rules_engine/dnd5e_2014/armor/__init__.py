"""D&D 5e (2014) armor rules and catalogue."""

from rules_engine.dnd5e_2014.armor.armor_class import (
    ArmorClassResult,
    derive_armor_class,
    ArmorProficiencyResult,
    derive_armor_proficiency,
)
from rules_engine.dnd5e_2014.armor.catalog import (
    ARMOR_CATALOG,
    ArmorCategory,
    ArmorDefinition,
    get_armor,
    list_armor,
)

__all__ = [
    "ARMOR_CATALOG",
    "ArmorCategory",
    "ArmorClassResult",
    "ArmorProficiencyResult",
    "ArmorDefinition",
    "derive_armor_class",
    "derive_armor_proficiency",
    "get_armor",
    "list_armor",
]
