from models.character_state import CharacterState
from models.entity import Entity
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from rules_engine.dnd5e_2014.core.skills import Skill
from services.characters.character_sheet_query_service import (
    CharacterSheetQueryService,
)


def test_character_sheet_projects_abilities_saves_and_skills():
    character_repository = CharacterRepository()
    entity_repository = EntityRepository()
    entity = entity_repository.save_entity(
        Entity(
            name="Aria",
            entity_type="character",
            description="A travelling wizard.",
            notes="GM-only secret",
        ),
        campaign_id=1,
    )
    character_repository.save_character(
        CharacterState(
            entity_id=entity.id,
            level=3,
            class_name="Wizard",
            current_hp=12,
            max_hp=18,
            strength=8,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=10,
            proficiency_bonus=2,
            skill_proficiencies=frozenset({Skill.ARCANA}),
            skill_expertise=frozenset(),
            saving_throw_proficiencies=frozenset({"intelligence", "wisdom"}),
        ),
        campaign_id=1,
    )

    sheet = CharacterSheetQueryService(
        character_repository,
        entity_repository,
    ).get_sheet(entity.id, campaign_id=1)

    assert sheet is not None
    assert sheet.name == "Aria"
    assert sheet.description == "A travelling wizard."
    assert "GM-only secret" not in str(sheet.model_dump())
    assert sheet.level == 3
    assert sheet.current_hp == 12
    assert sheet.max_hp == 18
    assert {item.ability: item.modifier for item in sheet.abilities}[
        "intelligence"
    ] == 3
    assert {
        item.ability: item.modifier for item in sheet.saving_throws
    }["intelligence"] == 5
    arcana = next(item for item in sheet.skills if item.skill == "arcana")
    assert arcana.proficient is True
    assert arcana.modifier == 5
    athletics = next(
        item for item in sheet.skills if item.skill == "athletics"
    )
    assert athletics.modifier == -1


def test_character_sheet_is_campaign_scoped():
    character_repository = CharacterRepository()
    entity_repository = EntityRepository()
    entity = entity_repository.save_entity(
        Entity(name="Aria", entity_type="character"),
        campaign_id=1,
    )
    character_repository.save_character(
        CharacterState(entity_id=entity.id),
        campaign_id=1,
    )

    service = CharacterSheetQueryService(
        character_repository,
        entity_repository,
    )

    assert service.get_sheet(entity.id, campaign_id=2) is None
