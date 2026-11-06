from fastapi import APIRouter, HTTPException, Query

from api.runtime_context import (
    get_current_runtime,
    memory_search_service,
    turn_execution_lock,
    world_service,
)
from models.schemas import WorldBootstrapIn
from models.world_read_models import WorldEntityPage
from operations.world_operations import CreateEntityOperation
from services.world import WorldQueryService

router = APIRouter()


# ============================================================
# WORLD
# ============================================================

@router.get("/world")
def get_world():

    with turn_execution_lock.acquire():

        world = world_service.get_world()

        return {
            "entities": list(
                world.entities.values()
            ),
            "items": list(
                world.items.values()
            ),
            "item_instances": list(
                world.item_instances.values()
            ),
            "resources": list(
                world.resources.values()
            ),
            "resource_balances": list(
                world.resource_balances.values()
            ),
            "relations": list(
                world.relations.values()
            ),
            "events": list(
                world.events.values()
            ),
        }


@router.get("/world/entities", response_model=WorldEntityPage)
def list_world_entities(
    q: str | None = Query(default=None, max_length=200),
    entity_type: str | None = Query(default=None, max_length=50),
    active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Return a stable, immutable and paginated entity read model."""
    runtime = get_current_runtime()

    with runtime.turn_execution_lock.acquire():
        return WorldQueryService().list_entities(
            runtime.world_service.get_world(),
            query=q,
            entity_type=entity_type,
            active=active,
            limit=limit,
            offset=offset,
        )


@router.post("/world/entities/bootstrap")
def bootstrap_world_entities(data: WorldBootstrapIn):
    """Create missing baseline entities in one atomic, idempotent operation."""
    runtime = get_current_runtime()

    with runtime.turn_execution_lock.acquire():
        world = runtime.world_service.get_world()
        existing_by_name = {
            entity.name.strip().casefold(): entity
            for entity in world.entities.values()
        }
        missing = [
            entity for entity in data.entities
            if entity.name.casefold() not in existing_by_name
        ]

        if missing:
            operations = [
                CreateEntityOperation(
                    name=entity.name,
                    entity_type=entity.entity_type,
                    description=entity.description,
                    notes=entity.notes,
                )
                for entity in missing
            ]
            try:
                result = runtime.world_service.apply_operations_and_save(
                    operations
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail="failed to bootstrap world entities",
                ) from exc

            if not result.success:
                raise HTTPException(
                    status_code=409,
                    detail="world entity bootstrap could not be applied atomically",
                )

            world = runtime.world_service.get_world()

        entities_by_name = {
            entity.name.strip().casefold(): entity
            for entity in world.entities.values()
        }
        return {
            "created": [
                entities_by_name[entity.name.casefold()].id
                for entity in missing
            ],
            "entities": [
                {
                    "id": entities_by_name[entity.name.casefold()].id,
                    "name": entities_by_name[entity.name.casefold()].name,
                    "entity_type": entities_by_name[entity.name.casefold()].entity_type,
                }
                for entity in data.entities
            ],
        }

# ============================================================
# EXPORT
# ============================================================


@router.get("/export")
def export_memory():
    """
    Exporta la representación pública actual de la campaña.

    WorldState es la fuente de verdad y MemorySearchService
    es responsable de aplicar las reglas de visibilidad y
    construir la representación estructurada exportable.
    """

    with turn_execution_lock.acquire():

        world = world_service.get_world()

        return memory_search_service.export(world)
