from services.world.world_serializer import WorldSerializer


def test_world_serializer_serializes_dataclass():
    # Usa aquí una entidad real de tu modelo.
    #
    # Ajusta los argumentos al constructor actual de Entity.
    from models.entity import Entity

    entity = Entity(
        id=1,
        name="Fungoso",
        entity_type="npc",
        description="Un goblin cubierto de hongos.",
    )

    result = WorldSerializer.entity_to_dict(
        entity
    )

    assert result["id"] == 1
    assert result["name"] == "Fungoso"

def test_world_serializer_serializes_relation():
    from models.relation import Relation

    relation = Relation(
        id="fungoso-goblin",
        subject_id=1,
        relation_type="enemy_of",
        target_id=2,
    )

    result = WorldSerializer.relation_to_dict(
        relation
    )

    assert result["id"] == "fungoso-goblin"
    assert result["subject_id"] == 1
    assert result["target_id"] == 2