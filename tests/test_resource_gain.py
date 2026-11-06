from models.entity import Entity
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState
from operations.world_operations import GainResourceOperation
from services.world import WorldApplier


def build_world():
    fungoso = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
    )

    oro = Resource(
        id=20,
        name="Oro",
        resource_type="currency",
        unit="gp",
    )

    balance = ResourceBalance(
        id=200,
        resource_id=20,
        owner_id=1,
        amount=100,
    )

    return WorldState(
        entities={
            1: fungoso,
        },
        resources={
            20: oro,
        },
        resource_balances={
            200: balance,
        },
    )


def test_apply_resource_gained():
    world = build_world()

    operation = GainResourceOperation(
        resource_id=20,
        owner_id=1,
        amount=50,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 150

def test_apply_resource_gained_rejects_unknown_resource():
    world = build_world()

    operation = GainResourceOperation(
        resource_id=999,
        owner_id=1,
        amount=50,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100


def test_apply_resource_gained_rejects_unknown_owner():
    world = build_world()

    operation = GainResourceOperation(
        resource_id=20,
        owner_id=999,
        amount=50,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100


def test_apply_resource_gained_rejects_non_positive_amount():
    world = build_world()

    operation = GainResourceOperation(
        resource_id=20,
        owner_id=1,
        amount=-50,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100

def test_gain_resource_creates_missing_balance():
    world = build_world()

    world.resources[1] = Resource(
        id=1,
        name="Gold",
    )

    operation = GainResourceOperation(
        resource_id=1,
        owner_id=1,
        amount=100,
    )

    WorldApplier().apply(world, operation)

    balances = [
        balance
        for balance in world.resource_balances.values()
        if balance.resource_id == 1
        and balance.owner_id == 1
    ]

    assert len(balances) == 1
    assert balances[0].amount == 100

def test_apply_gain_resource_rejects_nan():
    world = build_world()

    world.resource_balances[1] = ResourceBalance(
        id=1,
        resource_id=1,
        owner_id=1,
        amount=100,
    )

    operation = GainResourceOperation(
        resource_id=1,
        owner_id=1,
        amount=float("nan"),
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100

def test_apply_gain_resource_rejects_infinity():
    world = build_world()

    world.resource_balances[1] = ResourceBalance(
        id=1,
        resource_id=1,
        owner_id=1,
        amount=100,
    )

    operation = GainResourceOperation(
        resource_id=1,
        owner_id=1,
        amount=float("inf"),
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100

def test_apply_gain_resource_rejects_duplicate_balances():
    world = build_world()

    world.resource_balances[1] = ResourceBalance(
        id=1,
        resource_id=1,
        owner_id=1,
        amount=100,
    )

    world.resource_balances[2] = ResourceBalance(
        id=2,
        resource_id=1,
        owner_id=1,
        amount=50,
    )

    operation = GainResourceOperation(
        resource_id=1,
        owner_id=1,
        amount=25,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100
    assert world.resource_balances[2].amount == 50