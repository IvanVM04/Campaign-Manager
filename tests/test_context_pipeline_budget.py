from context_pipeline_test_support import (
    make_complex_world,
    make_entity,
    make_world,
)

from models.world_state import WorldState
from services.context import ContextBuilder


def test_pipeline_context_never_exceeds_budget():
    builder = ContextBuilder(
        max_context_chars=250,
    )

    world = make_complex_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    assert len(result["context"]) <= 250

def test_pipeline_context_budget_is_respected_with_large_descriptions():
    world = WorldState()

    world.entities = {
        1: make_entity(
            1,
            "Fungoso",
            description="X" * 1000,
        ),
        2: make_entity(
            2,
            "Aldric",
            description="Y" * 1000,
        ),
    }

    world.relations = {}

    builder = ContextBuilder(
        max_context_chars=100,
    )

    result = builder.build(
        world,
        "Fungoso",
    )

    assert len(result["context"]) <= 100

def test_pipeline_oversized_candidate_does_not_corrupt_context():
    builder = ContextBuilder(
        max_context_chars=150,
    )

    world = WorldState()

    world.entities = {
        1: make_entity(
            1,
            "A" * 1000,
        ),
        2: make_entity(
            2,
            "Fungoso",
        ),
    }

    world.relations = {}

    result = builder.build(
        world,
        "Fungoso",
    )

    assert "Fungoso" in result["context"]
    assert "A" * 1000 not in result["context"]


# ============================================================
# PUBLIC CONTRACT
# ============================================================

def test_pipeline_internal_relevance_is_not_public():
    builder = ContextBuilder()
    world = make_complex_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    for entity in result["entities"]:
        assert "_relevance" not in entity
        assert "_depth" not in entity

def test_pipeline_internal_relevance_is_not_in_text():
    builder = ContextBuilder()
    world = make_complex_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    assert "_relevance" not in result["context"]
    assert "_depth" not in result["context"]

def test_pipeline_public_result_has_expected_categories():
    builder = ContextBuilder()
    world = make_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    expected = {
        "query",
        "entities",
        "items",
        "item_instances",
        "resources",
        "resource_balances",
        "relations",
        "events",
        "context",
    }

    assert expected.issubset(
        result.keys()
    )


# ============================================================
# WORLD IMMUTABILITY
# ============================================================
