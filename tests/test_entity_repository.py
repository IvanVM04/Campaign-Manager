
from models.entity import Entity
from repositories.entity_repository import EntityRepository


def test_entity_repository_saves_and_gets_entity(
    isolated_database,
):
    repository = EntityRepository()

    entity = repository.save_entity(
        Entity(
            id=100,
            name="Aldric",
            entity_type="player_character",
            description="Un aventurero.",
            notes="Conoce Vorder's Hold.",
            active=True,
        ),
        campaign_id=1,
    )

    loaded = repository.get_entity(
        100,
        campaign_id=1,
    )

    assert loaded == entity
    assert loaded is not None
    assert loaded.id == 100
    assert loaded.name == "Aldric"
    assert loaded.entity_type == "player_character"
    assert loaded.description == "Un aventurero."
    assert loaded.notes == "Conoce Vorder's Hold."
    assert loaded.active is True


def test_entity_repository_returns_none_for_missing_entity(
    isolated_database,
):
    repository = EntityRepository()

    assert repository.get_entity(
        999999,
        campaign_id=1,
    ) is None


def test_entity_repository_updates_existing_entity(
    isolated_database,
):
    repository = EntityRepository()

    repository.save_entity(
        Entity(
            id=100,
            name="Aldric",
            entity_type="player_character",
        ),
        campaign_id=1,
    )

    updated = repository.save_entity(
        Entity(
            id=100,
            name="Aldric el Gris",
            entity_type="player_character",
            description="Veterano de Vorder's Hold.",
            notes="Tiene una deuda pendiente.",
            active=True,
        ),
        campaign_id=1,
    )

    loaded = repository.get_entity(
        100,
        campaign_id=1,
    )

    assert loaded == updated
    assert loaded.name == "Aldric el Gris"
    assert loaded.description == "Veterano de Vorder's Hold."
    assert loaded.notes == "Tiene una deuda pendiente."


def test_entity_repository_lists_entities(
    isolated_database,
):
    repository = EntityRepository()

    repository.save_entity(
        Entity(
            id=2,
            name="Vorder's Hold",
            entity_type="location",
        ),
        campaign_id=1,
    )

    repository.save_entity(
        Entity(
            id=1,
            name="Aldric",
            entity_type="player_character",
        ),
        campaign_id=1,
    )

    entities = repository.list_entities(
        campaign_id=1,
    )

    assert [entity.id for entity in entities] == [1, 2]
    assert [entity.name for entity in entities] == [
        "Aldric",
        "Vorder's Hold",
    ]


def test_entity_repository_deletes_entity(
    isolated_database,
):
    repository = EntityRepository()

    repository.save_entity(
        Entity(
            id=100,
            name="Aldric",
            entity_type="player_character",
        ),
        campaign_id=1,
    )

    repository.delete_entity(
        100,
        campaign_id=1,
    )

    assert repository.get_entity(
        100,
        campaign_id=1,
    ) is None


def test_entity_repository_isolates_entities_by_campaign(
    isolated_database,
):
    repository = EntityRepository()

    entity = repository.save_entity(
        Entity(
            id=100,
            name="Aldric",
            entity_type="player_character",
        ),
        campaign_id=1,
    )

    assert repository.get_entity(
        100,
        campaign_id=1,
    ) == entity

    assert repository.get_entity(
        100,
        campaign_id=2,
    ) is None

    assert repository.list_entities(
        campaign_id=2,
    ) == []

    repository.delete_entity(
        100,
        campaign_id=2,
    )

    assert repository.get_entity(
        100,
        campaign_id=1,
    ) == entity
