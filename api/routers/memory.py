from fastapi import APIRouter, Query

from api.runtime_context import get_current_runtime

router = APIRouter()


@router.get("/memory/search")
def search_memory(
    q: str = Query(..., min_length=1, max_length=1000),
):
    runtime = get_current_runtime()
    with runtime.turn_execution_lock.acquire():
        turn_context = runtime.campaign_state_service.get_turn_context()
        character_entity_id = (
            turn_context.active_character.entity_id
            if turn_context.active_character is not None
            else None
        )
        return runtime.memory_search_service.search(
            turn_context.world,
            q.strip(),
            character_entity_id=character_entity_id,
        )


@router.get("/memory/context")
def memory_context(
    q: str = Query(..., min_length=1, max_length=1000),
):
    runtime = get_current_runtime()
    with runtime.turn_execution_lock.acquire():
        turn_context = runtime.campaign_state_service.get_turn_context()
        character_entity_id = (
            turn_context.active_character.entity_id
            if turn_context.active_character is not None
            else None
        )
        return runtime.context_builder.build(
            turn_context.world,
            q.strip(),
            character_entity_id=character_entity_id,
        )
