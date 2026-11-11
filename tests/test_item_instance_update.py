import pytest

from models.entity import Entity
from models.item import Item, ItemInstance
from models.operation_result import OperationStatus
from models.world_state import WorldState
from operations.operation_reference import OperationReference
from operations.world_operations import (
    _UNSET,
    CreateItemInstanceOperation,
    UpdateItemInstanceOperation,
)
from services.llm_world.operation_parser import (
    OperationParseError,
    OperationParser,
)
from services.world import WorldApplier


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

    diamond_instance = ItemInstance(
        id=100,
        item_id=10,
        instance_number=1,
        owner_id=1,
        location_id=3,
        condition="intacto",
        notes="Guardado en una bolsa.",
        active=True,
    )

    return WorldState(
        entities={
            fungoso.id: fungoso,
            neria.id: neria,
            temple.id: temple,
        },
        items={
            diamond.id: diamond,
        },
        item_instances={
            diamond_instance.id: diamond_instance,
        },
        resources={},
        resource_balances={},
        relations={},
        events={},
    )

def test_applier_updates_owner():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        owner_id=2,
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.success
    assert result.changed
    assert world.item_instances[100].owner_id == 2

def test_applier_updates_location():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        location_id=2,
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.success
    assert result.changed
    assert world.item_instances[100].location_id == 2

def test_applier_updates_condition():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        condition="dañado",
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.success
    assert result.changed

    assert (
        world.item_instances[100].condition
        == "dañado"
    )

def test_applier_updates_notes():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        notes="Tiene una grieta en la montura.",
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.success
    assert result.changed

    assert (
        world.item_instances[100].notes
        == "Tiene una grieta en la montura."
    )

def test_applier_updates_active():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        active=False,
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.success
    assert result.changed

    assert world.item_instances[100].active is False

def test_applier_updates_multiple_fields():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        owner_id=2,
        location_id=2,
        condition="dañado",
        notes="Objeto recuperado de las ruinas.",
        active=False,
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.success
    assert result.changed

    instance = world.item_instances[100]

    assert instance.owner_id == 2
    assert instance.location_id == 2
    assert instance.condition == "dañado"
    assert (
        instance.notes
        == "Objeto recuperado de las ruinas."
    )
    assert instance.active is False

def test_applier_returns_not_found_for_unknown_instance():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=999,
        condition="dañado",
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.status == OperationStatus.NOT_FOUND

    assert 999 not in world.item_instances

    assert (
        world.item_instances[100].condition
        == "intacto"
    )

def test_applier_rejects_unknown_owner():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        owner_id=999,
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.status == OperationStatus.NOT_FOUND

    assert (
        world.item_instances[100].owner_id
        == 1
    )

def test_applier_rejects_unknown_location():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        location_id=999,
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.status == OperationStatus.NOT_FOUND

    assert (
        world.item_instances[100].location_id
        == 3
    )

def test_applier_returns_no_change_when_state_is_already_equal():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        owner_id=1,
        location_id=3,
        condition="intacto",
        notes="Guardado en una bolsa.",
        active=True,
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.success
    assert not result.changed
    assert result.status == OperationStatus.NO_CHANGE

def test_parser_accepts_update_item_instance():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "update_item_instance",
                    "instance_id": 100,
                    "owner_id": 2,
                    "location_id": 3,
                    "condition": "dañado",
                    "notes": "Grieta visible.",
                    "active": True,
                }
            ]
        }
    )

    assert len(operations) == 1

    operation = operations[0]

    assert isinstance(
        operation,
        UpdateItemInstanceOperation,
    )

    assert operation.instance_id == 100
    assert operation.owner_id == 2
    assert operation.location_id == 3
    assert operation.condition == "dañado"
    assert operation.notes == "Grieta visible."
    assert operation.active is True

def test_parser_accepts_update_item_instance_references():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "update_item_instance",
                    "instance_id": "$instance",
                    "owner_id": "$npc",
                    "location_id": "$location",
                }
            ]
        }
    )

    operation = operations[0]

    assert isinstance(
        operation,
        UpdateItemInstanceOperation,
    )

    assert isinstance(
        operation.instance_id,
        OperationReference,
    )

    assert operation.instance_id.name == "instance"

    assert isinstance(
        operation.owner_id,
        OperationReference,
    )

    assert operation.owner_id.name == "npc"

    assert isinstance(
        operation.location_id,
        OperationReference,
    )

    assert operation.location_id.name == "location"

def test_parser_accepts_partial_update():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "update_item_instance",
                    "instance_id": 100,
                    "condition": "roto",
                }
            ]
        }
    )

    operation = operations[0]

    assert operation.instance_id == 100
    assert operation.condition == "roto"

    assert operation.owner_id is _UNSET
    assert operation.location_id is _UNSET
    assert operation.notes is _UNSET
    assert operation.active is _UNSET

def test_parser_rejects_unknown_field():
    parser = OperationParser()

    with pytest.raises(OperationParseError):
        parser.parse(
            {
                "operations": [
                    {
                        "type": "update_item_instance",
                        "instance_id": 100,
                        "unknown": "value",
                    }
                ]
            }
        )

def test_create_item_instance_accepts_references():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "create_item_instance",
                    "item_id": "$sword",
                    "instance_number": 1,
                    "owner_id": "$npc",
                    "location_id": "$location",
                }
            ]
        }
    )

    operation = operations[0]

    assert isinstance(
        operation,
        CreateItemInstanceOperation,
    )

    assert isinstance(
        operation.item_id,
        OperationReference,
    )

    assert operation.item_id.name == "sword"

    assert isinstance(
        operation.owner_id,
        OperationReference,
    )

    assert operation.owner_id.name == "npc"

    assert isinstance(
        operation.location_id,
        OperationReference,
    )

    assert operation.location_id.name == "location"

def test_applier_clears_owner_with_none():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        owner_id=None,
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.success
    assert result.changed
    assert world.item_instances[100].owner_id is None

def test_applier_clears_location_with_none():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        location_id=None,
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.success
    assert result.changed
    assert world.item_instances[100].location_id is None

def test_applier_does_not_modify_omitted_fields():
    world = build_world()

    operation = UpdateItemInstanceOperation(
        instance_id=100,
        condition="dañado",
    )

    result = WorldApplier().apply(
        world,
        operation,
    )

    assert result.success
    assert result.changed

    instance = world.item_instances[100]

    assert instance.owner_id == 1
    assert instance.location_id == 3
    assert instance.condition == "dañado"

def test_parser_distinguishes_missing_from_null():
    parser = OperationParser()

    operations = parser.parse(
        {
            "operations": [
                {
                    "type": "update_item_instance",
                    "instance_id": 100,
                },
                {
                    "type": "update_item_instance",
                    "instance_id": 100,
                    "owner_id": None,
                    "location_id": None,
                },
            ]
        }
    )

    omitted = operations[0]
    explicit_null = operations[1]

    assert omitted.owner_id is _UNSET
    assert omitted.location_id is _UNSET
    assert omitted.condition is _UNSET
    assert omitted.notes is _UNSET
    assert omitted.active is _UNSET

    assert explicit_null.owner_id is None
    assert explicit_null.location_id is None