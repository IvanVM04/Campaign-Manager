import pytest

from models.schemas import CharacterCreate
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from services.characters import CharacterCreationService


def create_campaign():
    from database import execute

    execute(
        """
        UPDATE campaign
        SET
            name=?,
            system=?,
            tone=?,
            summary=?,
            current_session_id=NULL,
            active_character_id=NULL
        WHERE id=1
        """,
        (
            "Test Campaign",
            "D&D 5e 2014",
            "",
            "",
        ),
    )


@pytest.fixture
def character_creation_service(
    isolated_database,
):
    create_campaign()

    return CharacterCreationService(
        campaign_repository=CampaignRepository(),
        entity_repository=EntityRepository(),
        character_repository=CharacterRepository(),
    )


def test_create_character_creates_entity_and_character(
    character_creation_service,
):
    data = CharacterCreate(
        name="Aragorn",
        class_name="Ranger",
        level=1,
        max_hp=12,
        current_hp=12,
        armor_class=14,
        strength=14,
        dexterity=16,
        constitution=12,
        intelligence=10,
        wisdom=13,
        charisma=11,
        proficiency_bonus=2,
        skill_proficiencies=["stealth", "perception"],
        skill_expertise=["stealth"],
        saving_throw_proficiencies=["dexterity", "wisdom"],
        armor_proficiencies=["light", "shields"],
    )

    character = character_creation_service.create_character(
        campaign_id=1,
        data=data,
        activate=False,
    )

    assert character.entity_id is not None
    assert character.level == 1
    assert character.class_name == "Ranger"
    assert character.current_hp == 12
    assert character.max_hp == 12
    assert character.armor_class == 14
    assert character.strength == 14
    assert character.dexterity == 16
    assert character.constitution == 12
    assert character.intelligence == 10
    assert character.wisdom == 13
    assert character.charisma == 11
    assert character.proficiency_bonus == 2
    assert {skill.value for skill in character.skill_proficiencies} == {"stealth", "perception"}
    assert {skill.value for skill in character.skill_expertise} == {"stealth"}
    assert {ability.value for ability in character.saving_throw_proficiencies} == {"dexterity", "wisdom"}
    assert character.armor_proficiencies == frozenset({"light", "shields"})

    entity_repository = EntityRepository()
    character_repository = CharacterRepository()

    entity = entity_repository.get_entity(
        character.entity_id,
        campaign_id=1,
    )

    persisted_character = character_repository.get_character(
        character.entity_id,
        campaign_id=1,
    )

    assert entity is not None
    assert entity.id == character.entity_id
    assert entity.name == "Aragorn"
    assert entity.entity_type == "player_character"

    assert persisted_character is not None
    assert persisted_character.entity_id == character.entity_id
    assert persisted_character.class_name == "Ranger"
    assert persisted_character.armor_proficiencies == frozenset({"light", "shields"})


def test_create_character_activates_character(
    character_creation_service,
):
    data = CharacterCreate(
        name="Gandalf",
        class_name="Wizard",
        level=1,
        max_hp=8,
        current_hp=8,
        armor_class=12,
        strength=8,
        dexterity=12,
        constitution=10,
        intelligence=16,
        wisdom=14,
        charisma=10,
        proficiency_bonus=2,
    )

    character = character_creation_service.create_character(
        campaign_id=1,
        data=data,
        activate=True,
    )

    campaign_repository = CampaignRepository()

    active_character_id = (
        campaign_repository.get_active_character_id(
            campaign_id=1
        )
    )

    assert active_character_id == character.entity_id

def test_create_character_rolls_back_all_changes_on_activation_failure(
    character_creation_service,
    monkeypatch,
):
    data = CharacterCreate(
        name="Boromir",
        class_name="Fighter",
        level=1,
        max_hp=14,
        current_hp=14,
        armor_class=16,
        strength=16,
        dexterity=12,
        constitution=14,
        intelligence=10,
        wisdom=10,
        charisma=12,
        proficiency_bonus=2,
    )

    created_entity_id = None

    original_save_character = (
        character_creation_service.character_repository
        .save_character
    )

    def capture_character_and_continue(
        character,
        *,
        campaign_id,
        conn=None,
    ):
        nonlocal created_entity_id

        created_entity_id = character.entity_id

        return original_save_character(
            character,
            campaign_id=campaign_id,
            conn=conn,
        )

    monkeypatch.setattr(
        character_creation_service.character_repository,
        "save_character",
        capture_character_and_continue,
    )

    def failing_update_active_character(
        campaign_id,
        character_id,
        *,
        conn=None,
    ):
        raise RuntimeError(
            "forced activation failure"
        )

    monkeypatch.setattr(
        character_creation_service.campaign_repository,
        "update_active_character",
        failing_update_active_character,
    )

    with pytest.raises(
        RuntimeError,
        match="forced activation failure",
    ):
        character_creation_service.create_character(
            campaign_id=1,
            data=data,
            activate=True,
        )

    assert created_entity_id is not None

    entity_repository = EntityRepository()
    character_repository = CharacterRepository()
    campaign_repository = CampaignRepository()

    assert (
        entity_repository.get_entity(
            created_entity_id,
            campaign_id=1,
        )
        is None
    )

    assert (
        character_repository.get_character(
            created_entity_id,
            campaign_id=1,
        )
        is None
    )

    assert (
        campaign_repository.get_active_character_id(
            campaign_id=1
        )
        is None
    )

def test_character_create_rejects_expertise_without_proficiency():
    with pytest.raises(ValueError, match="expertise requires skill proficiency"):
        CharacterCreate(name="Invalid", max_hp=8, skill_expertise=["stealth"])


def test_character_create_rejects_duplicate_armor_proficiencies():
    with pytest.raises(ValueError, match="armor_proficiencies cannot contain duplicates"):
        CharacterCreate(
            name="Duplicate training",
            max_hp=8,
            armor_proficiencies=["light", "light"],
        )


def test_character_create_rejects_unknown_armor_proficiency():
    with pytest.raises(ValueError):
        CharacterCreate(
            name="Invalid training",
            max_hp=8,
            armor_proficiencies=["plate"],
        )
