from fastapi import APIRouter, HTTPException, Path, Query

from api.runtime_context import get_current_runtime
from models.schemas import (
    ActiveCharacterUpdate,
    CampaignCreate,
    CampaignSessionUpdate,
    CampaignUpdate,
    SessionIn,
)
from models.session_read_models import SessionPage, SessionRead
from repositories.campaign_repository import CampaignRepository
from services.campaign import CampaignStateServiceError

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


def _session_read(row) -> SessionRead:
    return SessionRead(
        id=row["id"],
        number=row["number"],
        title=row["title"] or "",
        summary=row["summary"] or "",
        start_location=row["start_location"] or "",
        end_location=row["end_location"] or "",
        turn_count=row["turn_count"],
        last_turn_at=row["last_turn_at"],
    )


@router.get("/sessions")
def list_sessions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    runtime = get_current_runtime()
    repository = runtime.campaign_repository
    session_rows = repository.list_sessions(
        campaign_id=runtime.campaign_id,
        limit=limit,
        offset=offset,
    )
    return SessionPage(
        items=tuple(_session_read(row) for row in session_rows),
        total=repository.count_sessions(campaign_id=runtime.campaign_id),
        limit=limit,
        offset=offset,
    )


@router.get("/sessions/{session_id}")
def get_session(session_id: int = Path(ge=1)):
    runtime = get_current_runtime()
    row = runtime.campaign_repository.get_session_overview(
        session_id,
        campaign_id=runtime.campaign_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _session_read(row)


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
