from copy import deepcopy

from models.world_state import WorldState
from services.context import ContextBuilder
from tests.context_pipeline_test_support import (
    make_complex_world,
    make_relation,
    make_world,
)


def test_pipeline_does_not_mutate_world():
    world = make_complex_world()

    before_entities = dict(
        world.entities
    )
    before_relations = dict(
        world.relations
    )
    before_events = dict(
        getattr(world, "events", {})
    )

    builder = ContextBuilder()

    builder.build(
        world,
        "Fungoso",
    )

    assert world.entities == before_entities
    assert world.relations == before_relations
    assert getattr(world, "events", {}) == before_events

def test_pipeline_does_not_mutate_nested_world_state():
    world = make_complex_world()

    snapshot = deepcopy(world)

    builder = ContextBuilder()

    builder.build(
        world,
        "Fungoso",
    )

    assert world == snapshot


# ============================================================
# DETERMINISM
# ============================================================

def test_pipeline_is_deterministic():
    world = make_complex_world()
    builder = ContextBuilder()

    first = builder.build(
        world,
        "Fungoso",
    )

    second = builder.build(
        world,
        "Fungoso",
    )

    assert first == second

def test_pipeline_entity_order_is_deterministic():
    world = make_complex_world()
    builder = ContextBuilder()

    result = builder.build(
        world,
        "Fungoso",
    )

    first_order = [
        entity["id"]
        for entity in result["entities"]
    ]

    second = builder.build(
        world,
        "Fungoso",
    )

    second_order = [
        entity["id"]
        for entity in second["entities"]
    ]

    assert first_order == second_order


# ============================================================
# NO DATA
# ============================================================

def test_pipeline_world_without_matches_returns_empty_context():
    world = WorldState()
    world.entities = {}
    world.relations = {}
    world.events = {}

    builder = ContextBuilder()

    result = builder.build(
        world,
        "dragón inexistente",
    )

    assert result["entities"] == []
    assert result["relations"] == []
    assert result["events"] == []
    assert result["context"] == (
        "Sin información relevante."
    )


# ============================================================
# RELATION METADATA
# ============================================================

def test_pipeline_relation_reason_is_rendered():
    world = make_world()

    world.relations[1] = make_relation(
        1,
        1,
        2,
        relation_type="friend",
        metadata={
            "reason": "Combatieron juntos durante la guerra.",
        },
    )

    builder = ContextBuilder()

    result = builder.build(
        world,
        "Fungoso",
    )

    assert (
        "Combatieron juntos durante la guerra."
        in result["context"]
    )


# ============================================================
# RESULT ISOLATION
# ============================================================

def test_pipeline_modifying_result_does_not_modify_world():
    world = make_world()
    builder = ContextBuilder()

    result = builder.build(
        world,
        "Fungoso",
    )

    result["entities"][0]["name"] = "MODIFICADO"

    assert any(
        entity.name == "Fungoso"
        for entity in world.entities.values()
    )

def test_pipeline_result_lists_are_independent():
    world = make_world()
    builder = ContextBuilder()

    result = builder.build(
        world,
        "Fungoso",
    )

    entities = result["entities"]

    entities.clear()

    assert world.entities
