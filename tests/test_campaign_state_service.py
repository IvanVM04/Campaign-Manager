from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.entity import Entity
from models.turn_context import TurnContext
from models.world_state import WorldState
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from repositories.persistent_effect_repository import PersistentEffectRepository
from services.campaign_state_service import (
    CampaignStateService,
    CampaignStateServiceError,
)
from services.effective_condition_service import EffectiveConditionService
from services.world_service import WorldService


def create_campaign(repository):
    from database import execute

    execute(
        """
        UPDATE campaign
        SET
            name=?,
            system=?,
            tone=?,
            summary=?,
            current_session_id=NULL
        WHERE id=1
        """,
        (
            "Test Campaign",
            "D&D 5e 2014",
            "",
            "",
        ),
    )


def make_service():
    return CampaignStateService(
        campaign_repository=CampaignRepository(),
        character_repository=CharacterRepository(),
        world_service=WorldService(),
        entity_repository=EntityRepository(),
    )


def test_campaign_state_service_returns_complete_state(
    isolated_database,
):
    repository = CampaignRepository()

    create_campaign(repository)

    service = CampaignStateService(
        campaign_repository=repository,
        character_repository=CharacterRepository(),
        world_service=WorldService(),
        entity_repository=EntityRepository(),
    )

    state = service.get_state()

    assert state.campaign_id == 1
    assert state.name == "Test Campaign"
    assert state.system == "D&D 5e 2014"
    assert state.current_session_id is None
    assert state.active_character_id is None


def test_campaign_state_service_sets_and_gets_current_session(
    isolated_database,
):
    campaign_repository = CampaignRepository()

    create_campaign(
        campaign_repository
    )

    session = campaign_repository.create_session(
        number=1,
        campaign_id=1,
        title="Session 1",
        summary="First session",
        start_location="Vorder's Hold",
        end_location="",
        notes="",
    )

    service = CampaignStateService(
        campaign_repository=campaign_repository,
        character_repository=CharacterRepository(),
        world_service=WorldService(),
        entity_repository=EntityRepository(),
    )

    state = service.set_current_session(
        session_id=session["id"],
    )

    assert isinstance(
        state,
        CampaignState,
    )

    assert state.current_session_id == session["id"]

    state = service.get_state()

    assert isinstance(
        state,
        CampaignState,
    )

    assert state.current_session_id == session["id"]


def test_campaign_state_service_can_clear_current_session(
    isolated_database,
):
    campaign_repository = CampaignRepository()

    create_campaign(
        campaign_repository
    )

    session = campaign_repository.create_session(
        number=1,
        campaign_id=1,
        title="Session 1",
        summary="First session",
        start_location="Vorder's Hold",
        end_location="",
        notes="",
    )

    service = CampaignStateService(
        campaign_repository=campaign_repository,
        character_repository=CharacterRepository(),
        world_service=WorldService(),
        entity_repository=EntityRepository(),
    )

    service.set_current_session(
        session_id=session["id"],
    )

    state = service.set_current_session(
        session_id=None,
    )

    assert isinstance(
        state,
        CampaignState,
    )

    assert state.current_session_id is None


def test_campaign_state_service_rejects_missing_session(
    isolated_database,
):
    campaign_repository = CampaignRepository()

    create_campaign(campaign_repository)

    service = CampaignStateService(
        campaign_repository=campaign_repository,
        character_repository=CharacterRepository(),
        world_service=WorldService(),
        entity_repository=EntityRepository(),
    )

    try:
        service.set_current_session(
            session_id=999999,
        )
    except CampaignStateServiceError:
        pass
    else:
        raise AssertionError(
            "Expected CampaignStateServiceError"
        )


def test_campaign_state_service_rejects_missing_active_character(
    isolated_database,
):
    campaign_repository = CampaignRepository()

    create_campaign(campaign_repository)

    service = CampaignStateService(
        campaign_repository=campaign_repository,
        character_repository=CharacterRepository(),
        world_service=WorldService(),
        entity_repository=EntityRepository(),
    )

    try:
        service.set_active_character(
            character_id=999999,
        )
    except CampaignStateServiceError:
        pass
    else:
        raise AssertionError(
            "Expected CampaignStateServiceError"
        )

def test_campaign_state_service_builds_typed_turn_context(
    isolated_database,
):
    campaign_repository = CampaignRepository()

    create_campaign(
        campaign_repository
    )

    service = CampaignStateService(
        campaign_repository=campaign_repository,
        character_repository=CharacterRepository(),
        world_service=WorldService(),
        entity_repository=EntityRepository(),
    )

    context = service.get_turn_context()

    assert isinstance(
        context,
        TurnContext,
    )

    assert isinstance(
        context.campaign,
        CampaignState,
    )

    assert context.campaign.name == (
        "Test Campaign"
    )

    assert context.current_session is None
    assert context.active_character is None

    assert isinstance(
        context.world,
        WorldState,
    )

def test_get_turn_context_works_from_persisted_campaign_state():
    entity_repository = EntityRepository()
    character_repository = CharacterRepository()

    entity = entity_repository.save_entity(
        Entity(
            id=None,
            name="Aldric",
            entity_type="character",
            description="Aldric, aventurero humano.",
            notes="",
            active=True,
        ),
        campaign_id=1,
    )

    character = character_repository.save_character(
        CharacterState(
            entity_id=entity.id,
            level=1,
            class_name="Fighter",
            current_hp=12,
            max_hp=12,
            armor_class=16,
            strength=16,
            dexterity=12,
            constitution=14,
            intelligence=10,
            wisdom=10,
            charisma=10,
            proficiency_bonus=2,
            metadata={},
        ),
        campaign_id=1,
    )

    campaign_repository = CampaignRepository()

    campaign_repository.update_active_character(
        campaign_id=1,
        character_id=character.entity_id,
    )

    service = CampaignStateService(
        campaign_repository=campaign_repository,
        character_repository=character_repository,
        entity_repository=entity_repository,
        world_service=WorldService(),
    )

    context = service.get_turn_context()

    assert context.campaign is not None
    assert context.active_character is not None
    assert context.active_character.entity_id == entity.id
    assert context.active_character_entity is not None
    assert context.active_character_entity.id == entity.id
    assert context.world is not None

def test_get_turn_context_includes_current_session():
    campaign_repository = CampaignRepository()

    session = campaign_repository.create_session(
        campaign_id=1,
        title="Primera sesión",
        number=1,
        summary="Comienza la aventura.",
        start_location="Vorder's Hold",
        end_location="",
        notes="",
    )

    campaign_repository.update_current_session(
        campaign_id=1,
        session_id=session["id"],
    )

    service = CampaignStateService(
        campaign_repository=campaign_repository,
        character_repository=CharacterRepository(),
        entity_repository=EntityRepository(),
        world_service=WorldService(),
    )

    context = service.get_turn_context()

    assert context.current_session is not None
    assert context.current_session.session_id == session["id"]
    assert context.current_session.title == "Primera sesión"

def test_campaign_state_service_accepts_structural_world_state_port(
    isolated_database,
):
    class FakeWorldStatePort:
        campaign_id = 1

        def get_world(self):
            return WorldState()

        def load(self):
            return WorldState()

        def save(self):
            return None

    service = CampaignStateService(
        campaign_repository=CampaignRepository(),
        character_repository=CharacterRepository(),
        entity_repository=EntityRepository(),
        world_service=FakeWorldStatePort(),
    )

    assert isinstance(service.get_world(), WorldState)


def test_campaign_state_service_uses_injected_effective_condition_service(
    isolated_database,
):
    repository = PersistentEffectRepository()
    effective_condition_service = EffectiveConditionService(repository)

    service = CampaignStateService(
        campaign_repository=CampaignRepository(),
        character_repository=CharacterRepository(),
        entity_repository=EntityRepository(),
        world_service=WorldService(),
        effective_condition_service=effective_condition_service,
    )

    assert service.effective_condition_service is effective_condition_service
