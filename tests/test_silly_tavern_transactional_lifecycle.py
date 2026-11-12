# ruff: noqa: F401, I001

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

import pytest

import integrations.adapters.silly_tavern as integration_module
from models.campaign_scope import CampaignScope
from models.character_state import CharacterState
from models.entity import Entity
from models.schemas import (
    SillyTavernClarificationIn,
    SillyTavernContextIn,
    SillyTavernTurnIn,
)
from operations.world_operations import CreateEntityOperation
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from integrations.adapters.silly_tavern import (
    SillyTavernIntegrationService,
    SillyTavernIntegrationServiceConflictError,
)
from services.turns import TurnExecutionLock
from services.world import WorldService

from tests.silly_tavern_integration_support import _build_service, _compose_service

def test_e2e_silly_tavern_turn_persists_world_change(
    monkeypatch,
):
    """
    E2E del pipeline real de integración:

        SillyTavern narrative
            ↓
        LLMWorldExtractor
            ↓
        WorldOperation
            ↓
        WorldService
            ↓
        SQLite
            ↓
        TurnRepository

    El extractor está controlado para que el test sea
    determinista y no dependa de Ollama/LLM real.
    """

    from database import get_conn
    from repositories.campaign_repository import (
        CampaignRepository,
    )
    from repositories.character_repository import (
        CharacterRepository,
    )
    from repositories.entity_repository import (
        EntityRepository,
    )
    from repositories.turn_repository import (
        TurnRepository,
    )
    from services.campaign import (
        CampaignStateService,
    )
    from services.context import (
        ContextBuilder,
    )
    from services.llm_world import (
        LLMWorldExtractor,
    )
    from services.llm_world.operation_parser import (
        OperationParser,
    )
    from services.world import (
        WorldService,
    )

    # --------------------------------------------------------
    # Construir el pipeline real
    # --------------------------------------------------------

    world_service = WorldService()

    campaign_state_service = CampaignStateService(
        campaign_repository=CampaignRepository(),
        character_repository=CharacterRepository(),
        entity_repository=EntityRepository(),
        world_service=world_service,
    )

    context_builder = ContextBuilder()

    extractor = LLMWorldExtractor(
        provider=lambda prompt: '{"operations": []}',
        operation_parser=OperationParser(),
    )

    turn_repository = TurnRepository()

    service = _compose_service(
        campaign_state_service=campaign_state_service,
        context_builder=context_builder,
        extractor=extractor,
        world_service=world_service,
        turn_repository=turn_repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    # --------------------------------------------------------
    # Sustituimos SOLO la extracción LLM.
    #
    # El resto del pipeline es real.
    # --------------------------------------------------------

    created_entity_name = "La Cripta Antigua"

    def fake_extract(
        narrative,
        context,
    ):
        assert narrative == (
            "Aldren descubre una antigua cripta "
            "oculta bajo la montaña."
        )

        assert context is not None

        return [
            CreateEntityOperation(
                name=created_entity_name,
                entity_type="location",
                description=(
                    "Una antigua cripta oculta bajo la montaña."
                ),
            )
        ]

    monkeypatch.setattr(
        extractor,
        "extract",
        fake_extract,
    )

    # --------------------------------------------------------
    # Ejecutar el turno completo
    # --------------------------------------------------------

    result = service.process_turn(
        player_input=(
            "Busco un lugar donde refugiarme."
        ),
        narrative=(
            "Aldren descubre una antigua cripta "
            "oculta bajo la montaña."
        ),
        external_turn_id="e2e-test-turn-001",
        turn_version=1,
    )

    # --------------------------------------------------------
    # Comprobar resultado del turno
    # --------------------------------------------------------

    assert result.narrative == (
        "Aldren descubre una antigua cripta "
        "oculta bajo la montaña."
    )

    assert result.operation_count == 1
    assert result.successful_operation_count == 1
    assert result.failed_operation_count == 0
    assert result.all_operations_succeeded is True
    assert result.world_changed is True

    # --------------------------------------------------------
    # Comprobar WorldState en memoria
    # --------------------------------------------------------

    world = world_service.get_world()

    matching_entities = [
        entity
        for entity in world.entities.values()
        if entity.name == created_entity_name
    ]

    assert len(matching_entities) == 1

    entity = matching_entities[0]

    assert entity.entity_type == "location"
    assert entity.description == (
        "Una antigua cripta oculta bajo la montaña."
    )

    # --------------------------------------------------------
    # Comprobar que el cambio llegó realmente a SQLite
    #
    # No usamos WorldService aquí.
    # Leemos directamente desde el repositorio.
    # --------------------------------------------------------

    entity_repository = EntityRepository()

    persisted_entity = entity_repository.get_entity(
        entity.id,
        campaign_id=1,
    )

    assert persisted_entity is not None
    assert persisted_entity.id == entity.id
    assert persisted_entity.name == created_entity_name
    assert persisted_entity.entity_type == "location"
    assert persisted_entity.description == (
        "Una antigua cripta oculta bajo la montaña."
    )

    # --------------------------------------------------------
    # Comprobar que el TurnRecord también se persistió
    # --------------------------------------------------------

    persisted_turn = (
        turn_repository.get_active_by_external_turn_id(
            "e2e-test-turn-001",
        
            scope=CampaignScope(1),
        )
    )

    assert persisted_turn is not None

    assert persisted_turn.external_turn_id == (
        "e2e-test-turn-001"
    )

    assert persisted_turn.version == 1

    assert persisted_turn.player_input == (
        "Busco un lugar donde refugiarme."
    )

    assert persisted_turn.narrative == (
        "Aldren descubre una antigua cripta "
        "oculta bajo la montaña."
    )

    assert persisted_turn.operation_count == 1
    assert persisted_turn.successful_operation_count == 1
    assert persisted_turn.failed_operation_count == 0
    assert persisted_turn.world_changed is True

    # --------------------------------------------------------
    # Comprobación final independiente contra SQLite
    # --------------------------------------------------------

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                id,
                name,
                entity_type,
                description
            FROM entities
            WHERE id=?
            """,
            (entity.id,),
        ).fetchone()

    assert row is not None
    assert row["name"] == created_entity_name
    assert row["entity_type"] == "location"
    assert row["description"] == (
        "Una antigua cripta oculta bajo la montaña."
    )

def test_e2e_silly_tavern_turn_persists_character_hp_change(
    monkeypatch,
):
    from database import get_conn
    from models.character_state import CharacterState
    from models.entity import Entity
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )
    from repositories.campaign_repository import (
        CampaignRepository,
    )
    from repositories.character_repository import (
        CharacterRepository,
    )
    from repositories.entity_repository import (
        EntityRepository,
    )
    from repositories.turn_repository import (
        TurnRepository,
    )
    from services.campaign import (
        CampaignStateService,
    )
    from services.context import (
        ContextBuilder,
    )
    from services.llm_world import (
        LLMWorldExtractor,
    )
    from services.llm_world.operation_parser import (
        OperationParser,
    )
    from services.world import (
        WorldService,
    )

    entity_repository = EntityRepository()
    character_repository = CharacterRepository()
    campaign_repository = CampaignRepository()

    entity = entity_repository.save_entity(
        Entity(
            name="Aldren",
            entity_type="character",
            description="Aldren, aventurero.",
            notes="",
            active=True,
        ),
        campaign_id=1,
    )

    character = character_repository.save_character(
        CharacterState(
            entity_id=entity.id,
            level=1,
            class_name="Fighter",
            current_hp=10,
            max_hp=10,
            armor_class=16,
            strength=16,
            dexterity=12,
            constitution=14,
            intelligence=10,
            wisdom=10,
            charisma=10,
            proficiency_bonus=2,
            metadata={},
        ),
        campaign_id=1,
    )

    campaign_repository.update_active_character(
        campaign_id=1,
        character_id=character.entity_id,
    )

    world_service = WorldService()

    campaign_state_service = CampaignStateService(
        campaign_repository=campaign_repository,
        character_repository=character_repository,
        entity_repository=entity_repository,
        world_service=world_service,
    )

    extractor = LLMWorldExtractor(
        provider=lambda prompt: '{"operations": []}',
        operation_parser=OperationParser(),
    )

    turn_repository = TurnRepository()
    service = _compose_service(
        campaign_state_service=campaign_state_service,
        context_builder=ContextBuilder(),
        extractor=extractor,
        world_service=world_service,
        turn_repository=turn_repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    def fake_extract(narrative, context):
        assert context.active_character is not None
        assert context.active_character.entity_id == entity.id

        return [
            ChangeCharacterHpOperation(
                entity_id=entity.id,
                amount=-4,
            )
        ]

    monkeypatch.setattr(
        extractor,
        "extract",
        fake_extract,
    )

    result = service.process_turn(
        player_input="Sufro daño por una trampa.",
        narrative=(
            "Una trampa oculta alcanza a Aldren "
            "y le causa 4 puntos de daño."
        ),
        external_turn_id="e2e-hp-test-001",
        turn_version=1,
    )

    assert result.operation_count == 1
    assert result.successful_operation_count == 1
    assert result.failed_operation_count == 0
    assert result.all_operations_succeeded is True
    assert result.world_changed is True

    character_after = character_repository.get_character(
        entity.id,
        campaign_id=1,
    )

    assert character_after is not None
    assert character_after.current_hp == 6

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT current_hp
            FROM character_states
            WHERE entity_id = ?
            """,
            (entity.id,),
        ).fetchone()

    assert row is not None
    assert row["current_hp"] == 6

def test_world_service_rolls_back_all_operations_when_one_fails():
    from models.entity import Entity
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )
    from operations.world_operations import (
        CreateEntityOperation,
    )
    from repositories.character_repository import (
        CharacterRepository,
    )
    from repositories.entity_repository import (
        EntityRepository,
    )

    entity_repository = EntityRepository()
    character_repository = CharacterRepository()

    character_entity = entity_repository.save_entity(
        Entity(
            name="Aldren",
            entity_type="character",
            description="Aldren, aventurero.",
            notes="",
            active=True,
        ),
        campaign_id=1,
    )

    from models.character_state import CharacterState

    character_repository.save_character(
        CharacterState(
            entity_id=character_entity.id,
            current_hp=10,
            max_hp=10,
        ),
        campaign_id=1,
    )

    world_service = WorldService()

    world_service.load()

    initial_entity_count = len(
        world_service.get_world().entities
    )

    results = world_service.apply_turn_operations(
        world_operations=[
            CreateEntityOperation(
                name="Entidad temporal",
                entity_type="location",
            )
        ],
        character_operations=[
            ChangeCharacterHpOperation(
                entity_id=999999,
                amount=-4,
            )
        ],
        campaign_id=1,
    )

    assert len(results) == 2

    assert results[0].success
    assert not results[1].success

    assert len(
        world_service.get_world().entities
    ) == initial_entity_count

    assert all(
        entity.name != "Entidad temporal"
        for entity in world_service.get_world().entities.values()
    )

    world = world_service.get_world()

    assert len(world.entities) == initial_entity_count

    assert not any(
        entity.name == "Entidad temporal"
        for entity in world.entities.values()
    )

    character_after = (
        character_repository.get_character(
            character_entity.id,
            campaign_id=1,
        )
    )

    assert character_after is not None
    assert character_after.current_hp == 10

def test_e2e_turn_rolls_back_world_and_turn_when_operation_fails(
    monkeypatch,
):
    """
    Comprueba que un turno es completamente atómico.

    ```
    Si una operación válida modifica el mundo pero una operación
    posterior falla, ninguna modificación del turno debe quedar
    persistida en SQLite y no debe existir TurnRecord.

    Pipeline probado:

        extractor
            ↓
        WorldService
            ↓
        SQLite transaction
            ↓
        rollback

    El extractor está controlado para que el test sea determinista.
    """

    from database import get_conn
    from operations.world_operations import (
        CreateEntityOperation,
    )
    from repositories.campaign_repository import (
        CampaignRepository,
    )
    from repositories.character_repository import (
        CharacterRepository,
    )
    from repositories.entity_repository import (
        EntityRepository,
    )
    from repositories.turn_repository import (
        TurnRepository,
    )
    from services.campaign import (
        CampaignStateService,
    )
    from services.context import (
        ContextBuilder,
    )
    from services.llm_world import (
        LLMWorldExtractor,
    )
    from services.llm_world.operation_parser import (
        OperationParser,
    )
    from integrations.adapters.silly_tavern import (
        SillyTavernIntegrationServiceError,
    )
    from services.world import (
        WorldService,
    )

    # --------------------------------------------------------
    # Construir un pipeline completamente real.
    # --------------------------------------------------------

    world_service = WorldService()

    campaign_state_service = CampaignStateService(
        campaign_repository=CampaignRepository(),
        character_repository=CharacterRepository(),
        entity_repository=EntityRepository(),
        world_service=world_service,
    )

    context_builder = ContextBuilder()

    extractor = LLMWorldExtractor(
        provider=lambda prompt: '{"operations": []}',
        operation_parser=OperationParser(),
    )

    turn_repository = TurnRepository()

    service = _compose_service(
        campaign_state_service=campaign_state_service,
        context_builder=context_builder,
        extractor=extractor,
        world_service=world_service,
        turn_repository=turn_repository,
        turn_execution_lock=TurnExecutionLock(),
    )

    # --------------------------------------------------------
    # Las dos operaciones del turno.
    #
    # La primera es válida.
    # La segunda será inválida.
    # --------------------------------------------------------

    valid_operation = CreateEntityOperation(
        name="Entidad temporal",
        entity_type="npc",
        description="Esta entidad no debe sobrevivir al rollback.",
    )

    invalid_operation = CreateEntityOperation(
        name="Entidad inválida",
        entity_type="npc",
        description="Esta operación nunca debe persistirse.",
    )

    def fake_extract(narrative, context):
        return [
            valid_operation,
            invalid_operation,
        ]

    monkeypatch.setattr(
        extractor,
        "extract",
        fake_extract,
    )

    # --------------------------------------------------------
    # Forzamos el fallo de la segunda operación.
    #
    # La primera operación ya habrá sido aplicada cuando
    # la segunda provoque la excepción.
    # --------------------------------------------------------

    original_apply = world_service.apply_turn_operations

    def failing_apply(
        world_operations,
        character_operations,
        *,
        conn=None,
        ordered_operations=None,
    ):
        operations = tuple(ordered_operations)

        assert len(operations) == 2

        # Aplicamos únicamente la primera operación.
        original_apply(
            world_operations=(operations[0],),
            character_operations=(),
            conn=conn,
            ordered_operations=(operations[0],),
        )

        # Simulamos un fallo posterior dentro del mismo turno.
        raise RuntimeError(
            "forced failure after first operation"
        )

    monkeypatch.setattr(
        world_service,
        "apply_turn_operations",
        failing_apply,
    )

    # --------------------------------------------------------
    # Ejecutar el turno.
    #
    # process_turn debe convertir la excepción en el error
    # específico del servicio.
    # --------------------------------------------------------

    with pytest.raises(SillyTavernIntegrationServiceError):
        service.process_turn(
            external_turn_id="rollback-test-turn",
            turn_version=1,
            player_input="Haz aparecer dos entidades.",
            narrative="La primera entidad aparece, pero la segunda provoca un fallo.",
        )

    with get_conn() as conn:
        entity_row = conn.execute(
            """
            SELECT id
            FROM entities
            WHERE name = ?
            """,
            ("Entidad temporal",),
        ).fetchone()

        turn_row = conn.execute(
            """
            SELECT id
            FROM turns
            WHERE external_turn_id = ?
            """,
            ("rollback-test-turn",),
        ).fetchone()

    assert entity_row is None
    assert turn_row is None

def test_turn_persists_after_world_service_restart(
    client,
    monkeypatch,
):
    from database import get_conn
    from operations.world_operations import (
        CreateEntityOperation,
    )

    service = __import__("app").runtime_factory.get_runtime(1).silly_tavern_integration_service

    external_turn_id = "restart-persistence-test"

    created_entity_operation = CreateEntityOperation(
        name="NPC persistente",
        entity_type="npc",
        description="Debe sobrevivir al reinicio.",
    )

    monkeypatch.setattr(
        service.legacy_turn_service.extractor,
        "extract",
        lambda narrative, context: (
            [created_entity_operation]
            if narrative == "Narrativa persistente."
            else []
        ),
    )

    # =========================================================
    # 1. CREAR ESTADO
    # =========================================================

    response = client.post(
        "/integration/turn",
        json={
            "player_input": "Creo un NPC.",
            "narrative": "Narrativa persistente.",
            "external_turn_id": external_turn_id,
            "turn_version": 1,
        },
    )

    assert response.status_code == 200, (
        f"Turno inicial devolvió "
        f"{response.status_code}: "
        f"{response.text}"
    )

    data = response.json()

    assert data["turn_version"] == 1
    assert data["world_changed"] is True
    assert data["operation_count"] == 1
    assert data["successful_operation_count"] == 1
    assert data["failed_operation_count"] == 0
    assert data["all_operations_succeeded"] is True

    # =========================================================
    # 2. COMPROBAR QUE ESTÁ PERSISTIDO EN SQLITE
    # =========================================================

    with get_conn() as conn:
        entity_before = conn.execute(
            """
            SELECT
                id,
                name,
                entity_type,
                description,
                notes,
                active
            FROM entities
            WHERE name = ?
            """,
            ("NPC persistente",),
        ).fetchone()

        turn_before = conn.execute(
            """
            SELECT
                id,
                external_turn_id,
                version,
                status,
                snapshot
            FROM turns
            WHERE external_turn_id = ?
            """,
            (external_turn_id,),
        ).fetchone()

    assert entity_before is not None
    assert entity_before["name"] == "NPC persistente"
    assert entity_before["entity_type"] == "npc"
    assert entity_before["description"] == (
        "Debe sobrevivir al reinicio."
    )

    assert turn_before is not None
    assert turn_before["version"] == 1
    assert turn_before["status"] == "active"

    # =========================================================
    # 3. SIMULAR REINICIO DE LA APLICACIÓN
    # =========================================================

    app_module = __import__("app")
    app_module.runtime_factory.invalidate(1)
    restarted_world_service = (
        app_module.runtime_factory.get_runtime(1).world_service
    )

    # =========================================================
    # 4. COMPROBAR QUE EL WORLD STATE SE RECARGA DESDE SQLITE
    # =========================================================

    assert (
        restarted_world_service.world.entities
        is not None
    )

    assert any(
        entity.name == "NPC persistente"
        for entity in restarted_world_service.world.entities.values()
    )

    persisted_entity = next(
        entity
        for entity
        in restarted_world_service.world.entities.values()
        if entity.name == "NPC persistente"
    )

    assert persisted_entity.entity_type == "npc"
    assert persisted_entity.description == (
        "Debe sobrevivir al reinicio."
    )

    # =========================================================
    # 5. COMPROBAR DE NUEVO DIRECTAMENTE EN SQLITE
    # =========================================================

    with get_conn() as conn:
        entity_after = conn.execute(
            """
            SELECT
                id,
                name,
                entity_type,
                description,
                notes,
                active
            FROM entities
            WHERE name = ?
            """,
            ("NPC persistente",),
        ).fetchone()

        turn_after = conn.execute(
            """
            SELECT
                id,
                external_turn_id,
                version,
                status,
                snapshot
            FROM turns
            WHERE external_turn_id = ?
            """,
            (external_turn_id,),
        ).fetchone()

    assert dict(entity_after) == dict(entity_before)
    assert dict(turn_after) == dict(turn_before)

def test_silly_tavern_context_turn_context_e2e(
    client,
    monkeypatch,
):
    import app
    from operations.world_operations import (
        CreateEntityOperation,
    )

    service = app.runtime_factory.get_runtime(1).silly_tavern_integration_service

    created_entity_operation = CreateEntityOperation(
        name="NPC del contexto",
        entity_type="npc",
        description="NPC creado durante el turno.",
    )

    monkeypatch.setattr(
        service.legacy_turn_service.extractor,
        "extract",
        lambda narrative, context: (
            [created_entity_operation]
            if narrative == "Narrativa que crea un NPC."
            else []
        ),
    )

    # ========================================================
    # 1. CONTEXTO INICIAL
    # ========================================================

    response_before = client.post(
        "/integration/context",
        json={
            "query": "¿Qué hay a mi alrededor?",
        },
    )

    assert response_before.status_code == 200, (
        f"Contexto inicial devolvió "
        f"{response_before.status_code}: "
        f"{response_before.text}"
    )

    context_before = response_before.json()

    assert context_before["query"] == (
        "¿Qué hay a mi alrededor?"
    )

    assert "campaign" in context_before
    assert "session" in context_before
    assert "active_character" in context_before
    assert "context" in context_before

    # El NPC todavía no existe.
    assert "NPC del contexto" not in str(
        context_before["context"]
    )

    # ========================================================
    # 2. PROCESAR TURNO REAL
    # ========================================================

    response_turn = client.post(
        "/integration/turn",
        json={
            "player_input": "Busco a alguien en la taberna.",
            "narrative": "Narrativa que crea un NPC.",
            "external_turn_id": "context-turn-context-e2e",
            "turn_version": 1,
        },
    )

    assert response_turn.status_code == 200, (
        f"Turno devolvió "
        f"{response_turn.status_code}: "
        f"{response_turn.text}"
    )

    turn_data = response_turn.json()

    assert turn_data["turn_version"] == 1
    assert turn_data["operation_count"] == 1
    assert turn_data["successful_operation_count"] == 1
    assert turn_data["failed_operation_count"] == 0
    assert turn_data["all_operations_succeeded"] is True
    assert turn_data["world_changed"] is True

    assert (
        "CreateEntityOperation"
        in turn_data["operations"]
    )

    # ========================================================
    # 3. CONTEXTO DESPUÉS DEL TURNO
    # ========================================================

    response_after = client.post(
        "/integration/context",
        json={
            "query": "¿Qué NPC hay en la taberna?",
        },
    )

    assert response_after.status_code == 200, (
        f"Contexto posterior devolvió "
        f"{response_after.status_code}: "
        f"{response_after.text}"
    )

    context_after = response_after.json()

    assert context_after["query"] == (
        "¿Qué NPC hay en la taberna?"
    )

    assert "NPC del contexto" in str(
        context_after["context"]
    )

def test_integration_turn_rolls_back_character_mutation_when_later_operation_fails(
    client,
):
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )

    campaign_repository = CampaignRepository()
    character_repository = CharacterRepository()
    entity_repository = EntityRepository()

    # ========================================================
    # Arrange
    # ========================================================

    campaign = campaign_repository.get_campaign(1)
    assert campaign is not None

    entity = entity_repository.save_entity(
        Entity(
            name="Test Character",
            entity_type="character",
            description=(
                "Character used for integration rollback testing."
            ),
        ),
        campaign_id=1,
    )

    character = character_repository.save_character(
        CharacterState(
            entity_id=entity.id,
            level=1,
            class_name="Fighter",
            current_hp=20,
            max_hp=20,
            armor_class=16,
        ),
        campaign_id=1,
    )

    campaign_repository.update_active_character(
        campaign["id"],
        character.entity_id,
    )

    active_character_id = (
        campaign_repository.get_active_character_id(
            campaign["id"]
        )
    )

    assert active_character_id == character.entity_id

    character = character_repository.get_character(
        active_character_id,
        campaign_id=1,
    )

    assert character is not None

    original_hp = character.current_hp

    payload = {
        "external_turn_id": (
            "rollback-character-integration-001"
        ),
        "turn_version": 1,
        "player_input": "I attack the goblin.",
        "narrative": (
            "The attack goes terribly wrong."
        ),
    }

    # ========================================================
    # Sustituir SOLO la extracción LLM
    # ========================================================

    def fake_extract(*args, **kwargs):
        return [
            ChangeCharacterHpOperation(
                entity_id=character.entity_id,
                amount=-5,
            ),
            ChangeCharacterHpOperation(
                entity_id=999999,
                amount=-10,
            ),
        ]

    from app import runtime_factory

    silly_tavern_integration_service = runtime_factory.get_runtime(1).silly_tavern_integration_service

    original_extract = (
        silly_tavern_integration_service.legacy_turn_service.extractor.extract
    )

    silly_tavern_integration_service.legacy_turn_service.extractor.extract = (
        fake_extract
    )

    try:
        # ====================================================
        # Act
        # ====================================================

        response = client.post(
            "/integration/turn",
            json=payload,
        )

    finally:
        # Restaurar el extractor para no contaminar otros tests.
        silly_tavern_integration_service.legacy_turn_service.extractor.extract = (
            original_extract
        )

    # ========================================================
    # Assert
    # ========================================================

    assert response.status_code == 200, (
        f"Integration turn devolvió "
        f"{response.status_code}: "
        f"{response.text}"
    )

    body = response.json()

    assert body["all_operations_succeeded"] is False

    # La primera operación (-5 HP) se ejecutó antes de
    # encontrar el error de la segunda operación.
    #
    # Al fallar el turno completo, NINGUNA de las mutaciones
    # debe quedar persistida en SQLite.
    character_after = character_repository.get_character(
        character.entity_id,
        campaign_id=1,
    )

    assert character_after is not None
    assert character_after.current_hp == original_hp

def test_turn_persistence_failure_restores_shared_in_memory_world(
    client,
    monkeypatch,
):
    import copy

    import app
    from integrations.adapters.silly_tavern import (
        SillyTavernIntegrationServiceError,
    )

    service = (
        app.runtime_factory.get_runtime(1)
        .silly_tavern_integration_service
    )

    world_service = service.legacy_turn_service.world_service
    world_service.load()

    legacy_turn_service = service.legacy_turn_service
    original_transaction = legacy_turn_service.transaction_context
    transaction_modes = []

    @contextmanager
    def tracked_transaction(mode="DEFERRED"):
        transaction_modes.append(mode)
        with original_transaction(mode) as conn:
            yield conn

    monkeypatch.setattr(
        legacy_turn_service,
        "transaction_context",
        tracked_transaction,
    )

    original_world = world_service.get_world()
    original_snapshot = copy.deepcopy(original_world)
    operation = CreateEntityOperation(
        name="Must not remain in memory",
        entity_type="npc",
        description="Used to verify rollback after turn persistence fails.",
    )

    monkeypatch.setattr(
        service.legacy_turn_service.extractor,
        "extract",
        lambda narrative, context: [operation],
    )

    def fail_save_turn(*args, **kwargs):
        raise RuntimeError("forced turn persistence failure")

    monkeypatch.setattr(
        service.legacy_turn_service.turn_repository,
        "save_turn",
        fail_save_turn,
    )

    with pytest.raises(SillyTavernIntegrationServiceError):
        service.process_turn(
            player_input="Creo un NPC.",
            narrative="Aparece un NPC.",
            external_turn_id="memory-rollback-after-save-failure",
            turn_version=1,
        )

    assert transaction_modes == ["DEFERRED", "IMMEDIATE"]
    assert world_service.world is original_world
    assert original_world.entities == original_snapshot.entities
    assert original_world.items == original_snapshot.items
    assert original_world.item_instances == original_snapshot.item_instances
    assert original_world.resources == original_snapshot.resources
    assert original_world.resource_balances == original_snapshot.resource_balances
    assert original_world.relations == original_snapshot.relations
    assert original_world.events == original_snapshot.events

    from database import one

    assert one(
        "SELECT id FROM entities WHERE campaign_id = ? AND name = ?",
        (1, "Must not remain in memory"),
    ) is None
    assert one(
        "SELECT id FROM turns WHERE campaign_id = ? AND external_turn_id = ?",
        (1, "memory-rollback-after-save-failure"),
    ) is None
