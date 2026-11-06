import pytest
from pydantic import ValidationError

from models.event import Event
from models.item import Item, ItemInstance
from models.relation import Relation
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState
from services.world import WorldCollectionQueryService


def make_world():
    return WorldState(
        items={
            2: Item(id=2, name="Silver Key", description="Opens the crypt"),
            1: Item(id=1, name="Iron Sword", weapon_key="longsword"),
        },
        item_instances={
            1: ItemInstance(
                id=1, item_id=2, instance_number=1,
                owner_id=7, condition="Pristine",
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


def test_collection_query_is_case_insensitive_and_paginates_stably():
    page = WorldCollectionQueryService().list_collection(
        make_world(), "items", query="SILVER", limit=1
    )

    assert page.total == 1
    assert page.items[0].name == "Silver Key"


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
