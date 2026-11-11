import pytest

from models.entity import Entity
from models.relation import Relation
from models.world_state import WorldState
from operations.world_operations import (
    CreateRelationOperation,
    UpdateRelationOperation,
)
from services.llm_world.operation_parser import OperationParseError, OperationParser
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
                name="Elric",
                entity_type="character",
            ),
            3: Entity(
                id=3,
                name="Morgath",
                entity_type="character",
            ),
        },
        relations={
            "rel-1": Relation(
                id="rel-1",
                subject_id=1,
                relation_type="friend",
                target_id=2,
                metadata={
                    "reason": "old companions"
                },
            )
        },
    )


def test_create_relation():

    world = build_world()

    operation = CreateRelationOperation(
        relation_id="rel-2",
        subject_id="1",
        relation_type="enemy",
        target_id="3",
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    assert "rel-2" in world.relations

    relation = world.relations["rel-2"]

    assert relation.subject_id == 1
    assert relation.relation_type == "enemy"
    assert relation.target_id == 3
    assert relation.active is True


def test_create_relation_with_metadata():

    world = build_world()

    operation = CreateRelationOperation(
        relation_id="rel-2",
        subject_id="1",
        relation_type="owes",
        target_id="2",
        metadata={
            "amount": 100,
            "reason": "debt",
        },
    )

    applier = WorldApplier()
    applier.apply(world, operation)

    relation = world.relations["rel-2"]

    assert relation.metadata == {
        "amount": 100,
        "reason": "debt",
    }


def test_create_relation_rejects_unknown_subject():

    world = build_world()

    operation = CreateRelationOperation(
        relation_id="rel-2",
        subject_id="999",
        relation_type="enemy",
        target_id="2",
    )

    WorldApplier().apply(world, operation)

    assert "rel-2" not in world.relations


def test_create_relation_rejects_unknown_target():

    world = build_world()

    operation = CreateRelationOperation(
        relation_id="rel-2",
        subject_id="1",
        relation_type="enemy",
        target_id="999",
    )

    WorldApplier().apply(world, operation)

    assert "rel-2" not in world.relations


def test_create_relation_rejects_duplicate_id():

    world = build_world()

    original = world.relations["rel-1"]

    operation = CreateRelationOperation(
        relation_id="rel-1",
        subject_id="1",
        relation_type="enemy",
        target_id="3",
    )

    WorldApplier().apply(world, operation)

    relation = world.relations["rel-1"]

    assert relation is original
    assert relation.relation_type == "friend"
    assert relation.target_id == 2


def test_create_relation_rejects_empty_relation_type():

    world = build_world()

    operation = CreateRelationOperation(
        relation_id="rel-2",
        subject_id="1",
        relation_type="",
        target_id="2",
    )

    WorldApplier().apply(world, operation)

    assert "rel-2" not in world.relations


def test_update_relation_type():

    world = build_world()

    operation = UpdateRelationOperation(
        relation_id="rel-1",
        relation_type="enemy",
    )

    WorldApplier().apply(world, operation)

    relation = world.relations["rel-1"]

    assert relation.relation_type == "enemy"
    assert relation.target_id == 2


def test_update_relation_target():

    world = build_world()

    operation = UpdateRelationOperation(
        relation_id="rel-1",
        target_id="3",
    )

    WorldApplier().apply(world, operation)

    relation = world.relations["rel-1"]

    assert relation.target_id == 3
    assert relation.relation_type == "friend"


def test_update_relation_metadata():

    world = build_world()

    operation = UpdateRelationOperation(
        relation_id="rel-1",
        metadata={
            "reason": "betrayal"
        },
    )

    WorldApplier().apply(world, operation)

    assert world.relations["rel-1"].metadata == {
        "reason": "betrayal"
    }


def test_update_relation_active():

    world = build_world()

    operation = UpdateRelationOperation(
        relation_id="rel-1",
        active=False,
    )

    WorldApplier().apply(world, operation)

    assert world.relations["rel-1"].active is False


def test_update_relation_rejects_unknown_relation():

    world = build_world()

    operation = UpdateRelationOperation(
        relation_id="does-not-exist",
        relation_type="enemy",
    )

    WorldApplier().apply(world, operation)

    assert len(world.relations) == 1


def test_update_relation_rejects_unknown_target():

    world = build_world()

    operation = UpdateRelationOperation(
        relation_id="rel-1",
        target_id="999",
    )

    WorldApplier().apply(world, operation)

    relation = world.relations["rel-1"]

    assert relation.target_id == 2

def test_create_relation_rejects_invalid_subject_id():
    world = build_world()

    operation = CreateRelationOperation(
        relation_id="rel-invalid",
        subject_id="abc",
        relation_type="enemy",
        target_id="2",
    )

    WorldApplier().apply(world, operation)

    assert "rel-invalid" not in world.relations


def test_create_relation_rejects_invalid_target_id():
    world = build_world()

    operation = CreateRelationOperation(
        relation_id="rel-invalid",
        subject_id="1",
        relation_type="enemy",
        target_id="abc",
    )

    WorldApplier().apply(world, operation)

    assert "rel-invalid" not in world.relations


def test_create_relation_rejects_none_subject_id():
    world = build_world()

    operation = CreateRelationOperation(
        relation_id="rel-invalid",
        subject_id=None,
        relation_type="enemy",
        target_id="2",
    )

    WorldApplier().apply(world, operation)

    assert "rel-invalid" not in world.relations


def test_create_relation_rejects_none_target_id():
    world = build_world()

    operation = CreateRelationOperation(
        relation_id="rel-invalid",
        subject_id="1",
        relation_type="enemy",
        target_id=None,
    )

    WorldApplier().apply(world, operation)

    assert "rel-invalid" not in world.relations


def test_create_relation_does_not_modify_world_on_invalid_subject():
    world = build_world()

    original_relations = dict(world.relations)

    operation = CreateRelationOperation(
        relation_id="rel-invalid",
        subject_id="abc",
        relation_type="enemy",
        target_id="2",
    )

    WorldApplier().apply(world, operation)

    assert world.relations == original_relations


def test_create_relation_does_not_modify_world_on_invalid_target():
    world = build_world()

    original_relations = dict(world.relations)

    operation = CreateRelationOperation(
        relation_id="rel-invalid",
        subject_id="1",
        relation_type="enemy",
        target_id="abc",
    )

    WorldApplier().apply(world, operation)

    assert world.relations == original_relations


def test_update_relation_rejects_invalid_target_id():
    world = build_world()

    original_target = world.relations["rel-1"].target_id

    operation = UpdateRelationOperation(
        relation_id="rel-1",
        target_id="abc",
    )

    WorldApplier().apply(world, operation)

    assert world.relations["rel-1"].target_id == original_target


def test_update_relation_rejects_none_target_id():
    world = build_world()

    original_target = world.relations["rel-1"].target_id

    operation = UpdateRelationOperation(
        relation_id="rel-1",
        target_id=None,
    )

    WorldApplier().apply(world, operation)

    assert world.relations["rel-1"].target_id == original_target


def test_update_relation_keeps_existing_values_when_not_provided():
    world = build_world()

    relation = world.relations["rel-1"]

    operation = UpdateRelationOperation(
        relation_id="rel-1",
    )

    WorldApplier().apply(world, operation)

    assert relation.relation_type == "friend"
    assert relation.target_id == 2
    assert relation.metadata == {
        "reason": "old companions"
    }
    assert relation.active is True


def test_update_relation_can_update_multiple_fields():
    world = build_world()

    operation = UpdateRelationOperation(
        relation_id="rel-1",
        relation_type="enemy",
        target_id="3",
        metadata={
            "reason": "betrayal"
        },
        active=False,
    )

    WorldApplier().apply(world, operation)

    relation = world.relations["rel-1"]

    assert relation.relation_type == "enemy"
    assert relation.target_id == 3
    assert relation.metadata == {
        "reason": "betrayal"
    }
    assert relation.active is False

def test_create_relation_accepts_string_entity_ids():
    parser = OperationParser()

    operations = parser.parse({
        "operations": [
            {
                "type": "create_relation",
                "relation_id": "rel-1",
                "subject_id": "1",
                "relation_type": "enemy",
                "target_id": "2",
            }
        ]
    })

    operation = operations[0]

    assert operation.subject_id == 1
    assert operation.target_id == 2
    assert isinstance(operation.subject_id, int)
    assert isinstance(operation.target_id, int)

def test_create_relation_rejects_invalid_entity_id():
    parser = OperationParser()

    with pytest.raises(OperationParseError):
        parser.parse({
            "operations": [
                {
                    "type": "create_relation",
                    "relation_id": "rel-1",
                    "subject_id": "Fungoso",
                    "relation_type": "enemy",
                    "target_id": "2",
                }
            ]
        })

def test_parser_does_not_validate_entity_existence():
    parser = OperationParser()

    operations = parser.parse({
        "operations": [
            {
                "type": "create_relation",
                "relation_id": "rel-1",
                "subject_id": "999",
                "relation_type": "enemy",
                "target_id": "888",
            }
        ]
    })

    assert len(operations) == 1