from models.entity import Entity
from models.operation_result import OperationStatus
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState
from operations.world_operations import (
    CreateResourceOperation,
    GainResourceOperation,
    SpendResourceOperation,
    TransferResourceOperation,
)
from services.world import WorldResourceApplier


def build_world():
    return WorldState(
        entities={
            1: Entity(id=1, name="Fungoso", entity_type="character"),
            2: Entity(id=2, name="Neria", entity_type="character"),
        },
        resources={
            20: Resource(
                id=20,
                name="oro",
                resource_type="currency",
                unit="gp",
            )
        },
        resource_balances={
            200: ResourceBalance(
                id=200,
                resource_id=20,
                owner_id=1,
                amount=100,
            )
        },
    )


def test_create_resource_allocates_id_and_preserves_metadata():
    world = build_world()

    result = WorldResourceApplier().apply(
        world,
        CreateResourceOperation(
            name="Plata",
            resource_type="currency",
            unit="sp",
            notes="Moneda secundaria",
        ),
    )

    assert result.status == OperationStatus.SUCCESS
    assert result.data["resource_id"] == 21
    assert world.resources[21].unit == "sp"
    assert world.resources[21].notes == "Moneda secundaria"


def test_gain_resource_updates_existing_balance():
    world = build_world()

    result = WorldResourceApplier().apply(
        world,
        GainResourceOperation(resource_id=20, owner_id=1, amount=25),
    )

    assert result.status == OperationStatus.SUCCESS
    assert world.resource_balances[200].amount == 125


def test_spend_resource_rejects_insufficient_balance_without_mutation():
    world = build_world()

    result = WorldResourceApplier().apply(
        world,
        SpendResourceOperation(resource_id=20, owner_id=1, amount=150),
    )

    assert result.status == OperationStatus.INVALID
    assert world.resource_balances[200].amount == 100


def test_transfer_resource_moves_amount_between_existing_balances():
    world = build_world()
    world.resource_balances[201] = ResourceBalance(
        id=201,
        resource_id=20,
        owner_id=2,
        amount=10,
    )

    result = WorldResourceApplier().apply(
        world,
        TransferResourceOperation(
            resource_id=20,
            subject_id=1,
            target_id=2,
            amount=30,
        ),
    )

    assert result.status == OperationStatus.SUCCESS
    assert world.resource_balances[200].amount == 70
    assert world.resource_balances[201].amount == 40


def test_transfer_resource_rejects_invalid_amount_without_creating_balance():
    world = build_world()

    result = WorldResourceApplier().apply(
        world,
        TransferResourceOperation(
            resource_id=20,
            subject_id=1,
            target_id=2,
            amount=float("nan"),
        ),
    )

    assert result.status == OperationStatus.INVALID
    assert world.resource_balances[200].amount == 100
    assert len(world.resource_balances) == 1
