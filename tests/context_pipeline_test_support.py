"""Shared fixture builders for context-pipeline contract tests."""

from models.entity import Entity
from models.relation import Relation
from models.world_state import WorldState


def make_entity(
    entity_id: int,
    name: str,
    entity_type: str = "character",
    description: str = "",
    active: bool = True,
) -> Entity:
    return Entity(
        id=entity_id,
        name=name,
        entity_type=entity_type,
        description=description,
        active=active,
    )


def make_relation(
    relation_id: int,
    subject_id: int,
    target_id: int,
    relation_type: str = "knows",
    active: bool = True,
    metadata: dict | None = None,
) -> Relation:
    return Relation(
        id=relation_id,
        subject_id=subject_id,
        target_id=target_id,
        relation_type=relation_type,
        active=active,
        metadata=metadata or {},
    )


def make_world() -> WorldState:
    world = WorldState()
    world.entities = {
        1: make_entity(1, "Fungoso", description="Un aventurero solitario."),
        2: make_entity(2, "Aldric", entity_type="npc", description="Un viejo mercader."),
    }
    world.relations = {
        1: make_relation(1, 1, 2, relation_type="friend"),
    }
    return world


def make_complex_world() -> WorldState:
    world = WorldState()
    world.entities = {
        1: make_entity(1, "Fungoso", description="Aventurero protagonista."),
        2: make_entity(2, "Aldric", entity_type="npc", description="Mercader y viejo amigo."),
        3: make_entity(3, "Morth", entity_type="npc", description="Rival peligroso."),
        4: make_entity(4, "Vera", entity_type="npc", description="Una guardia local."),
        5: make_entity(5, "Fantasma", entity_type="creature", description="Una criatura olvidada."),
        6: make_entity(6, "Inactivo", entity_type="npc", description="No debería aparecer.", active=False),
    }
    world.relations = {
        1: make_relation(1, 1, 2, relation_type="friend"),
        2: make_relation(2, 1, 3, relation_type="enemy"),
        3: make_relation(3, 2, 4, relation_type="knows"),
        4: make_relation(4, 1, 6, relation_type="friend"),
        5: make_relation(5, 1, 5, relation_type="knows", active=False),
    }
    return world
