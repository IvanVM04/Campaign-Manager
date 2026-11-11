from models.entity import Entity
from models.item import Item
from models.world_state import WorldState
from operations.world_operations import (
    CreateItemInstanceOperation,
    CreateItemOperation,
)
from services.llm_world.operation_parser import OperationParser
from services.world import WorldApplier


def build_world():
    fungoso = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
    )

    temple = Entity(
        id=2,
        name="Templo perdido",
        entity_type="location",
    )

    return WorldState(
        entities={
            fungoso.id: fungoso,
            temple.id: temple,
        },
        items={},
        item_instances={},
        resources={},
        resource_balances={},
        relations={},
        events={},
    )


def test_create_item_creates_item():
    world = build_world()

    operation = CreateItemOperation(
        name="Espada oxidada",
        description="Una vieja espada.",
    )

    result = WorldApplier().apply(world, operation)

    assert result.status.value == "success"

    assert len(world.items) == 1

    item = next(iter(world.items.values()))

    assert item.name == "Espada oxidada"
    assert item.description == "Una vieja espada."


def test_create_item_rejects_duplicate_name():
    world = build_world()

    world.items[10] = Item(
        id=10,
        name="Espada oxidada",
    )

    operation = CreateItemOperation(
        name="  espada oxidada  ",
    )

    result = WorldApplier().apply(world, operation)

    assert result.status.value == "duplicate"
    assert len(world.items) == 1


def test_create_item_rejects_empty_name():
    world = build_world()

    operation = CreateItemOperation(
        name="   ",
    )

    result = WorldApplier().apply(world, operation)

    assert result.status.value == "invalid"
    assert world.items == {}


def test_create_item_instance_requires_existing_item():
    world = build_world()

    operation = CreateItemInstanceOperation(
        item_id=999,
        owner_id=1,
    )

    result = WorldApplier().apply(world, operation)

    assert result.status.value == "not_found"
    assert world.item_instances == {}


def test_create_item_instance_requires_existing_owner():
    world = build_world()

    world.items[10] = Item(
        id=10,
        name="Espada oxidada",
    )

    operation = CreateItemInstanceOperation(
        item_id=10,
        owner_id=999,
    )

    result = WorldApplier().apply(world, operation)

    assert result.status.value == "not_found"
    assert world.item_instances == {}


def test_create_item_instance_creates_instance():
    world = build_world()

    world.items[10] = Item(
        id=10,
        name="Espada oxidada",
    )

    operation = CreateItemInstanceOperation(
        item_id=10,
        instance_number=1,
        owner_id=1,
        condition="mala",
    )

    result = WorldApplier().apply(world, operation)

    assert result.status.value == "success"

    assert len(world.item_instances) == 1

    instance = next(iter(world.item_instances.values()))

    assert instance.item_id == 10
    assert instance.instance_number == 1
    assert instance.owner_id == 1
    assert instance.condition == "mala"


def test_create_item_instance_rejects_duplicate_instance_number():
    world = build_world()

    world.items[10] = Item(
        id=10,
        name="Espada oxidada",
    )

    world.item_instances[100] = (
        __import__("models.item", fromlist=["ItemInstance"])
        .ItemInstance(
            id=100,
            item_id=10,
            instance_number=1,
            owner_id=1,
        )
    )

    operation = CreateItemInstanceOperation(
        item_id=10,
        instance_number=1,
        owner_id=1,
    )

    result = WorldApplier().apply(world, operation)

    assert result.status.value == "duplicate"
    assert len(world.item_instances) == 1


def test_create_item_preserves_weapon_and_equipment_metadata():
    world = build_world()
    result = WorldApplier().apply(
        world,
        CreateItemOperation(
            name="Espada larga",
            weapon_key="longsword",
            equipment_slot="off_hand",
        ),
    )
    assert result.success
    item = next(iter(world.items.values()))
    assert item.weapon_key == "longsword"
    assert item.equipment_slot == "off_hand"


def test_create_weapon_defaults_to_main_hand():
    world = build_world()
    result = WorldApplier().apply(
        world,
        CreateItemOperation(name="Espada larga", weapon_key="longsword"),
    )
    assert result.success
    assert next(iter(world.items.values())).equipment_slot == "main_hand"


def test_create_weapon_rejects_non_hand_equipment_slot():
    world = build_world()
    result = WorldApplier().apply(
        world,
        CreateItemOperation(
            name="Espada larga", weapon_key="longsword", equipment_slot="body"
        ),
    )
    assert result.status.value == "invalid"
    assert world.items == {}




def test_create_armor_item_defaults_to_body_slot():
    world = build_world()
    result = WorldApplier().apply(
        world,
        CreateItemOperation(name="Armadura de cuero", armor_key="leather"),
    )
    assert result.success
    item = next(iter(world.items.values()))
    assert item.armor_key == "leather"
    assert item.equipment_slot == "body"


def test_create_shield_item_defaults_to_off_hand_slot():
    world = build_world()
    result = WorldApplier().apply(
        world,
        CreateItemOperation(name="Escudo", armor_key="shield"),
    )
    assert result.success
    item = next(iter(world.items.values()))
    assert item.armor_key == "shield"
    assert item.equipment_slot == "off_hand"


def test_create_armor_rejects_incompatible_slot_and_weapon_metadata():
    world = build_world()
    wrong_slot = WorldApplier().apply(
        world,
        CreateItemOperation(
            name="Armadura", armor_key="leather", equipment_slot="off_hand"
        ),
    )
    both = WorldApplier().apply(
        world,
        CreateItemOperation(
            name="Armadura espada", armor_key="leather", weapon_key="longsword"
        ),
    )
    assert wrong_slot.status.value == "invalid"
    assert both.status.value == "invalid"
    assert world.items == {}


def test_parser_accepts_armor_metadata_on_item_definition():
    operation = OperationParser().parse({
        "operations": [{
            "type": "create_item",
            "name": "Escudo",
            "armor_key": "shield",
            "equipment_slot": "off_hand",
        }]
    })[0]
    assert isinstance(operation, CreateItemOperation)
    assert operation.armor_key == "shield"
    assert operation.equipment_slot == "off_hand"


def test_parser_accepts_equipment_metadata_on_item_definition():
    operations = OperationParser().parse({
        "operations": [{
            "type": "create_item",
            "name": "Chain mail",
            "equipment_slot": "body",
        }]
    })
    operation = operations[0]
    assert isinstance(operation, CreateItemOperation)
    assert operation.equipment_slot == "body"
