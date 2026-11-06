from __future__ import annotations

from copy import deepcopy

import pytest

from models.entity import Entity
from models.event import Event
from models.item import Item, ItemInstance
from models.relation import Relation
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState
from services.context import ContextBuilder

# ============================================================
# HELPERS
# ============================================================


def make_entity(
    entity_id: int,
    name: str,
    entity_type: str = "character",
    description: str = "",
    active: bool = True,
) -> Entity:
    return Entity(
        id=entity_id,
        name=name,
        entity_type=entity_type,
        description=description,
        active=active,
    )


def make_relation(
    relation_id: int,
    subject_id: int,
    target_id: int,
    relation_type: str = "knows",
    active: bool = True,
    metadata: dict | None = None,
) -> Relation:
    return Relation(
        id=relation_id,
        subject_id=subject_id,
        target_id=target_id,
        relation_type=relation_type,
        active=active,
        metadata=metadata or {},
    )


def make_world() -> WorldState:
    world = WorldState()

    world.entities = {
        1: make_entity(
            1,
            "Fungoso",
            description="Un aventurero solitario.",
        ),
        2: make_entity(
            2,
            "Aldric",
            entity_type="npc",
            description="Un viejo mercader.",
        ),
    }

    world.relations = {
        1: make_relation(
            1,
            1,
            2,
            relation_type="friend",
        ),
    }

    return world


def make_complex_world() -> WorldState:
    world = WorldState()

    world.entities = {
        1: make_entity(
            1,
            "Fungoso",
            description="Aventurero protagonista.",
        ),
        2: make_entity(
            2,
            "Aldric",
            entity_type="npc",
            description="Mercader y viejo amigo.",
        ),
        3: make_entity(
            3,
            "Morth",
            entity_type="npc",
            description="Rival peligroso.",
        ),
        4: make_entity(
            4,
            "Vera",
            entity_type="npc",
            description="Una guardia local.",
        ),
        5: make_entity(
            5,
            "Fantasma",
            entity_type="creature",
            description="Una criatura olvidada.",
        ),
        6: make_entity(
            6,
            "Inactivo",
            entity_type="npc",
            description="No debería aparecer.",
            active=False,
        ),
    }

    world.relations = {
        1: make_relation(
            1,
            1,
            2,
            relation_type="friend",
        ),
        2: make_relation(
            2,
            1,
            3,
            relation_type="enemy",
        ),
        3: make_relation(
            3,
            2,
            4,
            relation_type="knows",
        ),
        4: make_relation(
            4,
            1,
            6,
            relation_type="friend",
        ),
        5: make_relation(
            5,
            1,
            5,
            relation_type="knows",
            active=False,
        ),
    }

    return world


# ============================================================
# BASIC PIPELINE
# ============================================================


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
        1: Event(
            id=1,
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
        1: Event(
            id=1,
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
        1: Event(
            id=1,
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