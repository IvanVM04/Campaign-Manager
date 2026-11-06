from models.entity import Entity
from models.world_state import WorldState
from operations.world_operations import CreateResourceOperation
from services.world import WorldApplier


def build_world():
    fungoso = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
    )

    return WorldState(
        entities={
            fungoso.id: fungoso,
        },
        items={},
        item_instances={},
        resources={},
        resource_balances={},
        relations={},
        events={},
    )


def test_create_resource_creates_resource():
    world = build_world()

    operation = CreateResourceOperation(
        name="Oro",
        resource_type="currency",
        unit="gp",
    )

    result = WorldApplier().apply(world, operation)

    assert result.status.value == "success"

    assert len(world.resources) == 1

    resource = next(iter(world.resources.values()))

    assert resource.name == "Oro"
    assert resource.resource_type == "currency"
    assert resource.unit == "gp"


def test_create_resource_rejects_duplicate_name():
    world = build_world()

    world.resources[10] = __import__(
        "models.resource",
        fromlist=["Resource"],
    ).Resource(
        id=10,
        name="Oro",
    )

    operation = CreateResourceOperation(
        name=" oro ",
    )

    result = WorldApplier().apply(world, operation)

    assert result.status.value == "duplicate"
    assert len(world.resources) == 1


def test_create_resource_rejects_empty_name():
    world = build_world()

    operation = CreateResourceOperation(
        name="   ",
    )

    result = WorldApplier().apply(world, operation)

    assert result.status.value == "invalid"
    assert world.resources == {}