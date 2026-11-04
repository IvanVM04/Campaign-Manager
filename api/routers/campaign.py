from fastapi import APIRouter, HTTPException

from api.runtime_context import get_current_runtime
from models.schemas import (
    ActiveCharacterUpdate,
    CampaignCreate,
    CampaignSessionUpdate,
    CampaignUpdate,
    SessionIn,
)
from repositories.campaign_repository import CampaignRepository
from services.campaign_state_service import CampaignStateServiceError

router = APIRouter()


@router.get("/campaigns")
def list_campaigns():
    return CampaignRepository().list_campaigns()


@router.post("/campaigns", status_code=201)
def create_campaign(data: CampaignCreate):
    try:
        return CampaignRepository().create_campaign(
            name=data.name,
            system=data.system,
            tone=data.tone,
            summary=data.summary,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to create campaign",
        ) from exc


@router.patch("/campaign")
def update_campaign(data: CampaignUpdate):
    runtime = get_current_runtime()

    with runtime.turn_execution_lock.acquire():
        current = runtime.campaign_repository.get_campaign(
            runtime.campaign_id
        )

        values = {
            "name": (
                data.name if data.name is not None else current["name"]
            ),
            "system": (
                data.system if data.system is not None else current["system"]
            ),
            "tone": (
                data.tone if data.tone is not None else current["tone"]
            ),
            "summary": (
                data.summary
                if data.summary is not None
                else current["summary"]
            ),
        }

        return runtime.campaign_repository.update_campaign(
            campaign_id=runtime.campaign_id,
            **values,
        )


@router.patch("/campaign/session")
def update_campaign_session(data: CampaignSessionUpdate):
    runtime = get_current_runtime()

    try:
        with runtime.turn_execution_lock.acquire():
            state = runtime.campaign_state_service.set_current_session(
                data.session_id
            )
    except CampaignStateServiceError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to update campaign session",
        ) from exc

    return {
        "campaign_id": state.campaign_id,
        "current_session_id": state.current_session_id,
    }


@router.post("/sessions")
def create_session(data: SessionIn):
    runtime = get_current_runtime()

    with runtime.turn_execution_lock.acquire():
        return runtime.campaign_repository.create_session(
            **data.model_dump(),
            campaign_id=runtime.campaign_id,
        )


@router.get("/campaign/state")
def get_campaign_state():
    runtime = get_current_runtime()

    try:
        state = runtime.campaign_state_service.get_state()
    except CampaignStateServiceError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to retrieve campaign state",
        ) from exc

    return {
        "campaign_id": state.campaign_id,
        "name": state.name,
        "system": state.system,
        "tone": state.tone,
        "current_location_id": state.current_location_id,
        "current_session_id": state.current_session_id,
        "active_character_id": state.active_character_id,
        "summary": state.summary,
    }


@router.patch("/campaign/active-character")
def update_active_character(data: ActiveCharacterUpdate):
    runtime = get_current_runtime()

    try:
        with runtime.turn_execution_lock.acquire():
            state = runtime.campaign_state_service.set_active_character(
                data.character_id
            )
    except CampaignStateServiceError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to update active character",
        ) from exc

    return {
        "campaign_id": state.campaign_id,
        "active_character_id": state.active_character_id,
    }
