"""Combatant snapshot used by an active D&D 5e (2014) encounter."""

from __future__ import annotations

from dataclasses import dataclass, field

from rules_engine.dnd5e_2014.combat.conditions import ConditionSet


@dataclass(frozen=True)
class CombatantState:
    combatant_id: str
    name: str
    initiative: int
    current_hp: int
    max_hp: int
    armor_class: int
    entity_id: int | None = None
    is_player_character: bool = False
    conscious: bool = True
    conditions: ConditionSet = field(default_factory=ConditionSet)
    dexterity: int = 10

    def __post_init__(self) -> None:
        if not isinstance(self.combatant_id, str) or not self.combatant_id.strip():
            raise ValueError("combatant_id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        for value, field_name in (
            (self.initiative, "initiative"),
            (self.current_hp, "current_hp"),
            (self.max_hp, "max_hp"),
            (self.armor_class, "armor_class"),
            (self.dexterity, "dexterity"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
        if not 1 <= self.dexterity <= 30:
            raise ValueError("dexterity must be between 1 and 30")
        if self.max_hp < 1:
            raise ValueError("max_hp must be positive")
        if not 0 <= self.current_hp <= self.max_hp:
            raise ValueError("current_hp must be between zero and max_hp")
        if self.entity_id is not None and (
            isinstance(self.entity_id, bool)
            or not isinstance(self.entity_id, int)
            or self.entity_id < 1
        ):
            raise ValueError("entity_id must be a positive integer or None")
        if not isinstance(self.is_player_character, bool):
            raise TypeError("is_player_character must be a boolean")
        if not isinstance(self.conscious, bool):
            raise TypeError("conscious must be a boolean")
        if not isinstance(self.conditions, ConditionSet):
            raise TypeError("conditions must be a ConditionSet")

    @property
    def defeated(self) -> bool:
        return self.current_hp == 0
