from dataclasses import dataclass, field
from typing import Any

from rules_engine.dnd5e_2014.core.abilities import Ability
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
    skill_proficiencies: frozenset[Skill] = field(default_factory=frozenset)
    skill_expertise: frozenset[Skill] = field(default_factory=frozenset)
    saving_throw_proficiencies: frozenset[Ability] = field(default_factory=frozenset)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.skill_proficiencies = frozenset(Skill(value) for value in self.skill_proficiencies)
        self.skill_expertise = frozenset(Skill(value) for value in self.skill_expertise)
        self.saving_throw_proficiencies = frozenset(Ability(value) for value in self.saving_throw_proficiencies)
        if not self.skill_expertise.issubset(self.skill_proficiencies):
            raise ValueError("skill expertise requires skill proficiency")
