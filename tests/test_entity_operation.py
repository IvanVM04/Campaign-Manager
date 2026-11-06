from models.world_state import WorldState
from operations.operation_reference import OperationReference
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import CreateEntityOperation, UpdateEntityOperation
from services.world_applier import WorldApplier
from services.world import WorldService


def test_create_entity():
    world = WorldState()
    applier = WorldApplier()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Un minero viejo.",
        notes="Sabe algo sobre las desapariciones.",
    )

    applier.apply(world, operation)

    assert len(world.entities) == 1

    entity = world.entities[1]

    assert entity.id == 1
    assert entity.name == "Aldric"
    assert entity.entity_type == "npc"
    assert entity.description == "Un minero viejo."
    assert entity.notes == "Sabe algo sobre las desapariciones."
    assert entity.active is True

def test_create_entity_generates_next_id():
    world = WorldState()

    applier = WorldApplier()

    first = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
    )

    second = CreateEntityOperation(
        name="Mara",
        entity_type="npc",
    )

    applier.apply(world, first)
    applier.apply(world, second)

    assert len(world.entities) == 2

    assert world.entities[1].name == "Aldric"
    assert world.entities[2].name == "Mara"

def test_create_entity_does_not_create_duplicate():
    world = WorldState()
    applier = WorldApplier()

    first = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
    )

    duplicate = CreateEntityOperation(
        name="aldric",
        entity_type="npc",
    )

    applier.apply(world, first)
    applier.apply(world, duplicate)

    assert len(world.entities) == 1
    assert world.entities[1].name == "Aldric"

def test_create_entity_returns_generated_id():
    world = WorldState()
    applier = WorldApplier()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
    )

    result = applier.apply(
        world,
        operation,
    )

    assert result.success is True
    assert result.data == {
        "entity_id": 1,
    }

def test_create_entity_reference_uses_generated_id():
    service = WorldService()

    result = service.apply_operations(
        [
            ReferencedOperation(
                operation=CreateEntityOperation(
                    name="Aldric",
                    entity_type="npc",
                ),
                ref="npc",
            ),
            UpdateEntityOperation(
                entity_id=OperationReference("npc"),
                description="Descripción actualizada.",
            ),
        ]
    )

    assert result.success is True
    assert result.changed is True

    world = service.get_world()

    entity = world.entities[1]

    assert entity.name == "Aldric"
    assert entity.description == "Descripción actualizada."