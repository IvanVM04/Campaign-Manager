from fastapi import APIRouter, HTTPException

from api.runtime_context import (
    character_creation_service,
    get_current_runtime,
)
from models.schemas import CharacterCreate

router = APIRouter()


@router.post("/characters")
def create_character(
    data: CharacterCreate,
    activate: bool = True,
):
    try:
        character = character_creation_service.create_character(
            campaign_id=get_current_runtime().campaign_id,
            data=data,
            activate=activate,
        )

        return {
            "character": character,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

@router.post("/campaign/bootstrap")
def bootstrap_campaign(
    data: CharacterCreate,
):
    try:
        character = character_creation_service.create_character(
            campaign_id=get_current_runtime().campaign_id,
            data=data,
            activate=True,
        )

        return {
            "campaign_id": get_current_runtime().campaign_id,
            "character": character,
            "active_character_id": character.entity_id,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
