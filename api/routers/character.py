import sqlite3
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from models.character_sheet_read_models import CharacterSheetRead
from services.characters.character_sheet_query_service import (
    CharacterSheetQueryService,
)

from api.runtime_context import get_current_runtime
from models.equipment_api_schemas import EquipItemIn, EquipmentSlot
from models.schemas import CharacterCreate

router = APIRouter()


@router.post("/characters")
def create_character(
    data: CharacterCreate,
    activate: bool = True,
):
    runtime = get_current_runtime()
    try:
        with runtime.turn_execution_lock.acquire():
            character = runtime.character_creation_service.create_character(
                campaign_id=runtime.campaign_id,
                data=data,
                activate=activate,
            )
            # Character creation persists its entity outside WorldService.
            # Refresh the runtime cache after the SQLite transaction commits.
            runtime.world_service.load()

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
    runtime = get_current_runtime()
    try:
        with runtime.turn_execution_lock.acquire():
            character = runtime.character_creation_service.create_character(
                campaign_id=runtime.campaign_id,
                data=data,
                activate=True,
            )
            runtime.world_service.load()

        return {
            "campaign_id": runtime.campaign_id,
            "character": character,
            "active_character_id": character.entity_id,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )



@router.get(
    "/characters/{character_entity_id}/sheet",
    response_model=CharacterSheetRead,
)
def get_character_sheet(character_entity_id: int):
    """Return a detached D&D 5e character sheet for this campaign."""
    runtime = get_current_runtime()
    with runtime.turn_execution_lock.acquire():
        sheet = CharacterSheetQueryService(
            runtime.character_repository,
            runtime.entity_repository,
        ).get_sheet(
            character_entity_id,
            campaign_id=runtime.campaign_id,
        )
        if sheet is None:
            raise HTTPException(
                status_code=404,
                detail="character does not exist",
            )
        character = runtime.character_repository.get_character(
            character_entity_id,
            campaign_id=runtime.campaign_id,
        )
        armor = runtime.weapon_equipment_service.armor_class(
            character,
            campaign_id=runtime.campaign_id,
        )
        return sheet.model_copy(update={"armor_class": armor.armor_class})


@router.get("/characters/{character_entity_id}/inventory")
def list_character_inventory(character_entity_id: int):
    runtime = get_current_runtime()
    return {
        "character_entity_id": character_entity_id,
        "items": runtime.weapon_equipment_service.inventory_items(
            campaign_id=runtime.campaign_id,
            character_entity_id=character_entity_id,
        ),
    }


@router.get("/characters/{character_entity_id}/equipment")
def list_character_equipment(character_entity_id: int):
    runtime = get_current_runtime()
    with runtime.turn_execution_lock.acquire():
        character = runtime.character_repository.get_character(
            character_entity_id, campaign_id=runtime.campaign_id
        )
        if character is None:
            raise HTTPException(status_code=404, detail="character does not exist")
        armor = runtime.weapon_equipment_service.armor_class(
            character, campaign_id=runtime.campaign_id
        )
        return {
            "character_entity_id": character_entity_id,
            "items": runtime.weapon_equipment_service.equipped_items(
                campaign_id=runtime.campaign_id,
                character_entity_id=character_entity_id,
            ),
            "armor_class": armor.armor_class,
            "unarmored_defense_applied": armor.unarmored_defense_applied,
            "armor_movement": {
                "strength_requirement_met": armor.strength_requirement_met,
                "speed_penalty_ft": armor.speed_penalty_ft,
            },
            "armor_proficiency": asdict(
                runtime.weapon_equipment_service.armor_proficiency(
                    character, campaign_id=runtime.campaign_id
                )
            ),
        }


@router.post("/characters/{character_entity_id}/equipment", status_code=201)
def equip_character_item(character_entity_id: int, data: EquipItemIn):
    runtime = get_current_runtime()
    try:
        with runtime.turn_execution_lock.acquire():
            runtime.weapon_equipment_service.equip(
                campaign_id=runtime.campaign_id,
                character_entity_id=character_entity_id,
                item_instance_id=data.item_instance_id,
                slot=data.slot,
            )
        return {
            "character_entity_id": character_entity_id,
            "slot": data.slot,
            "item_instance_id": data.item_instance_id,
        }
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/characters/{character_entity_id}/equipment/{slot}")
def unequip_character_slot(character_entity_id: int, slot: EquipmentSlot):
    runtime = get_current_runtime()
    with runtime.turn_execution_lock.acquire():
        runtime.weapon_equipment_service.unequip(
            campaign_id=runtime.campaign_id,
            character_entity_id=character_entity_id,
            slot=slot,
        )
    return {
        "character_entity_id": character_entity_id,
        "slot": slot,
        "unequipped": True,
    }
