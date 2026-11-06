from models.entity import Entity
from models.event import Event
from models.world_state import WorldState
from operations.world_operations import CreateEventOperation
from services.world import WorldApplier


def build_world():
    return WorldState(
        entities={
            1: Entity(
                id=1,
                name="Fungoso",
                entity_type="character",
            ),
            2: Entity(
                id=2,
                name="Neria",
                entity_type="character",
            ),
        },
        events={},
    )


def test_apply_create_event():
    world = build_world()

    operation = CreateEventOperation(
        event_id="event-1",
        event_type="DISCOVERY",
        title="El diamante fue encontrado",
        description="Fungoso encontró el diamante arcoíris.",
        consequences="El diamante pasa a estar en posesión de Fungoso.",
        session_id=1,
        secret=False,
        metadata={
            "importance": "high",
        },
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert "event-1" in world.events

    event = world.events["event-1"]

    assert event.id == "event-1"
    assert event.event_type == "DISCOVERY"
    assert event.title == "El diamante fue encontrado"
    assert event.description == (
        "Fungoso encontró el diamante arcoíris."
    )
    assert event.consequences == (
        "El diamante pasa a estar en posesión de Fungoso."
    )
    assert event.session_id == 1
    assert event.secret is False
    assert event.metadata == {
        "importance": "high",
    }


def test_apply_create_event_with_defaults():
    world = build_world()

    operation = CreateEventOperation(
        event_id="event-1",
        event_type="DISCOVERY",
        title="Algo ocurrió",
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    event = world.events["event-1"]

    assert event.description == ""
    assert event.consequences == ""
    assert event.session_id is None
    assert event.secret is False
    assert event.metadata == {}


def test_apply_create_event_rejects_missing_id():
    world = build_world()

    operation = CreateEventOperation(
        event_id="",
        event_type="DISCOVERY",
        title="Algo ocurrió",
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.events == {}


def test_apply_create_event_rejects_missing_type():
    world = build_world()

    operation = CreateEventOperation(
        event_id="event-1",
        event_type="",
        title="Algo ocurrió",
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.events == {}


def test_apply_create_event_rejects_missing_title():
    world = build_world()

    operation = CreateEventOperation(
        event_id="event-1",
        event_type="DISCOVERY",
        title="",
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.events == {}


def test_apply_create_secret_event():
    world = build_world()

    operation = CreateEventOperation(
        event_id="event-secret",
        event_type="SECRET",
        title="El culto se reúne",
        secret=True,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    event = world.events["event-secret"]

    assert event.secret is True


def test_apply_create_event_with_metadata():
    world = build_world()

    operation = CreateEventOperation(
        event_id="event-1",
        event_type="BATTLE",
        title="Batalla en el bosque",
        metadata={
            "location": "Bosque Gris",
            "participants": [
                "Fungoso",
                "Neria",
            ],
        },
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    event = world.events["event-1"]

    assert event.metadata["location"] == "Bosque Gris"
    assert event.metadata["participants"] == [
        "Fungoso",
        "Neria",
    ]

def test_apply_create_event_accepts_empty_metadata():
    world = build_world()

    operation = CreateEventOperation(
        event_id="event-1",
        event_type="COMBAT",
        title="Batalla",
        metadata={},
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert "event-1" in world.events
    assert world.events["event-1"].metadata == {}

def test_apply_create_event_does_not_overwrite_existing_event():
    world = build_world()

    world.events["event-1"] = Event(
        id="event-1",
        event_type="COMBAT",
        title="Evento original",
        description="Original",
    )

    operation = CreateEventOperation(
        event_id="event-1",
        event_type="COMBAT",
        title="Evento nuevo",
        description="Nuevo",
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    event = world.events["event-1"]

    assert event.title == "Evento original"
    assert event.description == "Original"