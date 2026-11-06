from collections import deque
from types import SimpleNamespace

from models.character_state import CharacterState
from rules_engine.dnd5e_2014.character_checks import (
    ability_check_for_character,
    saving_throw_for_character,
)
from rules_engine.dnd5e_2014.core.abilities import Ability
from rules_engine.dnd5e_2014.core.dice import DiceRoller
from rules_engine.dnd5e_2014.core.skills import Skill, ability_for_skill


class SequenceRandom:
    def __init__(self, values):
        self.values = deque(values)

    def randint(self, a, b):
        value = self.values.popleft()
        assert a <= value <= b
        return value


def test_all_18_skills_have_2014_governing_abilities():
    assert len(Skill) == 18
    assert ability_for_skill(Skill.ACROBATICS) is Ability.DEXTERITY
    assert ability_for_skill(Skill.ATHLETICS) is Ability.STRENGTH
    assert ability_for_skill(Skill.ARCANA) is Ability.INTELLIGENCE
    assert ability_for_skill(Skill.PERCEPTION) is Ability.WISDOM
    assert ability_for_skill(Skill.PERSUASION) is Ability.CHARISMA


def test_character_skill_check_uses_score_and_proficiency():
    character = CharacterState(
        entity_id=1,
        level=5,
        dexterity=16,
        skill_proficiencies=frozenset({Skill.STEALTH}),
    )
    result = ability_check_for_character(
        character=character,
        roller=DiceRoller(SequenceRandom([10])),
        skill=Skill.STEALTH,
        dc=16,
    )

    assert result.ability is Ability.DEXTERITY
    assert result.ability_modifier == 3
    assert result.proficiency_applied == 3
    assert result.total == 16
    assert result.success is True


def test_character_expertise_doubles_proficiency():
    character = CharacterState(
        entity_id=1,
        level=5,
        intelligence=14,
        skill_proficiencies=frozenset({Skill.INVESTIGATION}),
        skill_expertise=frozenset({Skill.INVESTIGATION}),
    )
    result = ability_check_for_character(
        character=character,
        roller=DiceRoller(SequenceRandom([10])),
        skill=Skill.INVESTIGATION,
        dc=18,
    )

    assert result.proficiency_applied == 6
    assert result.total == 18
    assert result.success is True


def test_character_saving_throw_uses_save_proficiency():
    character = CharacterState(
        entity_id=1,
        level=9,
        constitution=14,
        saving_throw_proficiencies=frozenset({Ability.CONSTITUTION}),
    )
    result = saving_throw_for_character(
        character=character,
        roller=DiceRoller(SequenceRandom([10])),
        ability=Ability.CONSTITUTION,
        dc=16,
    )

    assert result.proficiency_applied == 4
    assert result.total == 16
    assert result.success is True


def test_skill_check_can_use_dm_selected_ability():
    character = CharacterState(
        entity_id=1,
        strength=16,
        charisma=8,
        skill_proficiencies=frozenset({Skill.INTIMIDATION}),
    )
    result = ability_check_for_character(
        character=character,
        roller=DiceRoller(SequenceRandom([10])),
        skill=Skill.INTIMIDATION,
        ability_override=Ability.STRENGTH,
        dc=13,
    )

    assert result.ability is Ability.STRENGTH
    assert result.ability_modifier == 3
    assert result.proficiency_applied == 2
    assert result.total == 15



def test_character_check_accepts_ruleset_input_without_application_model():
    character = SimpleNamespace(
        level=5,
        dexterity=16,
        skill_proficiencies=frozenset({Skill.STEALTH}),
        skill_expertise=frozenset(),
        saving_throw_proficiencies=frozenset(),
    )
    result = ability_check_for_character(
        character=character,
        roller=DiceRoller(SequenceRandom([10])),
        skill=Skill.STEALTH,
        dc=16,
    )

    assert result.total == 16
    assert result.success is True
