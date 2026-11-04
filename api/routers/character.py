import sqlite3
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from api.runtime_context import (
    character_creation_service,
    get_current_runtime,
)
from models.equipment_api_schemas import EquipItemIn, EquipmentSlot
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
