from models.entity import Entity
from models.item import Item, ItemInstance
from models.world_state import WorldState
from operations.operation_reference import OperationReference
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import (
    CreateEntityOperation,
    CreateItemInstanceOperation,
    CreateItemOperation,
    TransferItemOperation,
)
from services.world import WorldApplier, WorldService


def build_world():
    fungoso = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
    )

    neria = Entity(
        id=2,
        name="Neria",
        entity_type="character",
    )

    temple = Entity(
        id=3,
        name="Templo perdido",
        entity_type="location",
    )

    diamond = Item(
        id=10,
        name="Diamante arcoíris",
    )

    diamond_1 = ItemInstance(
        id=100,
        item_id=10,
        instance_number=1,
        owner_id=1,
    )

    diamond_2 = ItemInstance(
        id=101,
        item_id=10,
        instance_number=2,
        location_id=3,
    )

    world = WorldState(
        entities={
            fungoso.id: fungoso,
            neria.id: neria,
            temple.id: temple,
        },
        items={
            diamond.id: diamond,
        },
        item_instances={
            diamond_1.id: diamond_1,
            diamond_2.id: diamond_2,
        },
        resources={},
        resource_balances={},
        relations={},
        events={},
    )

    return world


def test_applier_rejects_unknown_owner():
    world = build_world()

    operation = TransferItemOperation(
        instance_id=100,
        new_owner_id=999,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    # El propietario original no debe cambiar.
    assert world.item_instances[100].owner_id == 1


def test_applier_is_idempotent_for_same_owner():
    world = build_world()

    operation = TransferItemOperation(
        instance_id=100,
        new_owner_id=1,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    # Sigue perteneciendo a Fungoso.
    assert world.item_instances[100].owner_id == 1

def test_applier_ignores_unknown_item_instance():
    world = build_world()

    operation = TransferItemOperation(
        instance_id=999,
        new_owner_id=2,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    # La operación apunta a una instancia inexistente.
    # No debe crearla ni modificar ninguna otra.
    assert 999 not in world.item_instances

    assert world.item_instances[100].owner_id == 1
    assert world.item_instances[101].owner_id is None

def test_transfer_item_resolves_new_owner_reference():
    service = WorldService()

    results = service.apply_operations(
        [
            ReferencedOperation(
                operation=CreateItemOperation(
                    name="Espada de hierro",
                ),
                ref="sword",
            ),
            ReferencedOperation(
                operation=CreateEntityOperation(
                    name="Aldren",
                    entity_type="npc",
                ),
                ref="npc1",
            ),
            ReferencedOperation(
                operation=CreateEntityOperation(
                    name="Neria",
                    entity_type="npc",
                ),
                ref="npc2",
            ),
            ReferencedOperation(
                operation=CreateItemInstanceOperation(
                    item_id=OperationReference("sword"),
                    owner_id=OperationReference("npc1"),
                ),
                ref="instance",
            ),
            TransferItemOperation(
                instance_id=OperationReference("instance"),
                new_owner_id=OperationReference("npc2"),
            ),
        ]
    )

    assert results.success
    assert results.changed

    world = service.get_world()

    neria = next(
        entity
        for entity in world.entities.values()
        if entity.name == "Neria"
    )

    instance = next(
        instance
        for instance in world.item_instances.values()
        if instance.instance_number == 1
    )

    assert instance.owner_id == neria.id