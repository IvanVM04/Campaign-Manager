"""Ruleset-facing character data contracts.

The rules engine deliberately depends on this structural contract rather than on
application/domain models. Application character aggregates can satisfy it
directly or through a small adapter.
"""

from typing import Protocol

from rules_engine.dnd5e_2014.core.abilities import Ability
from rules_engine.dnd5e_2014.core.skills import Skill


class CharacterRulesInput(Protocol):
    """Minimum character data required by the D&D 5e (2014) rules."""

    level: int
    proficiency_bonus: int

    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int

    skill_proficiencies: frozenset[Skill]
    skill_expertise: frozenset[Skill]
    saving_throw_proficiencies: frozenset[Ability]
    weapon_proficiencies: frozenset[str]
