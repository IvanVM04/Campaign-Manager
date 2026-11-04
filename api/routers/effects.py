from fastapi import APIRouter, HTTPException

from api.runtime_context import get_current_runtime, turn_execution_lock
from models.persistent_effect_api_schemas import (
    PersistentEffectCreateIn,
    PersistentEffectStatusIn,
)


router = APIRouter()


# ============================================================
# PERSISTENT CAMPAIGN EFFECTS
# ============================================================


def _persistent_effect_payload(effect):
    return {
        "id": effect.id,
        "campaign_id": effect.campaign_id,
        "entity_id": effect.entity_id,
        "effect_type": effect.effect_type.value,
        "effect_key": effect.effect_key,
        "name": effect.name,
        "description": effect.description,
        "source_type": effect.source_type.value,
        "source_entity_id": effect.source_entity_id,
        "source_reference": effect.source_reference,
        "duration_type": effect.duration_type.value,
        "duration_condition": effect.duration_condition,
        "duration_minutes": effect.duration_minutes,
        "expires_at_minute": effect.expires_at_minute,
        "expired_at_minute": effect.expired_at_minute,
        "level": effect.level,
        "status": effect.status.value,
        "created_at": effect.created_at,
        "updated_at": effect.updated_at,
        "removed_at": effect.removed_at,
    }


@router.get("/entities/{entity_id}/effects")
def list_entity_effects(
    entity_id: int,
    include_removed: bool = False,
):
    try:
        effects = get_current_runtime().persistent_effect_service.list_for_entity(
            entity_id,
            include_removed=include_removed,
        )
        return [_persistent_effect_payload(effect) for effect in effects]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/entities/{entity_id}/effects", status_code=201)
def create_entity_effect(entity_id: int, data: PersistentEffectCreateIn):
    try:
        with turn_execution_lock.acquire():
            effect = get_current_runtime().persistent_effect_service.create(
                entity_id=entity_id,
                effect_type=data.effect_type,
                effect_key=data.effect_key,
                name=data.name,
                description=data.description,
                source_type=data.source_type,
                source_entity_id=data.source_entity_id,
                source_reference=data.source_reference,
                duration_type=data.duration_type,
                duration_condition=data.duration_condition,
                duration_minutes=data.duration_minutes,
                level=data.level,
            )
        return _persistent_effect_payload(effect)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/effects/{effect_id}/status")
def update_persistent_effect_status(
    effect_id: str,
    data: PersistentEffectStatusIn,
):
    try:
        with turn_execution_lock.acquire():
            effect = get_current_runtime().persistent_effect_service.set_status(
                effect_id,
                data.status,
            )
        return _persistent_effect_payload(effect)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/effects/{effect_id}")
def remove_persistent_effect(effect_id: str):
    try:
        with turn_execution_lock.acquire():
            effect = get_current_runtime().persistent_effect_service.remove(
                effect_id
            )
        return _persistent_effect_payload(effect)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
