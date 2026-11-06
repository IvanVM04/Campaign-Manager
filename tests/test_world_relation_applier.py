from models.entity import Entity
from models.operation_result import OperationStatus
from models.world_state import WorldState
from operations.world_operations import (
    CreateRelationOperation,
    RemoveRelationOperation,
    UpdateRelationOperation,
)
from services.world import WorldRelationApplier


def build_world():
    return WorldState(
        entities={
            1: Entity(id=1, name="Fungoso", entity_type="character"),
            2: Entity(id=2, name="Neria", entity_type="character"),
        },
        relations={},
    )


def test_create_relation_applies_validated_relationship():
    world = build_world()
    operation = CreateRelationOperation(
        relation_id="relation-1",
        subject_id=1,
        relation_type="ALLIED_WITH",
        target_id=2,
    )

    result = WorldRelationApplier().apply(world, operation)

    assert result.status == OperationStatus.SUCCESS
    assert world.relations["relation-1"].subject_id == 1
    assert world.relations["relation-1"].target_id == 2


def test_update_relation_changes_only_requested_fields():
    world = build_world()
    create = CreateRelationOperation(
        relation_id="relation-1",
        subject_id=1,
        relation_type="ALLIED_WITH",
        target_id=2,
    )
    WorldRelationApplier().apply(world, create)

    result = WorldRelationApplier().apply(
        world,
        UpdateRelationOperation(
            relation_id="relation-1",
            relation_type="HOSTILE_TO",
            active=False,
        ),
    )

    assert result.status == OperationStatus.SUCCESS
    assert world.relations["relation-1"].relation_type == "HOSTILE_TO"
    assert world.relations["relation-1"].active is False


def test_remove_relation_deactivates_without_deleting_it():
    world = build_world()
    WorldRelationApplier().apply(
        world,
        CreateRelationOperation(
            relation_id="relation-1",
            subject_id=1,
            relation_type="ALLIED_WITH",
            target_id=2,
        ),
    )

    result = WorldRelationApplier().apply(
        world,
        RemoveRelationOperation(relation_id="relation-1"),
    )

    assert result.status == OperationStatus.SUCCESS
    assert "relation-1" in world.relations
    assert world.relations["relation-1"].active is False
