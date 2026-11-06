from models.character_state import CharacterState
from services.characters import (
    CharacterService,
    CharacterServiceError,
)


class RecordingCharacterRepository:

    def __init__(
        self,
        character=None,
    ):
        self.character = character
        self.saved = []

    def get_character(
        self,
        entity_id,
        *,
        campaign_id,
        conn=None,
    ):
        if (
            self.character is not None
            and self.character.entity_id == entity_id
        ):
            return self.character

        return None


    def save_character(
        self,
        character,
        *,
        campaign_id,
        conn=None,
    ):
        self.saved.append(character)
        self.character = character
        return character


def make_character(
    current_hp=10,
    max_hp=10,
):
    return CharacterState(
        entity_id=1,
        current_hp=current_hp,
        max_hp=max_hp,
    )


def test_change_hp_applies_damage():

    repository = RecordingCharacterRepository(
        make_character(
            current_hp=10,
            max_hp=10,
        )
    )

    service = CharacterService(repository)

    result = service.change_hp(
        entity_id=1,
        amount=-4,
        campaign_id=1,
    )

    assert result.current_hp == 6
    assert repository.saved[-1].current_hp == 6


def test_change_hp_applies_healing():

    repository = RecordingCharacterRepository(
        make_character(
            current_hp=6,
            max_hp=10,
        )
    )

    service = CharacterService(repository)

    result = service.change_hp(
        entity_id=1,
        amount=3,
        campaign_id=1,
    )

    assert result.current_hp == 9


def test_change_hp_cannot_go_below_zero():

    repository = RecordingCharacterRepository(
        make_character(
            current_hp=3,
            max_hp=10,
        )
    )

    service = CharacterService(repository)

    result = service.change_hp(
        entity_id=1,
        amount=-50,
        campaign_id=1,
    )

    assert result.current_hp == 0


def test_change_hp_cannot_exceed_max_hp():

    repository = RecordingCharacterRepository(
        make_character(
            current_hp=8,
            max_hp=10,
        )
    )

    service = CharacterService(repository)

    result = service.change_hp(
        entity_id=1,
        amount=50,
        campaign_id=1,
    )

    assert result.current_hp == 10


def test_change_hp_rejects_missing_character():

    repository = RecordingCharacterRepository()

    service = CharacterService(repository)

    try:
        service.change_hp(
            entity_id=999,
            amount=-5,
            campaign_id=1,
        )
    except CharacterServiceError as exc:
        assert str(exc) == (
            "Character 999 not found"
        )
    else:
        raise AssertionError(
            "Expected CharacterServiceError"
        )


def test_change_hp_preserves_character_state():

    character = CharacterState(
        entity_id=1,
        level=3,
        class_name="Fighter",
        current_hp=12,
        max_hp=18,
        armor_class=16,
        strength=16,
        dexterity=12,
        constitution=14,
        intelligence=10,
        wisdom=11,
        charisma=8,
        proficiency_bonus=2,
        skill_proficiencies=frozenset({"stealth"}),
        skill_expertise=frozenset({"stealth"}),
        saving_throw_proficiencies=frozenset({"dexterity"}),
        metadata={
            "race": "Human",
        },
    )

    repository = RecordingCharacterRepository(
        character
    )

    service = CharacterService(repository)

    result = service.change_hp(
        entity_id=1,
        amount=-5,
        campaign_id=1,
    )

    assert result.current_hp == 7
    assert result.max_hp == 18
    assert result.level == 3
    assert result.class_name == "Fighter"
    assert result.armor_class == 16
    assert result.strength == 16
    assert result.dexterity == 12
    assert result.constitution == 14
    assert result.metadata == {
        "race": "Human",
    }

def test_change_hp_passes_connection_to_repository():

    class RecordingRepository:

        def __init__(self):
            self.get_conn = None
            self.save_conn = None

        def get_character(
            self,
            entity_id,
            *,
            campaign_id,
            conn=None,
        ):
            self.get_conn = conn
            self.get_campaign_id = campaign_id

            return CharacterState(
                entity_id=entity_id,
                current_hp=10,
                max_hp=10,
            )


        def save_character(
            self,
            character,
            *,
            campaign_id,
            conn=None,
        ):
            self.save_conn = conn
            self.save_campaign_id = campaign_id
            return character

    repository = RecordingRepository()

    service = CharacterService(repository)

    connection = object()

    result = service.change_hp(
        entity_id=1,
        amount=-4,
        campaign_id=1,
        conn=connection,
    )

    assert result.current_hp == 6
    assert repository.get_conn is connection
    assert repository.save_conn is connection
    assert repository.get_campaign_id == 1
    assert repository.save_campaign_id == 1

def test_change_hp_works_without_explicit_connection():

    repository = RecordingCharacterRepository(
        make_character(
            current_hp=10,
            max_hp=10,
        )
    )

    service = CharacterService(repository)

    result = service.change_hp(
        entity_id=1,
        amount=-3,
        campaign_id=1,
    )

    assert result.current_hp == 7