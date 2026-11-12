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

def test_event_legacy_defaults_preserve_confirmed_public_gm_authored_meaning():
    event = Event(id="legacy", event_type="discovery", title="Old fact")

    assert event.epistemic_status == "confirmed"
    assert event.provenance_source == "gm_authored"
    assert event.visibility_scope == "public"
    assert event.known_by_entity_ids == []
    assert event.secret is False


def test_event_secret_compatibility_alias_forces_gm_only_visibility():
    event = Event(
        id="secret",
        event_type="secret",
        title="Hidden",
        secret=True,
    )

    assert event.visibility_scope == "gm_only"
    assert event.secret is True


def test_event_character_scope_requires_explicit_known_character_ids():
    import pytest

    with pytest.raises(ValueError, match="at least one known-by entity"):
        Event(
            id="private",
            event_type="discovery",
            title="Private clue",
            visibility_scope="character",
        )

    event = Event(
        id="private",
        event_type="discovery",
        title="Private clue",
        visibility_scope="character",
        known_by_entity_ids=[1, 1],
    )
    assert event.known_by_entity_ids == [1]


def test_event_rejects_model_inference_as_confirmed_canon():
    import pytest

    with pytest.raises(ValueError, match="must remain epistemically unconfirmed"):
        Event(
            id="inference",
            event_type="inference",
            title="A possible motive",
            provenance_source="model_inference",
            epistemic_status="confirmed",
        )


def test_visibility_policy_enforces_public_character_and_gm_perspectives():
    from models.world_visibility_policy import WorldVisibilityPolicy

    public = Event(id="public", event_type="fact", title="Public", visibility_scope="public")
    character_one = Event(
        id="private-1",
        event_type="clue",
        title="Clue for Fungoso",
        visibility_scope="character",
        known_by_entity_ids=[1],
        epistemic_status="confirmed",
        provenance_source="direct_observation",
    )
    character_two = Event(
        id="private-2",
        event_type="clue",
        title="Clue for Neria",
        visibility_scope="character",
        known_by_entity_ids=[2],
    )
    secret = Event(id="gm", event_type="secret", title="GM secret", visibility_scope="gm_only")

    assert [event.id for event in WorldVisibilityPolicy.player_visible_events(
        [public, character_one, character_two, secret]
    )] == ["public"]
    assert [event.id for event in WorldVisibilityPolicy.player_visible_events(
        [public, character_one, character_two, secret],
        character_entity_id=1,
    )] == ["public", "private-1"]
    assert [event.id for event in WorldVisibilityPolicy.player_visible_events(
        [public, character_one, character_two, secret],
        character_entity_id=2,
    )] == ["public", "private-2"]


def test_visibility_policy_marks_superseded_events_as_historical():
    from models.world_visibility_policy import WorldVisibilityPolicy

    earlier = Event(id="earlier", event_type="location", title="Aldric vive en la posada")
    later = Event(
        id="later",
        event_type="location",
        title="Aldric se muda a la torre",
        supersedes_event_id="earlier",
        campaign_elapsed_minutes=240,
    )

    assert WorldVisibilityPolicy.is_event_current(earlier, [earlier, later]) is False
    assert WorldVisibilityPolicy.is_event_current(later, [earlier, later]) is True
