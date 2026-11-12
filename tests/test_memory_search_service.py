from __future__ import annotations

import pytest

from models.entity import Entity
from models.event import Event
from models.item import Item
from models.relation import Relation
from models.resource import Resource
from models.world_state import WorldState
from services.context import ContextBuilder, MemorySearchService


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
    from services.context import (
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
    from services.context import (
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

def test_search_finds_entity_by_explicit_alias(service):
    world = WorldState(
        entities={
            12: Entity(
                id=12,
                name="Aldric",
                entity_type="npc",
                description="Un tabernero veterano.",
                aliases=["el tabernero", "el posadero"],
            )
        }
    )
    result = service.search(world, "Hablo con el tabernero")
    assert [entity["id"] for entity in result["entities"]] == [12]


def test_search_normalizes_accents_and_case_for_entity_names(service):
    world = WorldState(
        entities={2: Entity(id=2, name="Doña Cárdena", entity_type="npc")}
    )
    result = service.search(world, "dona cardena")
    assert [entity["id"] for entity in result["entities"]] == [2]


def test_search_abstains_when_an_entity_alias_is_ambiguous(service):
    world = WorldState(
        entities={
            1: Entity(id=1, name="Aldric", aliases=["el guardia"]),
            2: Entity(id=2, name="Mara", aliases=["la guardia", "el guardia"]),
        }
    )
    result = service.search(world, "Hablo con el guardia")
    assert result["entities"] == []


def test_search_resolves_role_from_description_only_when_all_terms_match(service):
    world = WorldState(
        entities={
            1: Entity(id=1, name="Aldric", description="El tabernero de la posada del Dragón."),
            2: Entity(id=2, name="Mara", description="Una exploradora de los bosques."),
        }
    )
    result = service.search(world, "Hablo con el tabernero de la posada")
    assert [entity["id"] for entity in result["entities"]] == [1]


def test_search_keeps_role_candidates_when_description_is_ambiguous(service):
    world = WorldState(
        entities={
            1: Entity(id=1, name="Aldric", description="Un guardia del puerto."),
            2: Entity(id=2, name="Mara", description="Una guardia del puerto."),
        }
    )
    result = service.search(world, "Quiero hablar con el guardia del puerto")
    assert [entity["id"] for entity in result["entities"]] == [1, 2]


def test_search_keeps_number_words_as_part_of_compound_entity_names(service):
    world = WorldState(
        entities={
            10: Entity(id=10, name="Entidad diez", entity_type="npc"),
            2: Entity(id=2, name="Entidad dos", entity_type="npc"),
            1: Entity(id=1, name="Entidad uno", entity_type="npc"),
        }
    )

    result = service.search(world, "Entidad")

    assert sorted(entity["id"] for entity in result["entities"]) == [1, 2, 10]


def test_search_respects_character_knowledge_scope(service):
    world = WorldState(
        events={
            "only-fungoso": Event(
                id="only-fungoso",
                event_type="clue",
                title="La carta revela el nombre del culto de ceniza",
                visibility_scope="character",
                known_by_entity_ids=[1],
                epistemic_status="rumor",
                provenance_source="npc_statement",
            ),
            "only-neria": Event(
                id="only-neria",
                event_type="clue",
                title="El mapa revela el refugio del pantano",
                visibility_scope="character",
                known_by_entity_ids=[2],
                provenance_source="direct_observation",
            ),
        }
    )

    assert service.search(world, "culto de ceniza")["events"] == []
    fungoso = service.search(
        world,
        "culto de ceniza",
        character_entity_id=1,
    )
    assert [event["id"] for event in fungoso["events"]] == ["only-fungoso"]
    assert fungoso["events"][0]["epistemic_status"] == "rumor"
    assert service.search(
        world,
        "culto de ceniza",
        character_entity_id=2,
    )["events"] == []


def test_search_labels_superseded_events_as_historical(service):
    old = Event(
        id="old-location",
        event_type="location",
        title="Aldric vive en la posada",
    )
    current = Event(
        id="new-location",
        event_type="location",
        title="Aldric vive en la torre",
        supersedes_event_id="old-location",
        campaign_elapsed_minutes=240,
    )
    world = WorldState(events={old.id: old, current.id: current})

    old_result = service.search(world, "posada")["events"]
    current_result = service.search(world, "torre")["events"]

    assert old_result[0]["is_current"] is False
    assert current_result[0]["is_current"] is True


def test_search_rejects_invalid_character_perspective(service, world):
    with pytest.raises(ValueError, match="character_entity_id"):
        service.search(world, "Fungoso", character_entity_id=True)


def test_context_builder_never_reintroduces_another_characters_private_event(service):
    world = WorldState(
        entities={
            1: Entity(id=1, name="Fungoso", entity_type="player_character"),
        },
        events={
            "private-clue": Event(
                id="private-clue",
                event_type="clue",
                title="La carta menciona el culto de ceniza",
                description="Una pista conocida solo por Fungoso.",
                visibility_scope="character",
                known_by_entity_ids=[1],
                provenance_source="direct_observation",
                metadata={"entity_ids": [1]},
            )
        },
    )
    builder = ContextBuilder(memory_search_service=service)

    fungoso_context = builder.build(
        world,
        "La carta",
        character_entity_id=1,
    )
    other_context = builder.build(
        world,
        "Fungoso",
        character_entity_id=2,
    )
    no_perspective = builder.build(
        world,
        "Fungoso",
    )

    assert [event["id"] for event in fungoso_context["events"]] == ["private-clue"]
    assert other_context["events"] == []
    assert no_perspective["events"] == []
    assert "culto de ceniza" in fungoso_context["context"]
    assert "culto de ceniza" not in other_context["context"]
