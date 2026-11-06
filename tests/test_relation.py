from models.entity import Entity
from models.relation import Relation
from models.world_state import WorldState
from operations.world_operations import (
    CreateRelationOperation,
    RemoveRelationOperation,
    UpdateRelationOperation,
)
from services.world import WorldApplier


def build_world():
    return WorldState(
        entities={
            1: Entity(
                id=1,
                name="Fungoso",
                entity_type="character",
            ),
            2: Entity(
                id=2,
                name="Neria",
                entity_type="character",
            ),
        },
        relations={},
    )

def test_apply_create_relation():
    world = build_world()

    operation = CreateRelationOperation(
        relation_id="relation-1",
        subject_id=1,
        relation_type="ALLIED_WITH",
        target_id=2,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert "relation-1" in world.relations

    relation = world.relations["relation-1"]

    assert relation.id == "relation-1"
    assert relation.subject_id == 1
    assert relation.relation_type == "ALLIED_WITH"
    assert relation.target_id == 2
    assert relation.active is True


def test_apply_create_relation_rejects_unknown_subject():
    world = build_world()

    operation = CreateRelationOperation(
        relation_id="relation-1",
        subject_id=999,
        relation_type="ALLIED_WITH",
        target_id=2,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.relations == {}


def test_apply_create_relation_rejects_unknown_target():
    world = build_world()

    operation = CreateRelationOperation(
        relation_id="relation-1",
        subject_id=1,
        relation_type="ALLIED_WITH",
        target_id=999,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.relations == {}


def test_apply_create_relation_does_not_overwrite_existing_relation():
    world = build_world()

    world.relations["relation-1"] = Relation(
        id="relation-1",
        subject_id="1",
        relation_type="HATES",
        target_id="2",
    )

    operation = CreateRelationOperation(
        relation_id="relation-1",
        subject_id=1,
        relation_type="ALLIED_WITH",
        target_id=2,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    relation = world.relations["relation-1"]

    assert relation.relation_type == "HATES"


def test_apply_update_relation_metadata():
    world = build_world()

    world.relations["relation-1"] = Relation(
        id="relation-1",
        subject_id="1",
        relation_type="ALLIED_WITH",
        target_id="2",
        metadata={"strength": "weak"},
    )

    operation = UpdateRelationOperation(
        relation_id="relation-1",
        metadata={"strength": "strong"},
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    relation = world.relations["relation-1"]

    assert relation.metadata == {"strength": "strong"}


def test_apply_update_relation_active_state():
    world = build_world()

    world.relations["relation-1"] = Relation(
        id="relation-1",
        subject_id="1",
        relation_type="ALLIED_WITH",
        target_id="2",
        active=True,
    )

    operation = UpdateRelationOperation(
        relation_id="relation-1",
        active=False,
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.relations["relation-1"].active is False


def test_apply_remove_relation():
    world = build_world()

    world.relations["relation-1"] = Relation(
        id="relation-1",
        subject_id="1",
        relation_type="ALLIED_WITH",
        target_id="2",
        active=True,
    )

    operation = RemoveRelationOperation(
        relation_id="relation-1",
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert "relation-1" in world.relations
    assert world.relations["relation-1"].active is False


def test_apply_remove_relation_unknown_relation():
    world = build_world()

    operation = RemoveRelationOperation(
        relation_id="does-not-exist",
    )

    applier = WorldApplier()

    applier.apply(world, operation)

    assert world.relations == {}