"""Persistent mechanical state for non-player creatures."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CreatureState:
    """Campaign-owned mechanics for an NPC creature, independent of encounters."""

    entity_id: int
    current_hp: int
    max_hp: int
    armor_class: int
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    proficiency_bonus: int = 2
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "entity_id", "current_hp", "max_hp", "armor_class",
            "strength", "dexterity", "constitution", "intelligence",
            "wisdom", "charisma", "proficiency_bonus",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if self.entity_id < 1:
            raise ValueError("entity_id must be positive")
        if self.max_hp < 1 or not 0 <= self.current_hp <= self.max_hp:
            raise ValueError("current_hp must be between zero and positive max_hp")
        if not 0 <= self.armor_class <= 100:
            raise ValueError("armor_class must be between 0 and 100")
        if any(not 1 <= getattr(self, name) <= 30 for name in (
            "strength", "dexterity", "constitution", "intelligence",
            "wisdom", "charisma",
        )):
            raise ValueError("ability scores must be between 1 and 30")
        if not 0 <= self.proficiency_bonus <= 20:
            raise ValueError("proficiency_bonus must be between 0 and 20")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dictionary")
