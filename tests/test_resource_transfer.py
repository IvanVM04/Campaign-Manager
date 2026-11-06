from models.entity import Entity
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState
from operations.world_operations import TransferResourceOperation
from services.world import WorldApplier


def build_world():
    world = WorldState()

    world.entities[1] = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
    )

    world.entities[2] = Entity(
        id=2,
        name="Neria",
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

    world.resource_balances[201] = ResourceBalance(
        id=201,
        resource_id=20,
        owner_id=2,
        amount=25,
    )

    return world


def test_transfer_resource():
    world = build_world()

    operation = TransferResourceOperation(
        resource_id=20,
        subject_id=1,
        target_id=2,
        amount=30,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 70
    assert world.resource_balances[201].amount == 55


def test_transfer_resource_rejects_unknown_resource():
    world = build_world()

    operation = TransferResourceOperation(
        resource_id=999,
        subject_id=1,
        target_id=2,
        amount=30,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100
    assert world.resource_balances[201].amount == 25


def test_transfer_resource_rejects_unknown_source():
    world = build_world()

    operation = TransferResourceOperation(
        resource_id=20,
        subject_id=999,
        target_id=2,
        amount=30,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100
    assert world.resource_balances[201].amount == 25


def test_transfer_resource_rejects_unknown_target():
    world = build_world()

    operation = TransferResourceOperation(
        resource_id=20,
        subject_id=1,
        target_id=999,
        amount=30,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100
    assert world.resource_balances[201].amount == 25


def test_transfer_resource_rejects_non_positive_amount():
    world = build_world()

    operation = TransferResourceOperation(
        resource_id=20,
        subject_id=1,
        target_id=2,
        amount=-30,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100
    assert world.resource_balances[201].amount == 25


def test_transfer_resource_rejects_insufficient_balance():
    world = build_world()

    operation = TransferResourceOperation(
        resource_id=20,
        subject_id=1,
        target_id=2,
        amount=150,
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert world.resource_balances[200].amount == 100
    assert world.resource_balances[201].amount == 25

def test_transfer_resource_creates_missing_target_balance():
    world = build_world()

    world.resources[1] = Resource(
        id=1,
        name="Gold",
    )

    world.resource_balances[1] = ResourceBalance(
        id=1,
        resource_id=1,
        owner_id=1,
        amount=100,
    )

    operation = TransferResourceOperation(
        resource_id=1,
        subject_id=1,
        target_id=2,
        amount=40,
    )

    WorldApplier().apply(world, operation)

    source = next(
        balance
        for balance in world.resource_balances.values()
        if balance.resource_id == 1
        and balance.owner_id == 1
    )

    target = next(
        balance
        for balance in world.resource_balances.values()
        if balance.resource_id == 1
        and balance.owner_id == 2
    )

    assert source.amount == 60
    assert target.amount == 40

def test_apply_transfer_resource_rejects_nan():
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
        owner_id=2,
        amount=50,
    )

    operation = TransferResourceOperation(
        resource_id=1,
        subject_id=1,
        target_id=2,
        amount=float("nan"),
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100
    assert world.resource_balances[2].amount == 50

def test_apply_transfer_resource_rejects_infinity():
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
        owner_id=2,
        amount=50,
    )

    operation = TransferResourceOperation(
        resource_id=1,
        subject_id=1,
        target_id=2,
        amount=float("inf"),
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100
    assert world.resource_balances[2].amount == 50

def test_apply_transfer_resource_rejects_duplicate_source_balance():
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

    world.resource_balances[3] = ResourceBalance(
        id=3,
        resource_id=1,
        owner_id=2,
        amount=25,
    )

    operation = TransferResourceOperation(
        resource_id=1,
        subject_id=1,
        target_id=2,
        amount=20,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100
    assert world.resource_balances[2].amount == 50
    assert world.resource_balances[3].amount == 25

def test_apply_transfer_resource_rejects_missing_target_balance():
    world = build_world()

    world.resource_balances[1] = ResourceBalance(
        id=1,
        resource_id=1,
        owner_id=1,
        amount=100,
    )

    operation = TransferResourceOperation(
        resource_id=1,
        subject_id=1,
        target_id=2,
        amount=40,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100
    assert 2 not in world.resource_balances

def test_apply_transfer_resource_rejects_non_positive_amount():
    world = build_world()

    world.resource_balances[1] = ResourceBalance(
        id=1,
        resource_id=1,
        owner_id=1,
        amount=100,
    )

    operation = TransferResourceOperation(
        resource_id=1,
        subject_id=1,
        target_id=2,
        amount=0,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100
    assert 2 not in world.resource_balances

def test_apply_transfer_resource_rejects_self_transfer():
    world = build_world()

    world.resource_balances[1] = ResourceBalance(
        id=1,
        resource_id=1,
        owner_id=1,
        amount=100,
    )

    operation = TransferResourceOperation(
        resource_id=1,
        subject_id=1,
        target_id=1,
        amount=40,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100

def test_apply_transfer_resource_rejects_unknown_source():
    world = build_world()

    world.resource_balances[1] = ResourceBalance(
        id=1,
        resource_id=1,
        owner_id=1,
        amount=100,
    )

    operation = TransferResourceOperation(
        resource_id=1,
        subject_id=999,
        target_id=2,
        amount=40,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100
    assert 2 not in world.resource_balances

def test_apply_transfer_resource_rejects_unknown_resource():
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
        owner_id=2,
        amount=50,
    )

    operation = TransferResourceOperation(
        resource_id=999,
        subject_id=1,
        target_id=2,
        amount=40,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.resource_balances[1].amount == 100
    assert world.resource_balances[2].amount == 50