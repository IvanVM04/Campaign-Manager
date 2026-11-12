from contextlib import nullcontext
from types import SimpleNamespace

from api.routers import memory


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
