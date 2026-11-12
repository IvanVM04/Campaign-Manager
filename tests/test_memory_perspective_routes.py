from contextlib import nullcontext
from types import SimpleNamespace

from api.routers import memory, world as world_router
from models.entity import Entity
from models.event import Event
from models.world_state import WorldState


class _Lock:
    def acquire(self):
        return nullcontext()


def _runtime(monkeypatch):
    world = object()
    turn_context = SimpleNamespace(
        world=world,
        active_character=SimpleNamespace(entity_id=73),
    )
    calls = {}
    runtime = SimpleNamespace(
        turn_execution_lock=_Lock(),
        campaign_state_service=SimpleNamespace(
            get_turn_context=lambda: turn_context,
        ),
        memory_search_service=SimpleNamespace(
            search=lambda supplied_world, query, **kwargs: calls.update({
                "search_world": supplied_world,
                "search_query": query,
                "search_perspective": kwargs.get("character_entity_id"),
            }) or {"events": []},
        ),
        context_builder=SimpleNamespace(
            build=lambda supplied_world, query, **kwargs: calls.update({
                "context_world": supplied_world,
                "context_query": query,
                "context_perspective": kwargs.get("character_entity_id"),
            }) or {"events": [], "context": "filtered"},
        ),
    )
    monkeypatch.setattr(memory, "get_current_runtime", lambda: runtime)
    return calls, world


def test_memory_search_endpoint_uses_server_side_active_character(monkeypatch):
    calls, world = _runtime(monkeypatch)

    result = memory.search_memory(q="  la carta  ")

    assert result == {"events": []}
    assert calls["search_world"] is world
    assert calls["search_query"] == "la carta"
    assert calls["search_perspective"] == 73


def test_memory_context_endpoint_uses_server_side_active_character(monkeypatch):
    calls, world = _runtime(monkeypatch)

    result = memory.memory_context(q="  la carta  ")

    assert result == {"events": [], "context": "filtered"}
    assert calls["context_world"] is world
    assert calls["context_query"] == "la carta"
    assert calls["context_perspective"] == 73



def test_full_world_endpoint_filters_event_perspective_and_marks_history(monkeypatch):
    world = WorldState(
        entities={
            9: Entity(id=9, name="Aldric", entity_type="npc"),
        },
        events={
            "private-active": Event(
                id="private-active",
                event_type="clue",
                title="Aldric mentioned the hidden stair",
                visibility_scope="character",
                known_by_entity_ids=[73, 88],
                provenance_source="npc_statement",
                source_entity_id=9,
            ),
            "private-other": Event(
                id="private-other",
                event_type="clue",
                title="Neria found the secret chapel",
                visibility_scope="character",
                known_by_entity_ids=[88],
            ),
            "old-location": Event(
                id="old-location",
                event_type="location",
                title="Aldric lived in the inn",
            ),
            "new-location": Event(
                id="new-location",
                event_type="location",
                title="Aldric moved to the tower",
                supersedes_event_id="old-location",
            ),
            "gm-secret": Event(
                id="gm-secret",
                event_type="secret",
                title="The GM's hidden truth",
                secret=True,
            ),
        },
    )
    turn_context = SimpleNamespace(
        world=world,
        active_character=SimpleNamespace(entity_id=73),
    )
    runtime = SimpleNamespace(
        turn_execution_lock=_Lock(),
        campaign_state_service=SimpleNamespace(
            get_turn_context=lambda: turn_context,
        ),
    )
    monkeypatch.setattr(
        world_router,
        "get_current_runtime",
        lambda: runtime,
    )

    result = world_router.get_world()

    event_map = {event["id"]: event for event in result["events"]}
    assert set(event_map) == {
        "private-active",
        "old-location",
        "new-location",
    }
    assert event_map["private-active"]["source_entity_name"] == "Aldric"
    assert "known_by_entity_ids" not in event_map["private-active"]
    assert event_map["old-location"]["is_current"] is False
    assert event_map["new-location"]["is_current"] is True
