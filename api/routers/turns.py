from fastapi import APIRouter, Header, HTTPException, Query

from api.runtime_context import (
    campaign_turn_service,
    get_current_runtime,
    turn_repository,
)
from models.schemas import ManualRollIn, TurnIn

router = APIRouter()


def _serialize_mechanics_result(mechanics_result):
    if mechanics_result is None:
        return None

    decision = mechanics_result.decision
    check = mechanics_result.check
    roll = check.roll
    return {
        "decision": decision.decision.value,
        "skill": decision.skill.value if decision.skill is not None else None,
        "ability": check.ability.value,
        "dc": check.dc,
        "rolls": list(roll.rolls),
        "selected": roll.selected,
        "roll_mode": roll.mode.value,
        "modifier": roll.modifier,
        "total": check.total,
        "success": check.success,
        "reason": decision.reason,
    }


def _serialize_operation_result(result):
    return {
        "status": result.status.value,
        "message": result.message,
        "operation": (
            type(result.operation).__name__
            if result.operation is not None
            else None
        ),
    }


def _turn_result_payload(result):
    return {
        "narrative": result.narrative,
        "player_input": result.player_input,
        "mechanics": _serialize_mechanics_result(
            getattr(result, "mechanics_result", None)
        ),
        "pending_roll_id": getattr(result, "pending_roll_id", None),
        "pending_roll": getattr(result, "pending_roll", None),
        "operation_count": result.operation_count,
        "successful_operation_count": result.successful_operation_count,
        "failed_operation_count": result.failed_operation_count,
        "all_operations_succeeded": result.all_operations_succeeded,
        "world_changed": result.world_changed,
        "operations": [
            type(operation).__name__ for operation in result.operations
        ],
        "operation_results": [
            _serialize_operation_result(item)
            for item in result.operation_results
        ],
    }


@router.post("/turn")
def play_turn(
    data: TurnIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    from services.campaign_turn_service import CampaignTurnServiceError
    from services.durable_native_turn_service import DurableNativeTurnError

    try:
        if data.dice_mode == "automatic":
            result = get_current_runtime().durable_native_turn_service.play_turn(
                data.player_input,
                idempotency_key=idempotency_key,
            )
        else:
            result = campaign_turn_service.play_turn(
                data.player_input,
                dice_mode=data.dice_mode,
            )
    except DurableNativeTurnError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CampaignTurnServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _turn_result_payload(result)


@router.post("/turn/roll")
def submit_manual_roll(data: ManualRollIn):
    from services.campaign_turn_service import CampaignTurnServiceError

    try:
        result = campaign_turn_service.submit_manual_roll(
            data.pending_roll_id,
            tuple(data.rolls),
        )
    except (CampaignTurnServiceError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return _turn_result_payload(result)


@router.get("/turns")
def get_turns(
    session_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
):
    runtime = get_current_runtime()
    turns = turn_repository.list_turns(
        session_id=session_id,
        limit=limit,
        scope=runtime.scope,
    )

    return [
        {
            "id": turn.id,
            "session_id": turn.session_id,
            "player_input": turn.player_input,
            "narrative": turn.narrative,
            "operation_count": turn.operation_count,
            "successful_operation_count": turn.successful_operation_count,
            "failed_operation_count": turn.failed_operation_count,
            "all_operations_succeeded": turn.all_operations_succeeded,
            "world_changed": turn.world_changed,
            "created_at": turn.created_at,
        }
        for turn in turns
    ]
