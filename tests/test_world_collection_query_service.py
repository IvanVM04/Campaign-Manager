import pytest
from pydantic import ValidationError

from models.entity import Entity
from models.event import Event
from models.item import Item, ItemInstance
from models.relation import Relation
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState
from services.world import WorldCollectionQueryService


def make_world():
    return WorldState(
        entities={
            7: Entity(id=7, name="Aldric", entity_type="character"),
            8: Entity(id=8, name="Crypt", entity_type="location"),
        },
        items={
            2: Item(id=2, name="Silver Key", description="Opens the crypt"),
            1: Item(id=1, name="Iron Sword", weapon_key="longsword"),
        },
        item_instances={
            1: ItemInstance(
                id=1, item_id=2, instance_number=1,
                owner_id=7, location_id=8, condition="Pristine",
            ),
        },
        resources={
            1: Resource(id=1, name="Gold", resource_type="currency", unit="gp"),
        },
        resource_balances={
            1: ResourceBalance(
                id=1, resource_id=1, owner_id=7, amount=125, notes="Party treasury",
            ),
        },
        relations={
            "r-1": Relation(
                id="r-1", subject_id=7, relation_type="ALLY",
                target_id=8, metadata={"trust": 3},
            ),
        },
        events={
            "e-1": Event(
                id="e-1", event_type="discovery", title="Hidden door",
                description="A secret door was found",
                metadata={"room": "crypt"},
            ),
        },
    )


@pytest.mark.parametrize(
    ("collection", "expected", "expected_total"),
    [
        ("items", "Iron Sword", 2),
        ("item-instances", "Pristine", 1),
        ("resources", "Gold", 1),
        ("resource-balances", "Party treasury", 1),
        ("relations", "ALLY", 1),
        ("events", "Hidden door", 1),
    ],
)
def test_lists_each_world_collection(collection, expected, expected_total):
    page = WorldCollectionQueryService().list_collection(
        make_world(), collection
    )

    assert page.total == expected_total
    assert any(
        expected in str(item.model_dump()) for item in page.items
    )


def test_event_collection_filters_secret_events_before_search_and_pagination():
    world = make_world()
    world.events["secret-1"] = Event(
        id="secret-1",
        event_type="secret",
        title="The king is an impostor",
        description="A hidden fact.",
        secret=True,
    )
    service = WorldCollectionQueryService()

    page = service.list_collection(
        world,
        "events",
        limit=1,
        offset=1,
    )
    secret_match = service.list_collection(
        world,
        "events",
        query="impostor",
    )

    assert page.total == 1
    assert page.items == ()
    assert secret_match.total == 0
    assert secret_match.items == ()


def test_item_instances_include_item_owner_and_location_names():
    page = WorldCollectionQueryService().list_collection(
        make_world(), "item-instances"
    )

    instance = page.items[0]
    assert instance.item_id == 2
    assert instance.item_name == "Silver Key"
    assert instance.owner_id == 7
    assert instance.owner_name == "Aldric"
    assert instance.location_id == 8
    assert instance.location_name == "Crypt"


def test_resource_balances_include_resource_and_owner_names():
    page = WorldCollectionQueryService().list_collection(
        make_world(), "resource-balances"
    )

    balance = page.items[0]
    assert balance.resource_name == "Gold"
    assert balance.owner_name == "Aldric"


def test_relations_include_subject_and_target_names():
    page = WorldCollectionQueryService().list_collection(
        make_world(), "relations"
    )

    relation = page.items[0]
    assert relation.subject_name == "Aldric"
    assert relation.target_name == "Crypt"


def test_search_matches_related_entity_names():
    page = WorldCollectionQueryService().list_collection(
        make_world(), "item-instances", query="aldric"
    )

    assert page.total == 1
    assert page.items[0].owner_name == "Aldric"


def test_missing_related_records_keep_ids_and_return_null_names():
    world = make_world()
    world.entities.clear()
    world.items.clear()

    instance = WorldCollectionQueryService().list_collection(
        world, "item-instances"
    ).items[0]

    assert instance.item_id == 2
    assert instance.item_name is None
    assert instance.owner_id == 7
    assert instance.owner_name is None
    assert instance.location_id == 8
    assert instance.location_name is None


def test_relation_and_event_metadata_are_detached_json():
    world = make_world()
    service = WorldCollectionQueryService()

    relation = service.list_collection(world, "relations").items[0]
    event = service.list_collection(world, "events").items[0]

    world.relations["r-1"].metadata["trust"] = 99
    world.events["e-1"].metadata["room"] = "changed"

    assert relation.metadata_json == '{"trust": 3}'
    assert event.metadata_json == '{"room": "crypt"}'
    with pytest.raises(ValidationError):
        relation.active = False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit must be between 1 and 100"),
        ({"limit": 101}, "limit must be between 1 and 100"),
        ({"offset": -1}, "offset must not be negative"),
    ],
)
def test_collection_query_rejects_invalid_pagination(kwargs, message):
    with pytest.raises(ValueError, match=message):
        WorldCollectionQueryService().list_collection(
            make_world(), "items", **kwargs
        )


def test_collection_query_rejects_unknown_collection():
    with pytest.raises(ValueError, match="unsupported world collection"):
        WorldCollectionQueryService().list_collection(make_world(), "unknown")


def test_event_collection_scopes_character_knowledge_and_exposes_temporal_status():
    world = make_world()
    world.events["private-7"] = Event(
        id="private-7",
        event_type="clue",
        title="Fungoso knows the hidden entrance",
        visibility_scope="character",
        known_by_entity_ids=[7],
        provenance_source="direct_observation",
    )
    world.events["private-8"] = Event(
        id="private-8",
        event_type="clue",
        title="Neria knows the hidden passage",
        visibility_scope="character",
        known_by_entity_ids=[8],
    )
    world.events["old-fact"] = Event(
        id="old-fact",
        event_type="location",
        title="Aldric lives in the inn",
    )
    world.events["new-fact"] = Event(
        id="new-fact",
        event_type="location",
        title="Aldric lives in the tower",
        supersedes_event_id="old-fact",
    )
    service = WorldCollectionQueryService()

    no_perspective = service.list_collection(world, "events")
    fungoso = service.list_collection(
        world,
        "events",
        character_entity_id=7,
    )
    neria = service.list_collection(
        world,
        "events",
        character_entity_id=8,
    )

    assert "private-7" not in {item.id for item in no_perspective.items}
    assert "private-8" not in {item.id for item in no_perspective.items}
    assert "private-7" in {item.id for item in fungoso.items}
    assert "private-8" not in {item.id for item in fungoso.items}
    assert "private-8" in {item.id for item in neria.items}
    currentness = {item.id: item.is_current for item in fungoso.items}
    assert currentness["old-fact"] is False
    assert currentness["new-fact"] is True
    private_projection = next(item for item in fungoso.items if item.id == "private-7")
    assert not hasattr(private_projection, "known_by_entity_ids")



def test_event_collection_includes_resolved_provenance_source_name():
    world = make_world()
    world.events["rumor"] = Event(
        id="rumor",
        event_type="rumor",
        title="The lighthouse is cursed",
        provenance_source="npc_statement",
        source_entity_id=7,
    )

    event = next(
        item
        for item in WorldCollectionQueryService().list_collection(
            world,
            "events",
            character_entity_id=8,
        ).items
        if item.id == "rumor"
    )

    assert event.source_entity_id == 7
    assert event.source_entity_name == "Aldric"
    assert not hasattr(event, "known_by_entity_ids")
