
from models.operation_result import (
    OperationResult,
    OperationStatus,
)
from operations.character_operations import (
    ChangeCharacterHpOperation,
)
from services.character_service import (
    CharacterService,
    CharacterServiceError,
)


class CharacterApplierError(Exception):
    pass


class CharacterApplier:

    def __init__(
        self,
        character_service: CharacterService,
    ):
        self.character_service = character_service

    def apply(
        self,
        operation,
        *,
        campaign_id: int,
        conn=None,
    ) -> OperationResult:

        if isinstance(
            operation,
            ChangeCharacterHpOperation,
        ):
            try:
                character = self.character_service.change_hp(
                    entity_id=operation.entity_id,
                    amount=operation.amount,
                    campaign_id=campaign_id,
                    conn=conn,
                )

            except CharacterServiceError as exc:
                return OperationResult(
                    status=exc.status,
                    message=str(exc),
                    operation=operation,
                    data={
                        "entity_id": operation.entity_id,
                    },
                )

            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Character HP changed",
                operation=operation,
                data={
                    "entity_id": operation.entity_id,
                    "current_hp": character.current_hp,
                },
            )

        raise CharacterApplierError(
            f"unsupported character operation: "
            f"{type(operation).__name__}"
        )
