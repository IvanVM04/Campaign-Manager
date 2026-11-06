from models.entity import Entity
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState
from operations.world_operations import SpendResourceOperation
from services.world import WorldApplier


def build_world():
    world = WorldState()

    world.entities[1] = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
    )

    world.resources[20] = Resource(
        id=20,
        name="oro",
        resource_type="currency",
        unit="gp",
    )

    world.resource_balances[200] = ResourceBalance(
        id=200,
        resource_id=20,
        owner_id=1,
        amount=100,
    )

    return world


def test_apply_resource_spent():
    world = build_world()

    operation = SpendResourceOperation(
        resource_id=20,
        owner_id=1,
        amount=30,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 70


def test_apply_resource_spent_rejects_unknown_resource():
    world = build_world()

    operation = SpendResourceOperation(
        resource_id=999,
        owner_id=1,
        amount=30,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100


def test_apply_resource_spent_rejects_unknown_owner():
    world = build_world()

    operation = SpendResourceOperation(
        resource_id=20,
        owner_id=999,
        amount=30,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100


def test_apply_resource_spent_rejects_non_positive_amount():
    world = build_world()

    operation = SpendResourceOperation(
        resource_id=20,
        owner_id=1,
        amount=-30,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100


def test_apply_resource_spent_rejects_insufficient_balance():
    world = build_world()

    operation = SpendResourceOperation(
        resource_id=20,
        owner_id=1,
        amount=150,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100

def test_spend_resource_does_not_create_missing_balance():
    world = build_world()

    operation = SpendResourceOperation(
        resource_id=1,
        owner_id=1,
        amount=50,
    )

    WorldApplier().apply(world, operation)

    balances = [
        balance
        for balance in world.resource_balances.values()
        if balance.resource_id == 1
        and balance.owner_id == 1
    ]

    assert balances == []

def test_apply_spend_resource_rejects_nan():
    world = build_world()

    world.resource_balances[1] = ResourceBalance(
        id=1,
        resource_id=1,
        owner_id=1,
        amount=100,
    )

    operation = SpendResourceOperation(
        resource_id=1,
        owner_id=1,
        amount=float("nan"),
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100

def test_apply_spend_resource_rejects_infinity():
    world = build_world()

    world.resource_balances[1] = ResourceBalance(
        id=1,
        resource_id=1,
        owner_id=1,
        amount=100,
    )

    operation = SpendResourceOperation(
        resource_id=1,
        owner_id=1,
        amount=float("inf"),
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100

def test_apply_spend_resource_rejects_duplicate_balances():
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

    operation = SpendResourceOperation(
        resource_id=1,
        owner_id=1,
        amount=25,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100
    assert world.resource_balances[2].amount == 50

def test_apply_spend_resource_rejects_insufficient_balance_without_modifying_state():
    world = build_world()

    world.resource_balances[1] = ResourceBalance(
        id=1,
        resource_id=1,
        owner_id=1,
        amount=40,
    )

    operation = SpendResourceOperation(
        resource_id=1,
        owner_id=1,
        amount=50,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 40