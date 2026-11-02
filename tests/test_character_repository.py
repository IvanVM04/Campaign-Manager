
import pytest

import database
from database import get_conn, init_db
from models.character_state import CharacterState
from models.entity import Entity
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository


def setup_database(tmp_path):
    original_db_path = database.DB_PATH
    database.DB_PATH = tmp_path / "test_campaign.db"

    init_db()

    return original_db_path


def create_second_campaign():
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO campaign (
                id,
                name
            )
            VALUES (?, ?)
            """,
            (2, "Second Campaign"),
        )


def create_character(
    *,
    campaign_id: int,
    name: str,
) -> CharacterState:

    entity_repository = EntityRepository()
    character_repository = CharacterRepository()

    entity = entity_repository.save_entity(
        Entity(
            name=name,
            entity_type="character",
            description="Test character.",
            notes="",
            active=True,
        ),
        campaign_id=campaign_id,
    )

    return character_repository.save_character(
        CharacterState(
            entity_id=entity.id,
            level=1,
            class_name="Fighter",
            current_hp=10,
            max_hp=10,
            armor_class=12,
        ),
        campaign_id=campaign_id,
    )


def test_character_repository_returns_none_for_missing_character(
    tmp_path,
):
    original_db_path = setup_database(tmp_path)

    try:
        repository = CharacterRepository()

        assert repository.get_character(
            999999,
            campaign_id=1,
        ) is None

    finally:
        database.DB_PATH = original_db_path


def test_character_repository_saves_and_loads_character(
    tmp_path,
):
    original_db_path = setup_database(tmp_path)

    try:
        character = create_character(
            campaign_id=1,
            name="Fungoso",
        )

        repository = CharacterRepository()

        loaded = repository.get_character(
            character.entity_id,
            campaign_id=1,
        )

        assert loaded == character

    finally:
        database.DB_PATH = original_db_path


def test_character_repository_updates_existing_character(
    tmp_path,
):
    original_db_path = setup_database(tmp_path)

    try:
        original = create_character(
            campaign_id=1,
            name="Fungoso",
        )

        repository = CharacterRepository()

        updated = CharacterState(
            entity_id=original.entity_id,
            level=2,
            class_name="Fighter",
            current_hp=15,
            max_hp=18,
            armor_class=15,
        )

        repository.save_character(
            updated,
            campaign_id=1,
        )

        loaded = repository.get_character(
            original.entity_id,
            campaign_id=1,
        )

        assert loaded == updated

    finally:
        database.DB_PATH = original_db_path


def test_character_repository_lists_only_campaign_characters(
    tmp_path,
):
    original_db_path = setup_database(tmp_path)

    try:
        create_second_campaign()

        first = create_character(
            campaign_id=1,
            name="Fungoso",
        )

        second = create_character(
            campaign_id=1,
            name="Aldric",
        )

        other_campaign = create_character(
            campaign_id=2,
            name="Other",
        )

        repository = CharacterRepository()

        assert repository.list_characters(
            campaign_id=1,
        ) == [first, second]

        assert repository.list_characters(
            campaign_id=2,
        ) == [other_campaign]

    finally:
        database.DB_PATH = original_db_path


def test_character_repository_deletes_character(
    tmp_path,
):
    original_db_path = setup_database(tmp_path)

    try:
        character = create_character(
            campaign_id=1,
            name="Fungoso",
        )

        repository = CharacterRepository()

        repository.delete_character(
            character.entity_id,
            campaign_id=1,
        )

        assert repository.get_character(
            character.entity_id,
            campaign_id=1,
        ) is None

    finally:
        database.DB_PATH = original_db_path


def test_character_repository_delete_does_not_delete_entity(
    tmp_path,
):
    original_db_path = setup_database(tmp_path)

    try:
        character = create_character(
            campaign_id=1,
            name="Fungoso",
        )

        repository = CharacterRepository()

        repository.delete_character(
            character.entity_id,
            campaign_id=1,
        )

        assert repository.get_character(
            character.entity_id,
            campaign_id=1,
        ) is None

        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM entities
                WHERE id = ?
                  AND campaign_id = ?
                """,
                (character.entity_id, 1),
            ).fetchone()

        assert row is not None

    finally:
        database.DB_PATH = original_db_path


def test_character_repository_cannot_read_other_campaign(
    tmp_path,
):
    original_db_path = setup_database(tmp_path)

    try:
        create_second_campaign()

        character = create_character(
            campaign_id=1,
            name="Aldric",
        )

        repository = CharacterRepository()

        assert repository.get_character(
            character.entity_id,
            campaign_id=2,
        ) is None

        assert repository.list_characters(
            campaign_id=2,
        ) == []

    finally:
        database.DB_PATH = original_db_path


def test_character_repository_cannot_update_other_campaign(
    tmp_path,
):
    original_db_path = setup_database(tmp_path)

    try:
        create_second_campaign()

        character = create_character(
            campaign_id=1,
            name="Aldric",
        )

        repository = CharacterRepository()

        attempted_update = CharacterState(
            entity_id=character.entity_id,
            level=10,
            class_name="Wizard",
            current_hp=100,
            max_hp=100,
        )

        with pytest.raises(RuntimeError):
            repository.save_character(
                attempted_update,
                campaign_id=2,
            )

        persisted = repository.get_character(
            character.entity_id,
            campaign_id=1,
        )

        assert persisted == character

    finally:
        database.DB_PATH = original_db_path


def test_character_repository_cannot_delete_other_campaign(
    tmp_path,
):
    original_db_path = setup_database(tmp_path)

    try:
        create_second_campaign()

        character = create_character(
            campaign_id=1,
            name="Aldric",
        )

        repository = CharacterRepository()

        repository.delete_character(
            character.entity_id,
            campaign_id=2,
        )

        assert repository.get_character(
            character.entity_id,
            campaign_id=1,
        ) == character

    finally:
        database.DB_PATH = original_db_path
