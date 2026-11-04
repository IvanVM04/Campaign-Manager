from fastapi import APIRouter, Query

from api.runtime_context import (
    context_builder,
    memory_search_service,
    turn_execution_lock,
    world_service,
)

router = APIRouter()


@router.get("/memory/search")
def search_memory(
    q: str = Query(..., min_length=1, max_length=1000),
):
    with turn_execution_lock.acquire():
        world = world_service.get_world()
        return memory_search_service.search(world, q.strip())


@router.get("/memory/context")
def memory_context(
    q: str = Query(..., min_length=1, max_length=1000),
):
    with turn_execution_lock.acquire():
        world = world_service.get_world()
        return context_builder.build(world, q.strip())
