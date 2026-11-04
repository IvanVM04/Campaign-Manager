from fastapi import APIRouter, HTTPException

from api.runtime_context import (
    get_current_runtime,
    silly_tavern_integration_service,
    turn_execution_lock,
)
from api.serializers import serialize_operation_result
from models.schemas import (
    SillyTavernClarificationIn,
    SillyTavernContextIn,
    SillyTavernManualRollIn,
    SillyTavernTurnIn,
    SillyTavernTurnResolveIn,
)
from services.durable_native_turn_service import DurableNativeTurnError
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


@router.get("/integration/turn/{external_turn_id}/clarification")
def get_silly_tavern_clarification_state(external_turn_id: str):
    """Recover a pending or recently accepted clarification after client restart."""
    runtime = get_current_runtime()
    try:
        with runtime.turn_execution_lock.acquire():
            return runtime.durable_native_turn_service.get_external_clarification_state(
                external_turn_id
            )
    except DurableNativeTurnError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to obtain SillyTavern clarification state",
        ) from exc


@router.post("/integration/turn/resolve")
def resolve_silly_tavern_turn(data: SillyTavernTurnResolveIn):
    """Commit a SillyTavern turn's consequences before external narration begins."""
    runtime = get_current_runtime()
    try:
        with runtime.turn_execution_lock.acquire():
            preparation = runtime.durable_native_turn_service.prepare_external_turn(
                data.player_input,
                external_turn_id=data.external_turn_id,
                dice_mode=data.dice_mode,
            )
            context_result = runtime.silly_tavern_integration_service.get_context(
                data.query,
                exclude_external_turn_id=data.external_turn_id,
            )
    except DurableNativeTurnError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SillyTavernIntegrationServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to resolve SillyTavern turn before narration",
        ) from exc

    return {
        "external_turn_id": data.external_turn_id,
        "resolution_id": preparation.resolution_id,
        "lifecycle_state": preparation.lifecycle_state,
        "committed_resolution": preparation.committed_resolution,
        "clarification_question": preparation.clarification_question,
        "pending_clarification_id": getattr(
            preparation, "pending_clarification_id", None
        ),
        "pending_roll_id": getattr(preparation, "pending_roll_id", None),
        "pending_roll": getattr(preparation, "pending_roll", None),
        "legacy_replay": preparation.legacy_replay,
        "campaign": context_result["campaign"],
        "session": context_result["session"],
        "active_character": context_result["active_character"],
        "context": context_result["context"],
    }


@router.get("/integration/turn/{external_turn_id}/manual-roll")
def get_silly_tavern_manual_roll_state(external_turn_id: str):
    runtime = get_current_runtime()
    try:
        with runtime.turn_execution_lock.acquire():
            return runtime.durable_native_turn_service.get_external_manual_roll_state(external_turn_id)
    except DurableNativeTurnError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/integration/turn/roll")
def submit_silly_tavern_manual_roll(data: SillyTavernManualRollIn):
    runtime = get_current_runtime()
    try:
        with runtime.turn_execution_lock.acquire():
            preparation = runtime.durable_native_turn_service.submit_manual_roll(
                data.pending_roll_id, tuple(data.rolls),
                adapter_namespace="sillytavern", defer_narration=True,
                answer_external_turn_id=data.answer_external_turn_id,
            )
            context_result = runtime.silly_tavern_integration_service.get_context(data.query)
    except DurableNativeTurnError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SillyTavernIntegrationServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to submit SillyTavern manual roll") from exc
    return {
        "resolution_id": preparation.resolution_id,
        "lifecycle_state": preparation.lifecycle_state,
        "committed_resolution": preparation.committed_resolution,
        "pending_roll_id": preparation.pending_roll_id,
        "pending_roll": preparation.pending_roll,
        "campaign": context_result["campaign"],
        "session": context_result["session"],
        "active_character": context_result["active_character"],
        "context": context_result["context"],
    }


@router.post("/integration/turn/clarification")
def submit_silly_tavern_clarification(data: SillyTavernClarificationIn):
    runtime = get_current_runtime()
    try:
        with runtime.turn_execution_lock.acquire():
            preparation = runtime.durable_native_turn_service.submit_clarification(
                data.pending_clarification_id,
                data.answer,
                adapter_namespace="sillytavern",
                defer_narration=True,
                answer_external_turn_id=data.answer_external_turn_id,
            )
            context_result = runtime.silly_tavern_integration_service.get_context(
                data.query,
            )
    except DurableNativeTurnError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SillyTavernIntegrationServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to resume SillyTavern turn clarification",
        ) from exc

    return {
        "resolution_id": preparation.resolution_id,
        "lifecycle_state": preparation.lifecycle_state,
        "committed_resolution": preparation.committed_resolution,
        "clarification_question": preparation.clarification_question,
        "pending_clarification_id": preparation.pending_clarification_id,
        "pending_roll_id": getattr(preparation, "pending_roll_id", None),
        "pending_roll": getattr(preparation, "pending_roll", None),
        "campaign": context_result["campaign"],
        "session": context_result["session"],
        "active_character": context_result["active_character"],
        "context": context_result["context"],
    }


@router.post("/integration/turn")
def process_silly_tavern_turn(data: SillyTavernTurnIn):
    """Compatibility endpoint for pre-PR31 SillyTavern extensions.

    New clients must resolve consequences before generation and use
    /integration/turn/complete only to persist the resulting narration.
    """
    try:
        result = silly_tavern_integration_service.process_turn(
            player_input=data.player_input,
            narrative=data.narrative,
            external_turn_id=data.external_turn_id,
            turn_version=data.turn_version,
        )
    except SillyTavernIntegrationServiceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SillyTavernIntegrationServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to process legacy SillyTavern turn",
        ) from exc

    return {
        "narrative": result.narrative,
        "player_input": result.player_input,
        "external_turn_id": data.external_turn_id,
        "turn_version": data.turn_version,
        "operation_count": result.operation_count,
        "successful_operation_count": result.successful_operation_count,
        "failed_operation_count": result.failed_operation_count,
        "all_operations_succeeded": result.all_operations_succeeded,
        "world_changed": result.world_changed,
        "operations": [
            type(operation).__name__
            for operation in result.operations + result.character_operations
        ],
        "operation_results": [
            serialize_operation_result(item)
            for item in result.operation_results
        ],
    }


@router.post("/integration/turn/complete")
def complete_silly_tavern_turn(data: SillyTavernTurnIn):
    """Persist an external narrative against an already committed resolution."""
    runtime = get_current_runtime()
    try:
        result = runtime.durable_native_turn_service.complete_external_narration(
            external_turn_id=data.external_turn_id or "",
            player_input=data.player_input,
            narrative=data.narrative,
            turn_version=data.turn_version,
        )
    except DurableNativeTurnError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to persist SillyTavern narration",
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
