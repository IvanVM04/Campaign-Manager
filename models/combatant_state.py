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
    action_used: bool = False
    strength: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    proficiency_bonus: int = 2
    death_save_successes: int = 0
    death_save_failures: int = 0
    stable: bool = False
    dead: bool = False
    death_save_last_round: int | None = None
    death_save_last_turn_index: int | None = None

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
            (self.strength, "strength"),
            (self.constitution, "constitution"),
            (self.intelligence, "intelligence"),
            (self.wisdom, "wisdom"),
            (self.charisma, "charisma"),
            (self.proficiency_bonus, "proficiency_bonus"),
            (self.death_save_successes, "death_save_successes"),
            (self.death_save_failures, "death_save_failures"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
        if any(not 1 <= getattr(self, name) <= 30 for name in (
            "strength", "dexterity", "constitution", "intelligence",
            "wisdom", "charisma",
        )):
            raise ValueError("ability scores must be between 1 and 30")
        if not 0 <= self.death_save_successes <= 3 or not 0 <= self.death_save_failures <= 3:
            raise ValueError("death saving throw counters must be between zero and three")
        for value, name in ((self.death_save_last_round, "death_save_last_round"), (self.death_save_last_turn_index, "death_save_last_turn_index")):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if (self.death_save_last_round is None) != (self.death_save_last_turn_index is None):
            raise ValueError("death save turn position must include both round and turn index")
        if self.death_save_last_round == 0:
            raise ValueError("death_save_last_round must be positive")
        if not isinstance(self.stable, bool) or not isinstance(self.dead, bool):
            raise TypeError("stable and dead must be booleans")
        if self.stable and self.dead:
            raise ValueError("a combatant cannot be stable and dead")
        if self.dead and self.current_hp != 0:
            raise ValueError("a dead combatant must have zero hit points")
        if not 0 <= self.proficiency_bonus <= 20:
            raise ValueError("proficiency_bonus must be between 0 and 20")
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
        if not isinstance(self.action_used, bool):
            raise TypeError("action_used must be a boolean")
        if not isinstance(self.conditions, ConditionSet):
            raise TypeError("conditions must be a ConditionSet")

    @property
    def defeated(self) -> bool:
        return self.current_hp == 0
