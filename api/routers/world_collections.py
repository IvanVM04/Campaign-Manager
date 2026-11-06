from fastapi import APIRouter, Query

from api.runtime_context import get_current_runtime
from services.world import WorldCollectionQueryService

router = APIRouter()
_query_service = WorldCollectionQueryService()


def _list(
    collection: str,
    q: str | None,
    active: bool | None,
    limit: int,
    offset: int,
):
    runtime = get_current_runtime()
    with runtime.turn_execution_lock.acquire():
        return _query_service.list_collection(
            runtime.world_service.get_world(),
            collection,
            query=q,
            active=active,
            limit=limit,
            offset=offset,
        )


@router.get("/world/items")
def list_world_items(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return _list("items", q, None, limit, offset)


@router.get("/world/item-instances")
def list_world_item_instances(
    q: str | None = Query(default=None, max_length=200),
    active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return _list("item-instances", q, active, limit, offset)


@router.get("/world/resources")
def list_world_resources(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return _list("resources", q, None, limit, offset)


@router.get("/world/resource-balances")
def list_world_resource_balances(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return _list("resource-balances", q, None, limit, offset)


@router.get("/world/relations")
def list_world_relations(
    q: str | None = Query(default=None, max_length=200),
    active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return _list("relations", q, active, limit, offset)


@router.get("/world/events")
def list_world_events(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return _list("events", q, None, limit, offset)
