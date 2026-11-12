from dataclasses import dataclass, field
from typing import Any

from rules_engine.dnd5e_2014.core.abilities import Ability
from rules_engine.dnd5e_2014.core.hit_dice import hit_die_sides_for_class
from rules_engine.dnd5e_2014.core.skills import Skill


@dataclass
class CharacterState:
    """Mechanical state for a D&D 5e (2014) character."""

    entity_id: int
    level: int = 1
    class_name: str | None = None
    current_hp: int = 0
    max_hp: int = 0
    armor_class: int = 10
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    proficiency_bonus: int = 2
    hit_die_sides: int | None = None
    hit_dice_used: int = 0
    last_long_rest_elapsed_minutes: int | None = None
    skill_proficiencies: frozenset[Skill] = field(default_factory=frozenset)
    skill_expertise: frozenset[Skill] = field(default_factory=frozenset)
    saving_throw_proficiencies: frozenset[Ability] = field(default_factory=frozenset)
    weapon_proficiencies: frozenset[str] = field(default_factory=frozenset)
    armor_proficiencies: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.hit_die_sides is None:
            self.hit_die_sides = hit_die_sides_for_class(self.class_name)
        if (
            isinstance(self.hit_die_sides, bool)
            or not isinstance(self.hit_die_sides, int)
            or self.hit_die_sides not in (6, 8, 10, 12)
        ):
            raise ValueError("hit_die_sides must be one of 6, 8, 10 or 12")
        if (
            isinstance(self.hit_dice_used, bool)
            or not isinstance(self.hit_dice_used, int)
            or not 0 <= self.hit_dice_used <= self.level
        ):
            raise ValueError("hit_dice_used must be between zero and character level")
        if self.last_long_rest_elapsed_minutes is not None and (
            isinstance(self.last_long_rest_elapsed_minutes, bool)
            or not isinstance(self.last_long_rest_elapsed_minutes, int)
            or self.last_long_rest_elapsed_minutes < 0
        ):
            raise ValueError("last_long_rest_elapsed_minutes must be non-negative or None")
        self.skill_proficiencies = frozenset(Skill(value) for value in self.skill_proficiencies)
        self.skill_expertise = frozenset(Skill(value) for value in self.skill_expertise)
        self.saving_throw_proficiencies = frozenset(Ability(value) for value in self.saving_throw_proficiencies)
        self.weapon_proficiencies = frozenset(str(value) for value in self.weapon_proficiencies)
        self.armor_proficiencies = frozenset(
            str(value) for value in self.armor_proficiencies
        )
        valid_armor_proficiencies = {"light", "medium", "heavy", "shields"}
        if not self.armor_proficiencies.issubset(valid_armor_proficiencies):
            raise ValueError("armor proficiencies must be light, medium, heavy or shields")
        if any(not value.strip() for value in self.weapon_proficiencies):
            raise ValueError('weapon proficiencies must be non-empty identifiers')
        if not self.skill_expertise.issubset(self.skill_proficiencies):
            raise ValueError("skill expertise requires skill proficiency")
