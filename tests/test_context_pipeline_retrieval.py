import pytest

from models.event import Event
from models.item import Item, ItemInstance
from models.resource import Resource, ResourceBalance
from services.context import ContextBuilder
from tests.context_pipeline_test_support import (
    make_complex_world,
    make_relation,
    make_world,
)


def test_pipeline_direct_entity_appears_in_context():
    builder = ContextBuilder()
    world = make_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    assert result["query"] == "Fungoso"
    assert result["entities"]

    names = {
        entity["name"]
        for entity in result["entities"]
    }

    assert "Fungoso" in names
    assert "Fungoso" in result["context"]

def test_pipeline_related_entity_appears_in_context():
    builder = ContextBuilder()
    world = make_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    names = {
        entity["name"]
        for entity in result["entities"]
    }

    assert "Fungoso" in names
    assert "Aldric" in names

def test_pipeline_query_matching_is_case_insensitive():
    builder = ContextBuilder()
    world = make_world()

    result = builder.build(
        world,
        "fungoso",
    )

    assert result["query"] == "fungoso"
    assert "Fungoso" in result["context"]

def test_pipeline_query_is_stripped():
    builder = ContextBuilder()
    world = make_world()

    result = builder.build(
        world,
        "   Fungoso   ",
    )

    assert result["query"] == "Fungoso"


# ============================================================
# EMPTY / INVALID QUERY
# ============================================================

def test_pipeline_empty_query_returns_empty_result():
    builder = ContextBuilder()
    world = make_world()

    result = builder.build(
        world,
        "   ",
    )

    assert result["query"] == ""
    assert result["entities"] == []
    assert result["relations"] == []
    assert result["events"] == []
    assert result["context"] == (
        "Sin información relevante."
    )

def test_pipeline_none_query_raises():
    builder = ContextBuilder()
    world = make_world()

    with pytest.raises(TypeError):
        builder.build(
            world,
            None,
        )

def test_pipeline_invalid_world_raises():
    builder = ContextBuilder()

    with pytest.raises(TypeError):
        builder.build(
            {},
            "Fungoso",
        )


# ============================================================
# RELATION EXPANSION
# ============================================================

def test_pipeline_strong_relation_is_more_relevant_than_weak_relation():
    builder = ContextBuilder()
    world = make_complex_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    relevance_order = [
        entity["name"]
        for entity in result["entities"]
    ]

    assert "Aldric" in relevance_order
    assert "Morth" in relevance_order

    assert relevance_order.index(
        "Aldric"
    ) < relevance_order.index(
        "Morth"
    )

def test_pipeline_enemy_relation_is_included():
    builder = ContextBuilder()
    world = make_complex_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    names = {
        entity["name"]
        for entity in result["entities"]
    }

    assert "Morth" in names

def test_pipeline_inactive_relation_does_not_expand():
    builder = ContextBuilder()
    world = make_complex_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    names = {
        entity["name"]
        for entity in result["entities"]
    }

    assert "Fantasma" not in names

def test_pipeline_inactive_entity_is_excluded():
    builder = ContextBuilder()
    world = make_complex_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    names = {
        entity["name"]
        for entity in result["entities"]
    }

    assert "Inactivo" not in names

def test_pipeline_max_depth_one_does_not_include_second_degree_entity():
    builder = ContextBuilder()
    world = make_complex_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    names = {
        entity["name"]
        for entity in result["entities"]
    }

    # Fungoso -> Aldric -> Vera
    #
    # DEFAULT_MAX_DEPTH = 1
    #
    # Vera no debería entrar por esa segunda relación.
    assert "Vera" not in names


# ============================================================
# RELATIONS
# ============================================================

def test_pipeline_returns_relations_connected_to_entities():
    builder = ContextBuilder()
    world = make_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    assert result["relations"]

    relation_types = {
        relation["relation_type"]
        for relation in result["relations"]
    }

    assert "friend" in relation_types

def test_pipeline_inactive_relations_are_excluded():
    builder = ContextBuilder()
    world = make_complex_world()

    result = builder.build(
        world,
        "Fungoso",
    )

    relation_ids = {
        relation["id"]
        for relation in result["relations"]
    }

    assert 5 not in relation_ids

def test_pipeline_unrelated_relation_is_not_included():
    builder = ContextBuilder()
    world = make_complex_world()

    world.relations[99] = make_relation(
        99,
        4,
        5,
        relation_type="knows",
    )

    result = builder.build(
        world,
        "Fungoso",
    )

    relation_ids = {
        relation["id"]
        for relation in result["relations"]
    }

    assert 99 not in relation_ids


# ============================================================
# EVENTS
# ============================================================

def test_pipeline_related_public_event_is_included():
    builder = ContextBuilder()
    world = make_world()

    world.events = {
        "event-1": Event(
            id="event-1",
            event_type="arrival",
            title="Llegada a la ciudad",
            description="Fungoso llega a la ciudad.",
            consequences="Comienza la aventura.",
            secret=False,
            metadata={
                "entity_ids": [1],
            },
        ),
    }

    result = builder.build(
        world,
        "Fungoso",
    )

    assert result["events"]

    titles = {
        event["title"]
        for event in result["events"]
    }

    assert "Llegada a la ciudad" in titles

def test_pipeline_secret_event_is_never_included():
    builder = ContextBuilder()
    world = make_world()

    world.events = {
        "event-1": Event(
            id="event-1",
            event_type="secret",
            title="El secreto del rey",
            description="Información secreta.",
            consequences="Algo terrible.",
            secret=True,
            metadata={
                "entity_ids": [1],
            },
        ),
    }

    result = builder.build(
        world,
        "Fungoso",
    )

    assert result["events"] == []
    assert "El secreto del rey" not in result["context"]

def test_pipeline_event_without_entity_relationship_is_not_included():
    builder = ContextBuilder()
    world = make_world()

    world.events = {
        "event-1": Event(
            id="event-1",
            event_type="distant",
            title="Evento lejano",
            description="No tiene relación.",
            consequences="Nada.",
            secret=False,
            metadata={
                "entity_ids": [999],
            },
        ),
    }

    result = builder.build(
        world,
        "Fungoso",
    )

    assert result["events"] == []


# ============================================================
# PARENT OBJECT RESOLUTION
# ============================================================

def test_pipeline_item_instance_resolves_parent_item():
    builder = ContextBuilder()
    world = make_world()

    world.items = {
        10: Item(
            id=10,
            name="Espada de Vor",
            description="Una espada antigua.",
            significance="Importante",
            notes="",
        ),
    }

    world.item_instances = {
        100: ItemInstance(
            id=100,
            item_id=10,
            owner_id=1,
            location_id=None,
        ),
    }

    result = builder.build(
        world,
        "Espada de Vor",
    )

    item_ids = {
        item["id"]
        for item in result["items"]
    }

    assert 10 in item_ids

def test_pipeline_item_instance_parent_is_not_duplicated():
    builder = ContextBuilder()
    world = make_world()

    world.items = {
        10: Item(
            id=10,
            name="Espada de Vor",
            description="Una espada antigua.",
            significance="Importante",
            notes="",
        ),
    }

    world.item_instances = {
        100: ItemInstance(
            id=100,
            item_id=10,
            owner_id=1,
            location_id=None,
        ),
    }

    result = builder.build(
        world,
        "Espada",
    )

    item_ids = [
        item["id"]
        for item in result["items"]
    ]

    assert item_ids.count(10) == 1

def test_pipeline_resource_balance_resolves_parent_resource():
    builder = ContextBuilder()
    world = make_world()

    world.resources = {
        20: Resource(
            id=20,
            name="Oro",
            resource_type="currency",
            unit="gp",
            notes="",
        ),
    }

    world.resource_balances = {
        200: ResourceBalance(
            id=200,
            resource_id=20,
            owner_id=1,
            amount=100,
        ),
    }

    result = builder.build(
        world,
        "Oro",
    )

    resource_ids = {
        resource["id"]
        for resource in result["resources"]
    }

    assert 20 in resource_ids


# ============================================================
# CONTEXT BUDGET
# ============================================================


def test_pipeline_merges_supplemental_queries_without_losing_primary_intent():
    builder = ContextBuilder()
    world = make_complex_world()

    result = builder.build(
        world,
        "Fungoso",
        supplemental_queries=("Vera", "Vera"),
    )

    names = {entity["name"] for entity in result["entities"]}
    assert result["query"] == "Fungoso"
    assert "Fungoso" in names
    assert "Vera" in names
    assert len([entity for entity in result["entities"] if entity["name"] == "Vera"]) == 1


def test_pipeline_rejects_non_string_supplemental_query_values():
    builder = ContextBuilder()
    with pytest.raises(TypeError, match="supplemental_queries"):
        builder.build(make_world(), "Fungoso", supplemental_queries=("Aldric", 7))


def test_memory_search_many_preserves_primary_precedence_and_deduplicates():
    from services.context.memory_search_service import MemorySearchService

    world = make_complex_world()
    result = MemorySearchService().search_many(
        world,
        ("Fungoso", "Vera", " fungoso "),
    )
    entity_ids = [entity["id"] for entity in result["entities"]]
    assert entity_ids[0] == 1
    assert len(entity_ids) == len(set(entity_ids))
    assert 4 in entity_ids
