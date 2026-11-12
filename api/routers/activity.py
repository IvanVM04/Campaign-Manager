from __future__ import annotations

from fastapi import APIRouter, Query

from api.runtime_context import get_current_runtime
from models.activity_read_models import ActivityEventPage, ActivityEventType

router = APIRouter()


@router.get("/activity", response_model=ActivityEventPage)
def list_campaign_activity(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    resolution_id: int | None = Query(default=None, ge=1),
    session_id: int | None = Query(default=None, ge=1),
    event_type: ActivityEventType | None = Query(default=None),
) -> ActivityEventPage:
    """Return a safe, paginated activity timeline for the selected campaign."""
    runtime = get_current_runtime()
    return runtime.campaign_activity_service.list_activity(
        limit=limit,
        offset=offset,
        resolution_id=resolution_id,
        session_id=session_id,
        event_type=event_type,
    )
