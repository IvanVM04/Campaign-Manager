from fastapi import APIRouter, HTTPException

from api.runtime_context import (
    silly_tavern_integration_service,
    turn_execution_lock,
)
from api.serializers import serialize_operation_result
from models.schemas import SillyTavernContextIn, SillyTavernTurnIn
from services.silly_tavern_integration_service import (
    SillyTavernIntegrationServiceConflictError,
    SillyTavernIntegrationServiceError,
)


router = APIRouter()


# ============================================================
# SILLYTAVERN INTEGRATION
# ============================================================


@router.post("/integration/context")
def get_silly_tavern_context(
    data: SillyTavernContextIn,
):
    """
    Devuelve el contexto persistente necesario para que
    SillyTavern genere la siguiente respuesta narrativa.
    """

    try:
        with turn_execution_lock.acquire():
            result = (
                silly_tavern_integration_service
                .get_context(
                    data.query
                )
            )

    except SillyTavernIntegrationServiceError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to build SillyTavern context",
        ) from exc

    return result


@router.get(
    "/integration/turn/{external_turn_id}"
)
def get_silly_tavern_turn_state(
    external_turn_id: str,
):
    """
    Devuelve la versión activa persistida de un turno externo.

    La extensión de SillyTavern utiliza este endpoint para
    reconstruir su caché local después de una recarga o cambio
    de chat.
    """

    try:
        with turn_execution_lock.acquire():
            result = (
                silly_tavern_integration_service
                .get_external_turn_state(
                    external_turn_id
                )
            )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except SillyTavernIntegrationServiceError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "failed to obtain "
                "SillyTavern turn state"
            ),
        ) from exc

    return result


@router.post("/integration/turn")
def process_silly_tavern_turn(
    data: SillyTavernTurnIn,
):
    """
    Procesa una narrativa que ya ha sido generada
    por SillyTavern.

    Campaign Manager:

        narrativa
            ↓
        extracción
            ↓
        operaciones
            ↓
        WorldService
            ↓
        SQLite
    """

    try:
        result = (
            silly_tavern_integration_service
            .process_turn(
                player_input=data.player_input,
                narrative=data.narrative,
                external_turn_id=data.external_turn_id,
                turn_version=data.turn_version,
            )
        )

    except SillyTavernIntegrationServiceConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except SillyTavernIntegrationServiceError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to process SillyTavern turn",
        ) from exc

    return {
        "narrative": result.narrative,
        "player_input": result.player_input,
        "external_turn_id": data.external_turn_id,
        "turn_version": data.turn_version,
        "operation_count": (
            result.operation_count
        ),
        "successful_operation_count": (
            result.successful_operation_count
        ),
        "failed_operation_count": (
            result.failed_operation_count
        ),
        "all_operations_succeeded": (
            result.all_operations_succeeded
        ),
        "world_changed": (
            result.world_changed
        ),
        "operations": [
            type(operation).__name__
            for operation
            in (
                result.operations
                + result.character_operations
            )
        ],
        "operation_results": [
            serialize_operation_result(
                operation_result
            )
            for operation_result
            in result.operation_results
        ],
    }
