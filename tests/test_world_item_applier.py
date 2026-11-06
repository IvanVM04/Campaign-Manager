from models.entity import Entity
from models.item import Item, ItemInstance
from models.operation_result import OperationStatus
from models.world_state import WorldState
from operations.world_operations import (
    CreateItemInstanceOperation,
    CreateItemOperation,
    TransferItemOperation,
    UpdateItemInstanceOperation,
)
from services.world.world_item_applier import WorldItemApplier


def build_world():
    return WorldState(
        entities={
            1: Entity(id=1, name="Fungoso", entity_type="character"),
            2: Entity(id=2, name="Neria", entity_type="character"),
        },
        items={10: Item(id=10, name="Espada")},
        item_instances={
            100: ItemInstance(
                id=100,
                item_id=10,
                instance_number=1,
                owner_id=1,
                condition="intacta",
                notes="Guardada",
                active=True,
            )
        },
    )


def test_create_item_allocates_id_and_preserves_equipment_metadata():
    world = build_world()

    result = WorldItemApplier().apply(
        world,
        CreateItemOperation(
            name="Armadura de cuero",
            armor_key="leather",
        ),
    )

    assert result.status == OperationStatus.SUCCESS
    assert result.data["item_id"] == 11
    assert world.items[11].armor_key == "leather"
    assert world.items[11].equipment_slot == "body"


def test_create_item_instance_allocates_id_and_validates_references():
    world = build_world()

    result = WorldItemApplier().apply(
        world,
        CreateItemInstanceOperation(
            item_id=10,
            instance_number=2,
            owner_id=2,
        ),
    )

    assert result.status == OperationStatus.SUCCESS
    assert result.data["instance_id"] == 101
    assert world.item_instances[101].owner_id == 2


def test_transfer_item_changes_owner_without_changing_other_state():
    world = build_world()

    result = WorldItemApplier().apply(
        world,
        TransferItemOperation(instance_id=100, new_owner_id=2),
    )

    assert result.status == OperationStatus.SUCCESS
    assert world.item_instances[100].owner_id == 2
    assert world.item_instances[100].condition == "intacta"
    assert world.item_instances[100].notes == "Guardada"


def test_update_item_instance_preserves_unset_fields_and_clears_notes():
    world = build_world()

    result = WorldItemApplier().apply(
        world,
        UpdateItemInstanceOperation(instance_id=100, notes=None),
    )

    assert result.status == OperationStatus.SUCCESS
    assert world.item_instances[100].owner_id == 1
    assert world.item_instances[100].condition == "intacta"
    assert world.item_instances[100].notes == ""
    assert world.item_instances[100].active is True


def test_create_item_instance_rejects_missing_item_without_mutation():
    world = build_world()

    result = WorldItemApplier().apply(
        world,
        CreateItemInstanceOperation(item_id=999, instance_number=1),
    )

    assert result.status == OperationStatus.NOT_FOUND
    assert len(world.item_instances) == 1
