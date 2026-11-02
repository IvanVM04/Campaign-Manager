import pytest

from models.entity import Entity
from models.relation import Relation
from models.world_state import WorldState
from operations.world_operations import (
    CreateEntityOperation,
    UpdateEntityOperation,
)
from services.operation_parser import (
    OperationParseError,
    OperationParser,
)
from services.world_applier import WorldApplier
from services.world_service import WorldService


class InMemoryRepository:
    """
    Repository mínimo para probar el flujo completo sin tocar SQLite.

    Queremos probar:

        JSON
        -> OperationParser
        -> WorldService
        -> WorldApplier
        -> WorldState

    La persistencia SQLite ya está cubierta por test_world_repository.py.
    """

    def __init__(self, world=None):
        self.world = world if world is not None else WorldState()
        self.saved_world = None
        self.load_calls = 0
        self.save_calls = 0

    def load_world(self, **kwargs):
        self.load_calls += 1
        return self.world

    def save_world(self, world, **kwargs):
        self.save_calls += 1
        self.saved_world = world



def build_world():
    """
    Mundo mínimo utilizado por los tests de integración.
    """

    fungoso = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
        description="Un aventurero peculiar.",
        notes="Le gusta el oro.",
        active=True,
    )

    goblin = Entity(
        id=2,
        name="Goblin",
        entity_type="creature",
        description="Un goblin hostil.",
        notes="Vive cerca de la mina.",
        active=True,
    )

    return WorldState(
        entities={
            fungoso.id: fungoso,
            goblin.id: goblin,
        }
    )


def build_service():
    """
    Construye el WorldService REAL usando:

    - Repository en memoria.
    - WorldApplier REAL.

    No usamos FakeApplier porque aquí queremos comprobar
    que la operación realmente modifica el WorldState.
    """

    repository = InMemoryRepository(build_world())

    service = WorldService(
        repository=repository,
        applier=WorldApplier(),
    )

    service.load()

    return service, repository


def parse_and_apply(service, payload):
    """
    Simula exactamente el punto de entrada de SillyTavern:

        JSON -> parser -> operaciones -> WorldService
    """

    parser = OperationParser()

    operations = parser.parse(payload)

    for operation in operations:
        service.apply(operation)

    return operations


# ---------------------------------------------------------------------------
# CREATE RELATION
# ---------------------------------------------------------------------------


def test_sillytavern_create_relation_full_pipeline():
    """
    Simula una respuesta de SillyTavern con una operación para crear
    una relación entre Fungoso y el Goblin.

    Importante:
    SillyTavern manda los IDs como strings.

        "subject_id": "1"
        "target_id": "2"

    El parser debe normalizarlos a int.

    Después WorldApplier debe crear realmente la relación.
    """

    service, repository = build_service()

    payload = {
        "operations": [
            {
                "type": "create_relation",
                "relation_id": "fungoso-goblin",
                "subject_id": "1",
                "relation_type": "enemy_of",
                "target_id": "2",
                "metadata": {
                    "reason": "Intentó robarle",
                    "strength": 80,
                },
            }
        ]
    }

    operations = parse_and_apply(service, payload)

    # ------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------

    assert len(operations) == 1

    operation = operations[0]

    assert operation.subject_id == 1
    assert isinstance(operation.subject_id, int)

    assert operation.target_id == 2
    assert isinstance(operation.target_id, int)

    # ------------------------------------------------------------
    # WorldState
    # ------------------------------------------------------------

    assert "fungoso-goblin" in service.world.relations

    relation = service.world.relations["fungoso-goblin"]

    assert isinstance(relation, Relation)

    assert relation.id == "fungoso-goblin"
    assert relation.subject_id == 1
    assert relation.target_id == 2
    assert relation.relation_type == "enemy_of"

    assert relation.metadata == {
        "reason": "Intentó robarle",
        "strength": 80,
    }

    assert relation.active is True

    # ------------------------------------------------------------
    # No debería haber persistencia automática
    # ------------------------------------------------------------

    assert repository.save_calls == 0


# ---------------------------------------------------------------------------
# CREATE RELATION + SAVE
# ---------------------------------------------------------------------------


def test_sillytavern_create_relation_and_persist():
    """
    Comprueba el flujo completo incluyendo persistencia:

        JSON
        -> Parser
        -> WorldService.apply()
        -> WorldService.save()
        -> Repository
    """

    service, repository = build_service()

    parser = OperationParser()

    payload = {
        "operations": [
            {
                "type": "create_relation",
                "relation_id": "fungoso-goblin",
                "subject_id": "1",
                "relation_type": "enemy_of",
                "target_id": "2",
            }
        ]
    }

    operations = parser.parse(payload)

    assert len(operations) == 1

    result = service.apply(
        operations[0]
    )

    assert result.success

    service.save()

    # La operación modificó el mundo.
    assert "fungoso-goblin" in service.world.relations

    # Y se guardó.
    assert repository.save_calls == 1
    assert repository.saved_world is service.world


# ---------------------------------------------------------------------------
# MULTIPLE OPERATIONS
# ---------------------------------------------------------------------------


def test_sillytavern_can_send_multiple_operations():
    """
    SillyTavern puede devolver varias operaciones en una única respuesta.

    Todas deben pasar por el parser y después aplicarse al mismo mundo.
    """

    service, repository = build_service()

    payload = {
        "operations": [
            {
                "type": "create_relation",
                "relation_id": "fungoso-goblin",
                "subject_id": "1",
                "relation_type": "enemy_of",
                "target_id": "2",
            },
            {
                "type": "create_event",
                "event_id": "event-001",
                "event_type": "discovery",
                "title": "Una presencia inquietante",
                "description": "Fungoso descubre huellas de goblin.",
                "consequences": "Ahora sabe que hay goblins cerca.",
                "session_id": 1,
                "secret": False,
                "metadata": {
                    "location": "mina",
                    "importance": "medium",
                },
            },
        ]
    }

    operations = parse_and_apply(service, payload)

    assert len(operations) == 2

    # Primera operación.
    assert "fungoso-goblin" in service.world.relations

    relation = service.world.relations["fungoso-goblin"]

    assert relation.subject_id == 1
    assert relation.target_id == 2
    assert relation.relation_type == "enemy_of"

    # Segunda operación.
    assert "event-001" in service.world.events

    event = service.world.events["event-001"]

    assert event.title == "Una presencia inquietante"
    assert event.session_id == 1
    assert event.secret is False

    # Ninguna operación debería haber guardado automáticamente.
    assert repository.save_calls == 0


# ---------------------------------------------------------------------------
# PARSER DOES NOT VALIDATE EXISTENCE
# ---------------------------------------------------------------------------


def test_parser_does_not_validate_entity_existence():
    """
    El parser NO debe conocer el WorldState.

    Por tanto puede convertir correctamente:

        "subject_id": "999"

    aunque la entidad 999 no exista.

    La operación es estructuralmente válida.

    La validación semántica corresponde a WorldApplier.
    """

    parser = OperationParser()

    payload = {
        "operations": [
            {
                "type": "create_relation",
                "relation_id": "invalid-relation",
                "subject_id": "999",
                "relation_type": "enemy_of",
                "target_id": "2",
            }
        ]
    }

    operations = parser.parse(payload)

    assert len(operations) == 1

    operation = operations[0]

    assert operation.subject_id == 999
    assert operation.target_id == 2


# ---------------------------------------------------------------------------
# INVALID ENTITY IS REJECTED BY WORLD LAYER
# ---------------------------------------------------------------------------


def test_world_layer_rejects_relation_with_unknown_entity():
    """
    Aquí comprobamos la separación de responsabilidades.

    El parser acepta el ID porque su trabajo es estructural.

    Pero WorldApplier NO debe crear una relación cuyo sujeto no existe.
    """

    service, repository = build_service()

    payload = {
        "operations": [
            {
                "type": "create_relation",
                "relation_id": "invalid-relation",
                "subject_id": "999",
                "relation_type": "enemy_of",
                "target_id": "2",
            }
        ]
    }

    operations = OperationParser().parse(payload)

    assert len(operations) == 1

    service.apply(operations[0])

    # La relación NO debe aparecer.
    assert "invalid-relation" not in service.world.relations

    # El mundo sigue teniendo únicamente las entidades originales.
    assert set(service.world.entities.keys()) == {1, 2}

    # No se ha guardado nada automáticamente.
    assert repository.save_calls == 0


# ---------------------------------------------------------------------------
# INVALID JSON NEVER REACHES WORLD
# ---------------------------------------------------------------------------


def test_invalid_sillytavern_payload_never_reaches_world():
    """
    Un JSON inválido debe detenerse en OperationParser.

    WorldService no debe recibir ninguna operación.
    """

    service, repository = build_service()

    invalid_payload = {
        "operations": [
            {
                "type": "create_relation",
                "relation_id": "broken",
                "subject_id": "not-an-id",
                "relation_type": "enemy_of",
                "target_id": "2",
            }
        ]
    }

    parser = OperationParser()

    with pytest.raises(OperationParseError):
        parser.parse(invalid_payload)

    # No se ha modificado el mundo.
    assert service.world.relations == {}

    # Tampoco se ha guardado.
    assert repository.save_calls == 0


# ---------------------------------------------------------------------------
# WORLD PERSISTENCE BOUNDARY
# ---------------------------------------------------------------------------


def test_apply_then_save_is_explicit():
    """
    Documenta una decisión importante de arquitectura:

        service.apply()
            -> modifica memoria

        service.save()
            -> persiste

    El apply NO debe guardar automáticamente.
    """

    service, repository = build_service()

    payload = {
        "operations": [
            {
                "type": "create_relation",
                "relation_id": "fungoso-goblin",
                "subject_id": "1",
                "relation_type": "enemy_of",
                "target_id": "2",
            }
        ]
    }

    operation = OperationParser().parse(payload)[0]

    # Primero solamente memoria.
    service.apply(operation)

    assert "fungoso-goblin" in service.world.relations
    assert repository.save_calls == 0

    # Después persistencia explícita.
    service.save()

    assert repository.save_calls == 1
    assert repository.saved_world is service.world

def test_create_entity_and_persist():
    service = WorldService()

    service.load()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Un minero viejo.",
        notes="Sabe algo sobre las desapariciones.",
    )

    service.apply(operation)
    service.save()

    # Simulamos una nueva instancia del servicio.
    new_service = WorldService()
    world = new_service.load()

    entity = next(
        entity
        for entity in world.entities.values()
        if entity.name == "Aldric"
    )

    assert entity.entity_type == "npc"
    assert entity.description == "Un minero viejo."
    assert entity.notes == "Sabe algo sobre las desapariciones."
    assert entity.active is True

def test_create_entity_generates_next_id():
    world = WorldState(
        entities={
            1: Entity(
                id=1,
                name="Fungoso",
                entity_type="character",
                description="",
                notes="",
                active=True,
            ),
            4: Entity(
                id=4,
                name="Goblin",
                entity_type="creature",
                description="",
                notes="",
                active=True,
            ),
        }
    )

    service = WorldService(
        repository=InMemoryRepository(world),
        applier=WorldApplier(),
    )

    service.load()

    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Un minero viejo.",
        notes="",
    )

    service.apply(operation)

    assert 5 in service.world.entities
    assert service.world.entities[5].name == "Aldric"

def test_update_entity_changes_only_requested_fields():
    world = WorldState(
        entities={
            1: Entity(
                id=1,
                name="Aldric",
                entity_type="npc",
                description="Un minero viejo.",
                notes="Sabe algo sobre la mina.",
                active=True,
            )
        }
    )

    service = WorldService(
        repository=InMemoryRepository(world),
        applier=WorldApplier(),
    )

    service.load()

    operation = UpdateEntityOperation(
        entity_id=1,
        description="Ahora está herido.",
    )

    service.apply(operation)

    entity = service.world.entities[1]

    assert entity.name == "Aldric"
    assert entity.entity_type == "npc"
    assert entity.description == "Ahora está herido."
    assert entity.notes == "Sabe algo sobre la mina."
    assert entity.active is True


def test_update_entity_changes_multiple_fields():
    world = WorldState(
        entities={
            1: Entity(
                id=1,
                name="Aldric",
                entity_type="npc",
                description="Un minero viejo.",
                notes="",
                active=True,
            )
        }
    )

    service = WorldService(
        repository=InMemoryRepository(world),
        applier=WorldApplier(),
    )

    service.load()

    operation = UpdateEntityOperation(
        entity_id=1,
        name="Aldric el Herido",
        entity_type="character",
        description="Está gravemente herido.",
        notes="Ya no puede trabajar.",
        active=False,
    )

    service.apply(operation)

    entity = service.world.entities[1]

    assert entity.name == "Aldric el Herido"
    assert entity.entity_type == "character"
    assert entity.description == "Está gravemente herido."
    assert entity.notes == "Ya no puede trabajar."
    assert entity.active is False


def test_update_entity_ignores_unknown_entity():
    world = WorldState()

    service = WorldService(
        repository=InMemoryRepository(world),
        applier=WorldApplier(),
    )

    service.load()

    operation = UpdateEntityOperation(
        entity_id=999,
        description="Esto no debería aplicarse.",
    )

    service.apply(operation)

    assert service.world.entities == {}