from models.entity import Entity
from models.operation_result import OperationStatus
from models.world_state import WorldState
from operations.world_operations import CreateEntityOperation, UpdateEntityOperation
from services.world.world_entity_applier import WorldEntityApplier


def build_world():
    return WorldState(
        entities={
            4: Entity(id=4, name="Aldric", entity_type="npc"),
        }
    )


def test_create_entity_allocates_next_id_and_preserves_fields():
    world = build_world()

    result = WorldEntityApplier().apply(
        world,
        CreateEntityOperation(
            name="Mara",
            entity_type="npc",
            description="Exploradora",
            notes="Conoce el bosque",
            active=False,
        ),
    )

    assert result.status == OperationStatus.SUCCESS
    assert result.data == {"entity_id": 5}
    assert world.entities[5].name == "Mara"
    assert world.entities[5].description == "Exploradora"
    assert world.entities[5].notes == "Conoce el bosque"
    assert world.entities[5].active is False


def test_create_entity_rejects_blank_and_duplicate_names():
    world = build_world()
    applier = WorldEntityApplier()

    blank = applier.apply(world, CreateEntityOperation(name="   "))
    duplicate = applier.apply(world, CreateEntityOperation(name="alDRIC"))

    assert blank.status == OperationStatus.INVALID
    assert duplicate.status == OperationStatus.DUPLICATE
    assert list(world.entities) == [4]


def test_update_entity_changes_only_requested_fields():
    world = build_world()

    result = WorldEntityApplier().apply(
        world,
        UpdateEntityOperation(entity_id=4, description="Nueva descripción"),
    )

    assert result.status == OperationStatus.SUCCESS
    assert result.data == {"entity_id": 4}
    assert world.entities[4].name == "Aldric"
    assert world.entities[4].description == "Nueva descripción"


def test_update_entity_rejects_duplicate_name_without_mutation():
    world = build_world()
    world.entities[8] = Entity(id=8, name="Mara", entity_type="npc")

    result = WorldEntityApplier().apply(
        world,
        UpdateEntityOperation(entity_id=4, name="mara", description="No aplicar"),
    )

    assert result.status == OperationStatus.DUPLICATE
    assert world.entities[4].name == "Aldric"
    assert world.entities[4].description == ""


def test_update_entity_returns_no_change_for_identical_state():
    world = build_world()

    result = WorldEntityApplier().apply(
        world,
        UpdateEntityOperation(entity_id=4, name="Aldric"),
    )

    assert result.status == OperationStatus.NO_CHANGE
