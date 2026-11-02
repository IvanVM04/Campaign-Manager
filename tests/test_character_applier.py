from models.character_state import CharacterState
from models.operation_result import (
    OperationResult,
    OperationStatus,
)
from operations.character_operations import (
    ChangeCharacterHpOperation,
)
from services.character_applier import (
    CharacterApplier,
    CharacterApplierError,
    CharacterServiceError,
)


class RecordingCharacterService:

    def __init__(self):
        self.calls = []

    def change_hp(
        self,
        *,
        entity_id,
        amount,
        campaign_id,
        conn=None,
    ):
        self.calls.append(
            (
                entity_id,
                amount,
                campaign_id,
            )
        )

        return CharacterState(
            entity_id=entity_id,
            current_hp=6,
            max_hp=10,
        )


def test_change_hp_operation_is_applied():

    service = RecordingCharacterService()

    applier = CharacterApplier(service)

    operation = ChangeCharacterHpOperation(
        entity_id=1,
        amount=-4,
    )

    result = applier.apply(
        operation,
        campaign_id=1,
    )

    assert service.calls == [
        (1, -4, 1),
    ]

    assert isinstance(
        result,
        OperationResult,
    )

    assert result.status == OperationStatus.SUCCESS
    assert result.success is True
    assert result.changed is True

    assert result.operation == operation

    assert result.data == {
        "entity_id": 1,
        "current_hp": 6,
    }

def test_unsupported_character_operation_is_rejected():

    service = RecordingCharacterService()

    applier = CharacterApplier(service)

    class UnsupportedOperation:
        pass

    try:
        applier.apply(
            UnsupportedOperation()
        )
    except CharacterApplierError as exc:
        assert str(exc) == (
            "unsupported character operation: "
            "UnsupportedOperation"
        )
    else:
        raise AssertionError(
            "Expected CharacterApplierError"
        )


def test_character_service_error_returns_failed_operation_result():

    class FailingCharacterService:

        def change_hp(
            self,
            *,
            entity_id,
            amount,
        ):
            raise CharacterServiceError(
                "character failure"
            )

    applier = CharacterApplier(
        FailingCharacterService()
    )

    operation = ChangeCharacterHpOperation(
        entity_id=1,
        amount=-4,
    )

    result = applier.apply(
        operation,
        campaign_id=1,
    )

    assert result.success is False
    assert result.status == OperationStatus.INVALID
    assert result.operation == operation
    assert result.message == "character failure"


def test_apply_change_character_hp_passes_connection():
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )
    from services.character_applier import (
        CharacterApplier,
    )

    class RecordingCharacterService:

        def __init__(self):
            self.calls = []

        def change_hp(
            self,
            entity_id,
            amount,
            *,
            campaign_id,
            conn=None,
        ):
            self.calls.append(
                (
                    entity_id,
                    amount,
                    campaign_id,
                    conn,
                )
            )

            return type(
                "Character",
                (),
                {
                    "current_hp": 15,
                },
            )()

    character_service = RecordingCharacterService()

    applier = CharacterApplier(
        character_service=character_service,
    )

    connection = object()

    operation = ChangeCharacterHpOperation(
        entity_id=7,
        amount=-5,
    )

    result = applier.apply(
        operation,
        conn=connection,
        campaign_id=1,
    )

    assert character_service.calls == [
        (
            7,
            -5,
            1,
            connection,
        )
    ]

    assert isinstance(
        result,
        OperationResult,
    )

    assert result.status == OperationStatus.SUCCESS
    assert result.success is True
    assert result.changed is True

    assert result.operation == operation

    assert result.data == {
        "entity_id": 7,
        "current_hp": 15,
    }

def test_apply_returns_failure_when_character_service_fails():
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )
    from services.character_applier import (
        CharacterApplier,
    )
    from services.character_service import (
        CharacterServiceError,
    )

    class FakeCharacterService:
        def change_hp(self, **kwargs):
            raise CharacterServiceError(
                "character not found",
                status=OperationStatus.NOT_FOUND,
            )

    applier = CharacterApplier(
        FakeCharacterService()
    )

    operation = ChangeCharacterHpOperation(
        entity_id=999,
        amount=-5,
    )
    
    result = applier.apply(
        operation,
        campaign_id=1,
    )

    assert result.success is False
    assert result.operation == operation
    assert result.message == "character not found"
    assert result.data["entity_id"] == 999

def test_apply_returns_failure_when_character_service_fails_with_connection():
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )
    from services.character_applier import (
        CharacterApplier,
    )
    from services.character_service import (
        CharacterServiceError,
    )

    class FakeCharacterService:
        def change_hp(self, **kwargs):
            assert kwargs["conn"] == "fake-connection"

            raise CharacterServiceError(
                "character not found",
                status=OperationStatus.NOT_FOUND,
            )

    applier = CharacterApplier(
        FakeCharacterService()
    )

    operation = ChangeCharacterHpOperation(
        entity_id=999,
        amount=-5,
    )

    result = applier.apply(
        operation,
        conn="fake-connection",
        campaign_id=1,
    )

    assert result.success is False
    assert result.operation == operation
    assert result.message == "character not found"
    assert result.data["entity_id"] == 999