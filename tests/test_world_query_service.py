import pytest
from pydantic import ValidationError

from models.entity import Entity
from models.world_state import WorldState
from services.world import WorldQueryService


def make_world():
    return WorldState(
        entities={
            3: Entity(
                id=3,
                name="Goblin",
                entity_type="creature",
                description="A small green raider.",
                notes="Lives near the old bridge.",
            ),
            1: Entity(
                id=1,
                name="Aldric",
                entity_type="character",
                description="A travelling fighter.",
            ),
            2: Entity(
                id=2,
                name="Aldora",
                entity_type="character",
                description="A village healer.",
                active=False,
            ),
        }
    )


def test_list_entities_filters_search_and_type():
    page = WorldQueryService().list_entities(
        make_world(),
        query="ALD",
        entity_type="character",
    )

    assert page.total == 2
    assert [entity.name for entity in page.items] == [
        "Aldric",
        "Aldora",
    ]


def test_list_entities_filters_active_and_paginates_stably():
    service = WorldQueryService()
    world = make_world()

    first = service.list_entities(world, active=True, limit=1)
    second = service.list_entities(
        world,
        active=True,
        limit=1,
        offset=1,
    )

    assert first.total == 2
    assert [entity.id for entity in first.items] == [1]
    assert [entity.id for entity in second.items] == [3]


def test_read_models_are_immutable_and_detached_from_world():
    world = make_world()
    page = WorldQueryService().list_entities(world)

    world.entities[1].name = "Changed after projection"

    assert page.items[0].name == "Aldric"
    with pytest.raises(ValidationError):
        page.items[0].name = "Mutated through API model"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit must be between 1 and 100"),
        ({"limit": 101}, "limit must be between 1 and 100"),
        ({"offset": -1}, "offset must not be negative"),
    ],
)
def test_list_entities_rejects_invalid_pagination(kwargs, message):
    with pytest.raises(ValueError, match=message):
        WorldQueryService().list_entities(make_world(), **kwargs)
