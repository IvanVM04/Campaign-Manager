from __future__ import annotations

import pytest

from models.entity import Entity
from models.event import Event
from models.item import Item
from models.relation import Relation
from models.resource import Resource
from models.world_state import WorldState
from services.context import ContextBuilder
from services.context import MemorySearchService


@pytest.fixture
def service():
    return MemorySearchService()


@pytest.fixture
def world():
    fungoso = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
        description="Un aventurero peculiar.",
        notes="Le gusta el oro.",
        active=True,
    )

    goblin = Entity(
        id=2,
        name="Goblin",
        entity_type="creature",
        description="Una criatura hostil de la mina.",
        notes="Vive cerca de Vorder's Hold.",
        active=True,
    )

    sword = Item(
        id=1,
        name="Espada de hierro",
        description="Una espada sencilla.",
        significance="Común",
        unique=False,
        notes="Tiene una pequeña muesca.",
    )

    gold = Resource(
        id=1,
        name="Oro",
        resource_type="currency",
        unit="monedas",
        notes="Moneda habitual.",
    )

    relation = Relation(
        id="fungoso-goblin",
        subject_id=1,
        relation_type="enemy_of",
        target_id=2,
        metadata={
            "reason": "Intentó robarle",
            "strength": 80,
        },
        active=True,
    )

    public_event = Event(
        id="event-001",
        event_type="discovery",
        title="La mina abandonada",
        description="Fungoso descubre una mina abandonada.",
        consequences="Se abre una nueva zona de exploración.",
        session_id=1,
        secret=False,
        metadata={
            "location": "Vorder's Hold",
        },
    )

    secret_event = Event(
        id="secret-001",
        event_type="secret",
        title="El verdadero origen del rey",
        description="El rey es realmente un impostor.",
        consequences="El jugador todavía no lo sabe.",
        session_id=1,
        secret=True,
        metadata={
            "importance": "critical",
        },
    )

    return WorldState(
        entities={
            fungoso.id: fungoso,
            goblin.id: goblin,
        },
        items={
            sword.id: sword,
        },
        resources={
            gold.id: gold,
        },
        relations={
            relation.id: relation,
        },
        events={
            public_event.id: public_event,
            secret_event.id: secret_event,
        },
    )


# ============================================================
# ENTITIES
# ============================================================


def test_search_finds_entity_by_name(service, world):
    result = service.search(world, "Fungoso")

    assert len(result["entities"]) == 1
    assert result["entities"][0]["id"] == 1
    assert result["entities"][0]["name"] == "Fungoso"


def test_search_finds_entity_by_description(service, world):
    result = service.search(world, "criatura hostil")

    assert len(result["entities"]) == 1
    assert result["entities"][0]["name"] == "Goblin"


def test_search_is_case_insensitive(service, world):
    result = service.search(world, "FUNGOSO")

    assert len(result["entities"]) == 1
    assert result["entities"][0]["name"] == "Fungoso"


# ============================================================
# ITEMS
# ============================================================


def test_search_finds_item(service, world):
    result = service.search(world, "espada")

    assert len(result["items"]) == 1
    assert result["items"][0]["name"] == "Espada de hierro"


def test_search_finds_item_by_notes(service, world):
    result = service.search(world, "muesca")

    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == 1


# ============================================================
# RESOURCES
# ============================================================


def test_search_finds_resource(service, world):
    result = service.search(world, "oro")

    assert len(result["resources"]) == 1
    assert result["resources"][0]["name"] == "Oro"


def test_search_finds_resource_by_type(service, world):
    result = service.search(world, "currency")

    assert len(result["resources"]) == 1
    assert result["resources"][0]["name"] == "Oro"


# ============================================================
# RELATIONS
# ============================================================


def test_search_finds_relation_by_type(service, world):
    result = service.search(world, "enemy_of")

    assert len(result["relations"]) == 1
    assert result["relations"][0]["id"] == "fungoso-goblin"


def test_search_finds_relation_metadata(service, world):
    result = service.search(world, "robarle")

    assert len(result["relations"]) == 1
    assert result["relations"][0]["id"] == "fungoso-goblin"


# ============================================================
# EVENTS
# ============================================================


def test_search_finds_public_event(service, world):
    result = service.search(world, "mina abandonada")

    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "event-001"


def test_search_does_not_expose_secret_events(service, world):
    result = service.search(world, "impostor")

    assert result["events"] == []


def test_search_does_not_expose_secret_event_by_id(service, world):
    result = service.search(world, "secret-001")

    assert result["events"] == []


# ============================================================
# NO RESULTS
# ============================================================


def test_search_returns_empty_result_when_nothing_matches(service, world):
    result = service.search(world, "dragón inexistente")

    assert result == {
        "entities": [],
        "items": [],
        "item_instances": [],
        "resources": [],
        "resource_balances": [],
        "relations": [],
        "events": [],
    }


def test_search_empty_query_returns_empty_result(service, world):
    result = service.search(world, "   ")

    assert result == {
        "entities": [],
        "items": [],
        "item_instances": [],
        "resources": [],
        "resource_balances": [],
        "relations": [],
        "events": [],
    }


# ============================================================
# CONTEXT
# ============================================================


def test_context_wraps_search_results(service, world):
    context_builder = ContextBuilder(
        memory_search_service=service,
    )

    result = context_builder.build(
        world,
        "Fungoso",
    )

    assert result["query"] == "Fungoso"
    assert "entities" in result
    assert "items" in result
    assert "item_instances" in result
    assert "resources" in result
    assert "resource_balances" in result
    assert "relations" in result
    assert "events" in result
    assert "context" in result

    assert any(
        entity["name"] == "Fungoso"
        for entity in result["entities"]
    )

    assert "Fungoso" in result["context"]


# ============================================================
# WORLDSTATE INMUTABLE
# ============================================================


def test_search_does_not_modify_world(service, world):
    entities_before = dict(world.entities)
    items_before = dict(world.items)
    resources_before = dict(world.resources)
    relations_before = dict(world.relations)
    events_before = dict(world.events)

    service.search(world, "Fungoso")

    assert world.entities == entities_before
    assert world.items == items_before
    assert world.resources == resources_before
    assert world.relations == relations_before
    assert world.events == events_before


# ============================================================
# VALIDATION
# ============================================================


def test_search_requires_worldstate(service):
    with pytest.raises(TypeError):
        service.search(object(), "Fungoso")


def test_search_requires_string_query(service, world):
    with pytest.raises(TypeError):
        service.search(world, 123)


# ============================================================
# METADATA
# ============================================================


def test_search_can_find_event_by_metadata(service, world):
    result = service.search(world, "Vorder's Hold")

    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "event-001"

def test_search_matches_entity_from_natural_language_query():
    from models.entity import Entity
    from models.world_state import WorldState
    from services.memory_search_service import (
        MemorySearchService,
    )

    world = WorldState()

    entity = Entity(
        id=1,
        name="Aldren",
        entity_type="npc",
        description="Propietario de la taberna.",
        notes="",
        active=True,
    )

    world.entities[entity.id] = entity

    service = MemorySearchService()

    result = service.search(
        world,
        "¿Quién es Aldren?",
    )

    assert len(result["entities"]) == 1
    assert result["entities"][0]["name"] == "Aldren"


def test_search_matches_entity_when_name_is_only_part_of_query():
    from models.entity import Entity
    from models.world_state import WorldState
    from services.memory_search_service import (
        MemorySearchService,
    )

    world = WorldState()

    entity = Entity(
        id=1,
        name="Aldren",
        entity_type="npc",
        description="Propietario de la taberna.",
        notes="",
        active=True,
    )

    world.entities[entity.id] = entity

    service = MemorySearchService()

    result = service.search(
        world,
        "Háblame de Aldren",
    )

    assert len(result["entities"]) == 1
    assert result["entities"][0]["name"] == "Aldren"