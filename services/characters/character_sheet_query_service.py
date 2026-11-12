from typing import ClassVar

from models.character_sheet_read_models import (
    AbilityScoreRead,
    CharacterSheetRead,
    SavingThrowRead,
    SkillRead,
)
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from rules_engine.dnd5e_2014.core.abilities import Ability, ability_modifier
from rules_engine.dnd5e_2014.core.skills import (
    SKILL_ABILITIES,
    Skill,
    ability_for_skill,
)


class CharacterSheetQueryService:
    """Build detached D&D 5e character-sheet projections."""

    _ABILITY_FIELDS: ClassVar[dict[Ability, str]] = {
        Ability.STRENGTH: "strength",
        Ability.DEXTERITY: "dexterity",
        Ability.CONSTITUTION: "constitution",
        Ability.INTELLIGENCE: "intelligence",
        Ability.WISDOM: "wisdom",
        Ability.CHARISMA: "charisma",
    }

    def __init__(
        self,
        character_repository: CharacterRepository | None = None,
        entity_repository: EntityRepository | None = None,
    ) -> None:
        self.character_repository = character_repository or CharacterRepository()
        self.entity_repository = entity_repository or EntityRepository()

    def get_sheet(
        self,
        entity_id: int,
        *,
        campaign_id: int,
    ) -> CharacterSheetRead | None:
        character = self.character_repository.get_character(
            entity_id,
            campaign_id=campaign_id,
        )
        if character is None:
            return None

        entity = self.entity_repository.get_entity(
            entity_id,
            campaign_id=campaign_id,
        )
        if entity is None:
            return None

        scores = {
            ability: getattr(character, field)
            for ability, field in self._ABILITY_FIELDS.items()
        }
        abilities = tuple(
            AbilityScoreRead(
                ability=ability.value,
                score=score,
                modifier=ability_modifier(score),
            )
            for ability, score in scores.items()
        )
        saving_throws = tuple(
            SavingThrowRead(
                ability=ability.value,
                proficient=ability in character.saving_throw_proficiencies,
                modifier=ability_modifier(scores[ability])
                + (
                    character.proficiency_bonus
                    if ability in character.saving_throw_proficiencies
                    else 0
                ),
            )
            for ability in Ability
        )
        skills = tuple(
            SkillRead(
                skill=skill.value,
                ability=ability_for_skill(skill).value,
                proficient=skill in character.skill_proficiencies,
                expertise=skill in character.skill_expertise,
                modifier=ability_modifier(scores[SKILL_ABILITIES[skill]])
                + character.proficiency_bonus
                * (
                    2 if skill in character.skill_expertise
                    else 1 if skill in character.skill_proficiencies
                    else 0
                ),
            )
            for skill in Skill
        )

        hit_die_sides = character.hit_die_sides
        if hit_die_sides is None:
            raise RuntimeError("character Hit Die size is missing")

        return CharacterSheetRead(
            entity_id=entity_id,
            name=entity.name,
            entity_type=entity.entity_type,
            description=entity.description,
            active=entity.active,
            level=character.level,
            class_name=character.class_name,
            current_hp=character.current_hp,
            max_hp=character.max_hp,
            armor_class=character.armor_class,
            proficiency_bonus=character.proficiency_bonus,
            hit_die_sides=hit_die_sides,
            hit_dice_total=character.level,
            hit_dice_used=character.hit_dice_used,
            hit_dice_available=character.level - character.hit_dice_used,
            abilities=abilities,
            saving_throws=saving_throws,
            skills=skills,
            weapon_proficiencies=tuple(sorted(character.weapon_proficiencies)),
            armor_proficiencies=tuple(sorted(character.armor_proficiencies)),
        )
