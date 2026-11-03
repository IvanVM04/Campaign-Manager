from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app
from models.entity import Entity
from models.event import Event
from models.item import Item
from models.relation import Relation
from models.world_state import WorldState

client = TestClient(
    app,
    headers={"X-Campaign-Id": "1"},
)


@pytest.fixture
def clean_world():
    """
    Sustituye temporalmente el WorldState utilizado por app.py
    por uno controlado por el test.
    """

    import app as app_module

    runtime = app_module.runtime_factory.get_runtime(1)
    original_world = runtime.world_service.world

    world = WorldState()

    runtime.world_service.world = world

    try:
        yield world
    finally:
        runtime.world_service.world = original_world


# ============================================================
# ENTITY
# ============================================================


def test_memory_search_http_finds_entity(clean_world):
    clean_world.entities[1] = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
        description="Un aventurero peculiar.",
        notes="Le gusta el oro.",
        active=True,
    )

    response = client.get(
        "/memory/search",
        params={"q": "Fungoso"},
    )

    assert response.status_code == 200

    data = response.json()

    assert "entities" in data
    assert len(data["entities"]) == 1

    assert data["entities"][0]["id"] == 1
    assert data["entities"][0]["name"] == "Fungoso"


def test_memory_search_http_is_case_insensitive(clean_world):
    clean_world.entities[1] = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
        description="Un aventurero peculiar.",
        notes="",
        active=True,
    )

    response = client.get(
        "/memory/search",
        params={"q": "FUNGOSO"},
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["entities"]) == 1
    assert data["entities"][0]["name"] == "Fungoso"


# ============================================================
# ITEM
# ============================================================


def test_memory_search_http_finds_item(clean_world):
    clean_world.items[1] = Item(
        id=1,
        name="Espada de hierro",
        description="Una espada sencilla.",
        significance="Común",
        unique=False,
        notes="Tiene una pequeña muesca.",
    )

    response = client.get(
        "/memory/search",
        params={"q": "espada"},
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == 1
    assert data["items"][0]["name"] == "Espada de hierro"


# ============================================================
# RELATION
# ============================================================


def test_memory_search_http_finds_relation(clean_world):
    clean_world.relations["fungoso-goblin"] = Relation(
        id="fungoso-goblin",
        subject_id=1,
        relation_type="enemy_of",
        target_id=2,
        metadata={
            "reason": "Intentó robarle",
        },
        active=True,
    )

    response = client.get(
        "/memory/search",
        params={"q": "enemy_of"},
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["relations"]) == 1

    relation = data["relations"][0]

    assert relation["id"] == "fungoso-goblin"
    assert relation["subject_id"] == 1
    assert relation["target_id"] == 2


# ============================================================
# PUBLIC EVENT
# ============================================================


def test_memory_search_http_returns_public_event(clean_world):
    clean_world.events["event-001"] = Event(
        id="event-001",
        event_type="discovery",
        title="La mina abandonada",
        description="Fungoso descubre una mina abandonada.",
        consequences="Se abre una nueva zona.",
        session_id=1,
        secret=False,
        metadata={
            "location": "Vorder's Hold",
        },
    )

    response = client.get(
        "/memory/search",
        params={"q": "mina abandonada"},
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["events"]) == 1

    event = data["events"][0]

    assert event["id"] == "event-001"
    assert event["secret"] is False


# ============================================================
# SECRET EVENT
# ============================================================


def test_memory_search_http_does_not_expose_secret_event(clean_world):
    clean_world.events["secret-001"] = Event(
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

    response = client.get(
        "/memory/search",
        params={"q": "impostor"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["events"] == []


# ============================================================
# CONTEXT
# ============================================================


def test_memory_context_http_returns_context(clean_world):
    clean_world.entities[1] = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
        description="Un aventurero peculiar.",
        notes="",
        active=True,
    )

    response = client.get(
        "/memory/context",
        params={"q": "Fungoso"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["query"] == "Fungoso"
    assert "entities" in data
    assert "context" in data

    assert any(
        entity["name"] == "Fungoso"
        for entity in data["entities"]
    )

    assert "Fungoso" in data["context"]


# ============================================================
# NO RESULTS
# ============================================================


def test_memory_search_http_returns_empty_categories(clean_world):
    response = client.get(
        "/memory/search",
        params={"q": "esto-no-existe"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data == {
        "entities": [],
        "items": [],
        "item_instances": [],
        "resources": [],
        "resource_balances": [],
        "relations": [],
        "events": [],
    }


# ============================================================
# QUERY REQUIRED
# ============================================================


def test_memory_search_http_requires_query():
    response = client.get("/memory/search")

    assert response.status_code == 422


def test_memory_context_http_requires_query():
    response = client.get("/memory/context")

    assert response.status_code == 422

def test_export_returns_world_state_categories(clean_world):
    clean_world.entities[1] = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
        description="Un aventurero peculiar.",
        notes="",
        active=True,
    )

    response = client.get("/export")

    assert response.status_code == 200

    data = response.json()

    assert set(data.keys()) == {
        "entities",
        "items",
        "item_instances",
        "resources",
        "resource_balances",
        "relations",
        "events",
    }

    assert data["entities"][0]["name"] == "Fungoso"

def test_export_does_not_expose_inactive_entity(
    clean_world,
):
    clean_world.entities[1] = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
        description="Activo.",
        notes="",
        active=True,
    )

    clean_world.entities[2] = Entity(
        id=2,
        name="Goblin olvidado",
        entity_type="character",
        description="Inactivo.",
        notes="",
        active=False,
    )

    response = client.get("/export")

    assert response.status_code == 200

    data = response.json()

    names = {
        entity["name"]
        for entity in data["entities"]
    }

    assert names == {
        "Fungoso",
    }

def test_export_does_not_expose_secret_events(
    clean_world,
):
    clean_world.events["public-001"] = Event(
        id="public-001",
        event_type="discovery",
        title="La mina",
        description="Se descubre una mina.",
        consequences="Nueva zona disponible.",
        session_id=1,
        secret=False,
        metadata={},
    )

    clean_world.events["secret-001"] = Event(
        id="secret-001",
        event_type="secret",
        title="La conspiración",
        description="Un secreto importante.",
        consequences="El jugador no lo sabe.",
        session_id=1,
        secret=True,
        metadata={},
    )

    response = client.get("/export")

    assert response.status_code == 200

    data = response.json()

    event_ids = {
        event["id"]
        for event in data["events"]
    }

    assert event_ids == {
        "public-001",
    }

def test_export_does_not_expose_inactive_relations(
    clean_world,
):
    clean_world.relations["active-001"] = Relation(
        id="active-001",
        subject_id=1,
        relation_type="ally_of",
        target_id=2,
        metadata={},
        active=True,
    )

    clean_world.relations["inactive-001"] = Relation(
        id="inactive-001",
        subject_id=1,
        relation_type="enemy_of",
        target_id=3,
        metadata={},
        active=False,
    )

    response = client.get("/export")

    assert response.status_code == 200

    data = response.json()

    relation_ids = {
        relation["id"]
        for relation in data["relations"]
    }

    assert relation_ids == {
        "active-001",
    }

def test_memory_context_rejects_missing_query(
    client,
):
    response = client.get(
        "/memory/context"
    )

    assert response.status_code == 422


def test_memory_context_rejects_empty_query(
    client,
):
    response = client.get(
        "/memory/context?q="
    )

    assert response.status_code == 422

def test_memory_context_accepts_query(
    client,
    monkeypatch,
):
    def fake_build(
        world,
        query,
    ):
        assert query == "Aldric"

        return {
            "context": "Aldric es un mercader.",
        }

    monkeypatch.setattr(
        "app.context_builder.build",
        fake_build,
    )

    response = client.get(
        "/memory/context?q=Aldric"
    )

    assert response.status_code == 200

    assert response.json() == {
        "context": "Aldric es un mercader.",
    }