from fastapi import APIRouter, Query

from api.runtime_context import get_current_runtime

router = APIRouter()


@router.get("/memory/search")
def search_memory(
    q: str = Query(..., min_length=1, max_length=1000),
):
    runtime = get_current_runtime()
    with runtime.turn_execution_lock.acquire():
        world = runtime.world_service.get_world()
        return runtime.memory_search_service.search(world, q.strip())


@router.get("/memory/context")
def memory_context(
    q: str = Query(..., min_length=1, max_length=1000),
):
    runtime = get_current_runtime()
    with runtime.turn_execution_lock.acquire():
        world = runtime.world_service.get_world()
        return runtime.context_builder.build(world, q.strip())
