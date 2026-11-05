from fastapi import APIRouter, HTTPException

from api.runtime_context import get_current_runtime
from models.campaign_clock_api_schemas import CampaignClockAdvanceIn
from services.campaign_clock_service import CampaignClockService

router = APIRouter()


# ============================================================
# CAMPAIGN CLOCK
# ============================================================

def _campaign_clock_payload(clock):
    return {
        "campaign_id": clock.campaign_id,
        "elapsed_minutes": clock.elapsed_minutes,
        "version": clock.version,
        "updated_at": clock.updated_at,
    }


@router.get("/campaign/clock")
def get_campaign_clock():
    runtime = get_current_runtime()
    try:
        with runtime.turn_execution_lock.acquire():
            clock = CampaignClockService(
                campaign_id=runtime.campaign_id
            ).get()
        return _campaign_clock_payload(clock)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/campaign/clock/advance")
def advance_campaign_clock(data: CampaignClockAdvanceIn):
    try:
        runtime = get_current_runtime()
        with runtime.turn_execution_lock.acquire():
            clock = CampaignClockService(
                campaign_id=runtime.campaign_id
            ).advance(
                minutes=data.minutes,
                expected_elapsed_minutes=data.expected_elapsed_minutes,
            )
        return _campaign_clock_payload(clock)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
