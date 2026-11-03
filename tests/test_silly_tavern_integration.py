import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

import pytest

from models.campaign_scope import CampaignScope
from models.character_state import CharacterState
from models.entity import Entity
from models.schemas import (
    SillyTavernContextIn,
    SillyTavernTurnIn,
)
from operations.world_operations import CreateEntityOperation
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from services.silly_tavern_integration_service import (
    SillyTavernIntegrationService,
    SillyTavernIntegrationServiceConflictError,
)
from services.turn_execution_lock import TurnExecutionLock
from services.world_service import WorldService

# ============================================================
# SCHEMAS
# ============================================================


def test_silly_tavern_context_schema_accepts_query():
    data = SillyTavernContextIn(
        query="Entro en la taberna."
    )

    assert data.query == (
        "Entro en la taberna."
    )


def test_silly_tavern_context_schema_strips_query():
    data = SillyTavernContextIn(
        query="  Entro en la taberna.  "
    )

    assert data.query == (
        "Entro en la taberna."
    )


def test_silly_tavern_context_schema_rejects_empty_query():
    with pytest.raises(ValueError):
        SillyTavernContextIn(
            query="   "
        )


def test_silly_tavern_turn_schema_accepts_valid_data():
    data = SillyTavernTurnIn(
        player_input="Abro la puerta.",
        narrative=(
            "La puerta se abre con un chirrido "
            "lento y desagradable."
        ),
    )

    assert data.player_input == (
        "Abro la puerta."
    )

    assert data.narrative == (
        "La puerta se abre con un chirrido "
        "lento y desagradable."
    )


def test_silly_tavern_turn_schema_strips_text():
    data = SillyTavernTurnIn(
        player_input="  Abro la puerta.  ",
        narrative="  La puerta se abre.  ",
    )

    assert data.player_input == (
        "Abro la puerta."
    )

    assert data.narrative == (
        "La puerta se abre."
    )


def test_silly_tavern_turn_schema_rejects_empty_player_input():
    with pytest.raises(ValueError):
        SillyTavernTurnIn(
            player_input="   ",
            narrative="Narrativa.",
        )


def test_silly_tavern_turn_schema_rejects_empty_narrative():
    with pytest.raises(ValueError):
        SillyTavernTurnIn(
            player_input="Abro la puerta.",
            narrative="   ",
        )


# ============================================================
# API
# ============================================================


def test_integration_context_endpoint_rejects_missing_query(
    client,
):
    response = client.post(
        "/integration/context",
        json={},
    )

    assert response.status_code == 422


def test_integration_context_endpoint_rejects_empty_query(
    client,
):
    response = client.post(
        "/integration/context",
        json={
            "query": "",
        },
    )

    assert response.status_code == 422


def test_integration_turn_endpoint_rejects_missing_fields(
    client,
):
    response = client.post(
        "/integration/turn",
        json={},
    )

    assert response.status_code == 422


def test_integration_turn_endpoint_rejects_empty_player_input(
    client,
):
    response = client.post(
        "/integration/turn",
        json={
            "player_input": "",
            "narrative": "Narrativa.",
        },
    )

    assert response.status_code == 422


def test_integration_turn_endpoint_rejects_empty_narrative(
    client,
):
    response = client.post(
        "/integration/turn",
        json={
            "player_input": "Abro la puerta.",
            "narrative": "",
        },
    )

    assert response.status_code == 422


def test_integration_context_endpoint_returns_context(
    client,
    monkeypatch,
):
    def fake_get_context(query):
        assert query == (
            "Entro en la taberna."
        )

        return {
            "campaign": {
                "id": 1,
                "name": "Campaña",
                "system": "D&D 5e 2014",
                "tone": "oscuro",
                "summary": "",
            },
            "session": None,
            "active_character": None,
            "query": "Entro en la taberna.",
            "context": {
                "query": "Entro en la taberna.",
                "context": "Sin información relevante.",
            },
        }

    monkeypatch.setattr(
        "app.silly_tavern_integration_service.get_context",
        fake_get_context,
    )

    response = client.post(
        "/integration/context",
        json={
            "query": "Entro en la taberna.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["campaign"]["id"] == 1

    assert data["query"] == (
        "Entro en la taberna."
    )

    assert data["context"]["context"] == (
        "Sin información relevante."
    )


def test_integration_context_endpoint_returns_500_on_service_error(
    client,
    monkeypatch,
):
    from services.silly_tavern_integration_service import (
        SillyTavernIntegrationServiceError,
    )

    def fake_get_context(query):
        raise SillyTavernIntegrationServiceError(
            "context failed"
        )

    monkeypatch.setattr(
        "app.silly_tavern_integration_service.get_context",
        fake_get_context,
    )

    response = client.post(
        "/integration/context",
        json={
            "query": "Entro en la taberna.",
        },
    )

    assert response.status_code == 500

    assert response.json() == {
        "detail": "context failed"
    }


def test_integration_turn_endpoint_returns_processed_turn(
    client,
    monkeypatch,
):
    class FakeResult:
        narrative = (
            "La puerta se abre."
        )

        player_input = (
            "Abro la puerta."
        )

        operation_count = 0

        successful_operation_count = 0

        failed_operation_count = 0

        all_operations_succeeded = True

        world_changed = False

        operations = ()

        character_operations = ()

        operation_results = ()

    def fake_process_turn(
        player_input,
        narrative,
        external_turn_id=None,
        turn_version=1,
    ):
        assert player_input == (
            "Abro la puerta."
        )

        assert narrative == (
            "La puerta se abre."
        )

        assert turn_version == 1

        return FakeResult()

    monkeypatch.setattr(
        "app.silly_tavern_integration_service.process_turn",
        fake_process_turn,
    )

    response = client.post(
        "/integration/turn",
        json={
            "player_input": "Abro la puerta.",
            "narrative": "La puerta se abre.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["player_input"] == (
        "Abro la puerta."
    )

    assert data["narrative"] == (
        "La puerta se abre."
    )

    assert data["operation_count"] == 0

    assert data["successful_operation_count"] == 0

    assert data["failed_operation_count"] == 0

    assert data["all_operations_succeeded"] is True

    assert data["world_changed"] is False

    assert data["operations"] == []

    assert data["operation_results"] == []


def test_integration_turn_endpoint_returns_400_on_service_error(
    client,
    monkeypatch,
):
    from services.silly_tavern_integration_service import (
        SillyTavernIntegrationServiceError,
    )

    def fake_process_turn(
        player_input,
        narrative,
        external_turn_id=None,
        turn_version=1,
    ):
        raise SillyTavernIntegrationServiceError(
            "processing failed"
        )

    monkeypatch.setattr(
        "app.silly_tavern_integration_service.process_turn",
        fake_process_turn,
    )

    response = client.post(
        "/integration/turn",
        json={
            "player_input": "Abro la puerta.",
            "narrative": "La puerta se abre.",
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": "processing failed"
    }


# ============================================================
# SERVICE HELPERS
# ============================================================


def _build_service():
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
    from services.campaign_state_service import (
        CampaignStateService,
    )
    from services.context_builder import (
        ContextBuilder,
    )
    from services.llm_world_extractor import (
        LLMWorldExtractor,
    )
    from services.operation_parser import (
        OperationParser,
    )
    from services.turn_execution_lock import (
        TurnExecutionLock,
    )
    from services.world_service import (
        WorldService,
    )

    world_service = WorldService()

    campaign_state_service = (
        CampaignStateService(
            campaign_repository=(
                CampaignRepository()
            ),
            character_repository=(
                CharacterRepository()
            ),
            entity_repository=(
                EntityRepository()
            ),
            world_service=world_service,
        )
    )

    context_builder = ContextBuilder()

    extractor = LLMWorldExtractor(
        provider=lambda prompt: (
            '{"operations": []}'
        ),
        operation_parser=OperationParser(),
    )

    _turn_repository = TurnRepository()

    turn_execution_lock = TurnExecutionLock()

    service = (
        SillyTavernIntegrationService(
            campaign_state_service=(
                campaign_state_service
            ),
            context_builder=context_builder,
            extractor=extractor,
            world_service=world_service,
            turn_repository=_turn_repository,
            turn_execution_lock=turn_execution_lock,
        )
    )

    return (
        service,
        context_builder,
        extractor,
        world_service,
        _turn_repository,
    )


# ============================================================
# SERVICE - CONTEXT
# ============================================================


def test_integration_service_uses_context_builder_for_context(
    monkeypatch,
):
    (
        service,
        context_builder,
        _extractor,
        _world_service,
        _turn_repository,
    ) = _build_service()

    calls = []

    def fake_build(
        world,
        query,
        recent_turns=None,
    ):
        calls.append(
            {
                "world": world,
                "query": query,
                "recent_turns": recent_turns,
            }
        )

        return {
            "query": query,
            "context": "CONTEXTO",
        }

    monkeypatch.setattr(
        context_builder,
        "build",
        fake_build,
    )

    result = service.get_context(
        "Entro en la taberna."
    )

    assert result["query"] == (
        "Entro en la taberna."
    )

    assert result["context"] == {
        "query": "Entro en la taberna.",
        "context": "CONTEXTO",
    }

    assert len(calls) == 1

    assert calls[0]["query"] == (
        "Entro en la taberna."
    )

    assert isinstance(
        calls[0]["recent_turns"],
        list,
    )


# ============================================================
# SERVICE - NARRATIVE
# ============================================================


def test_integration_service_does_not_generate_narrative(
    monkeypatch,
):
    (
        service,
        _context_builder,
        extractor,
        world_service,
        turn_repository,
    ) = _build_service()

    monkeypatch.setattr(
        extractor,
        "extract",
        lambda narrative, context: [],
    )

    monkeypatch.setattr(
        turn_repository,
        "list_recent_turns",
        lambda session_id=None, limit=10, scope=None: [],
    )

    monkeypatch.setattr(
        turn_repository,
        "save_turn",
        lambda turn, *, scope=None, conn=None: turn,
    )

    monkeypatch.setattr(
        world_service,
        "apply_turn_operations",
        lambda world_operations,
        character_operations,
        *,
        campaign_id,
        conn=None,
        ordered_operations=None: (),
    )

    result = service.process_turn(
        player_input="Abro la puerta.",
        narrative="La puerta se abre.",
    )

    assert result.narrative == (
        "La puerta se abre."
    )


def test_integration_service_passes_silly_tavern_narrative_to_extractor(
    monkeypatch,
):
    (
        service,
        _context_builder,
        extractor,
        world_service,
        turn_repository,
    ) = _build_service()

    captured = {}

    def fake_extract(
        text,
        context,
    ):
        captured["text"] = text
        captured["context"] = context

        return []

    monkeypatch.setattr(
        extractor,
        "extract",
        fake_extract,
    )

    monkeypatch.setattr(
        turn_repository,
        "list_recent_turns",
        lambda session_id=None, limit=10: [],
    )

    monkeypatch.setattr(
        turn_repository,
        "save_turn",
        lambda turn, *, scope=None, conn=None: turn,
    )

    monkeypatch.setattr(
        world_service,
        "apply_turn_operations",
        lambda world_operations,
        character_operations,
        *,
        campaign_id,
        conn=None,
        ordered_operations=None: (),
    )

    result = service.process_turn(
        player_input="Abro la puerta.",
        narrative=(
            "La puerta se abre lentamente."
        ),
    )

    assert captured["text"] == (
        "La puerta se abre lentamente."
    )

    assert captured["context"] is not None

    assert result.narrative == (
        "La puerta se abre lentamente."
    )


# ============================================================
# SERVICE - OPERATIONS
# ============================================================


def test_integration_service_applies_extracted_operations(
    monkeypatch,
):
    (
        service,
        _context_builder,
        extractor,
        world_service,
        turn_repository,
    ) = _build_service()

    operations = []

    monkeypatch.setattr(
        extractor,
        "extract",
        lambda narrative, context: operations,
    )

    monkeypatch.setattr(
        turn_repository,
        "list_recent_turns",
        lambda session_id=None, limit=10: [],
    )

    captured = {}

    def fake_apply_turn_operations(
        world_operations,
        character_operations,
        *,
        campaign_id,
        conn=None,
        ordered_operations=None,
    ):
        captured["world_operations"] = tuple(
            world_operations
        )

        captured["character_operations"] = tuple(
            character_operations
        )

        captured["ordered_operations"] = tuple(
            ordered_operations
        )

        captured["conn"] = conn

        return ()

    monkeypatch.setattr(
        world_service,
        "apply_turn_operations",
        fake_apply_turn_operations,
    )

    monkeypatch.setattr(
        turn_repository,
        "save_turn",
        lambda turn, *, scope=None, conn=None: (
            captured.__setitem__(
                "save_conn",
                conn,
            )
            or turn
        ),
    )

    result = service.process_turn(
        player_input="Abro la puerta.",
        narrative="La puerta se abre.",
    )

    assert result.operation_count == 0

    assert captured["world_operations"] == ()

    assert captured["character_operations"] == ()

    assert captured["ordered_operations"] == ()

    assert captured["conn"] is not None

    assert captured["save_conn"] is (
        captured["conn"]
    )


# ============================================================
# SERVICE - OPERATION ORDER
# ============================================================

def test_integration_service_preserves_operation_order(
    monkeypatch,
):
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )
    from operations.referenced_operation import (
        ReferencedOperation,
    )
    from operations.world_operations import (
        CreateEntityOperation,
    )

    (
        service,
        _context_builder,
        extractor,
        world_service,
        turn_repository,
    ) = _build_service()

    # --------------------------------------------------------
    # Operaciones en el orden exacto producido por el extractor.
    #
    # World -> Character -> World
    # --------------------------------------------------------

    operation_a = ReferencedOperation(
        ref="first",
        operation=CreateEntityOperation(
            name="Aldren",
            entity_type="npc",
        ),
    )

    operation_b = ReferencedOperation(
        ref="second",
        operation=ChangeCharacterHpOperation(
            entity_id=1,
            amount=-2,
        ),
    )

    operation_c = ReferencedOperation(
        ref="third",
        operation=CreateEntityOperation(
            name="Marta",
            entity_type="npc",
        ),
    )

    operations = [
        operation_a,
        operation_b,
        operation_c,
    ]

    monkeypatch.setattr(
        extractor,
        "extract",
        lambda narrative, context: operations,
    )

    monkeypatch.setattr(
        turn_repository,
        "list_recent_turns",
        lambda session_id=None, limit=10: [],
    )

    captured = {}

    def fake_apply_turn_operations(
        world_operations,
        character_operations,
        *,
        campaign_id,
        conn=None,
        ordered_operations=None,
    ):
        captured["world_operations"] = tuple(
            world_operations
        )

        captured["character_operations"] = tuple(
            character_operations
        )

        captured["ordered_operations"] = tuple(
            ordered_operations
        )

        captured["conn"] = conn

        # Este test NO pretende probar el contenido de los
        # OperationResult. Solo necesitamos devolver tres
        # elementos para que el resultado del turno tenga
        # la misma cardinalidad que las operaciones.
        return (
            None,
            None,
            None,
        )

    monkeypatch.setattr(
        world_service,
        "apply_turn_operations",
        fake_apply_turn_operations,
    )

    monkeypatch.setattr(
        turn_repository,
        "save_turn",
        lambda turn, *, scope=None, conn=None: turn,
    )

    service.process_turn(
        player_input="Hago algo.",
        narrative="Ocurre algo.",
    )

    # --------------------------------------------------------
    # Las operaciones siguen separadas por tipo.
    # --------------------------------------------------------

    assert captured["world_operations"] == (
        operation_a,
        operation_c,
    )

    assert captured["character_operations"] == (
        operation_b,
    )

    # --------------------------------------------------------
    # ESTA ES LA COMPROBACIÓN IMPORTANTE:
    #
    # El orden original producido por el extractor se conserva
    # aunque las operaciones se separen internamente por tipo.
    # --------------------------------------------------------

    assert captured["ordered_operations"] == (
        operation_a,
        operation_b,
        operation_c,
    )

    # --------------------------------------------------------
    # WorldService recibió una conexión.
    # --------------------------------------------------------

    assert captured["conn"] is not None

def test_regenerate_turn_restores_snapshot_and_allows_new_version(
    client,
    monkeypatch,
):
    from database import get_conn
    from models.entity import Entity
    from operations.world_operations import (
        CreateItemInstanceOperation,
    )
    from repositories.entity_repository import EntityRepository

    external_turn_id = "test-external-turn"

    # =========================================================
    # PREPARACIÓN
    #
    # La BD de este test está completamente aislada.
    # Creamos explícitamente los datos que necesita la operación
    # para no depender de IDs concretos como 16 o 10.
    # =========================================================

    entity_repository = EntityRepository()

    owner = entity_repository.save_entity(
        Entity(
            name="Aventurero de prueba",
            entity_type="character",
        ),
        campaign_id=1,
    )

    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO items (
                name,
                description,
                significance,
                unique_item,
                notes
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "Espada oxidada de prueba",
                "Una espada vieja.",
                "",
                0,
                "",
            ),
        )

        item_id = cursor.lastrowid

    owner_id = owner.id

    assert item_id is not None
    assert owner_id is not None

    # =========================================================
    # RECARGAR WORLDSTATE
    #
    # El fixture carga WorldService antes de que creemos
    # el owner y el item. Recargamos para sincronizar
    # el estado en memoria con SQLite.
    # =========================================================

    service = __import__(
        "app"
    ).runtime_factory.get_runtime(1).silly_tavern_integration_service

    original_process_turn = service.process_turn


    def debug_process_turn(*args, **kwargs):
        try:
            return original_process_turn(*args, **kwargs)
        except Exception as exc:
            print("\n===== ERROR REAL process_turn =====")
            print(f"Exception: {type(exc).__name__}: {exc}")
            print(f"Cause: {type(exc.__cause__).__name__}: {exc.__cause__}")
            print("\n===== TRACEBACK CAUSA =====")
            if exc.__cause__ is not None:
                traceback.print_exception(
                    type(exc.__cause__),
                    exc.__cause__,
                    exc.__cause__.__traceback__,
                )
            else:
                traceback.print_exception(
                    type(exc),
                    exc,
                    exc.__traceback__,
                )
            print("===================================\n")
            raise


    monkeypatch.setattr(
        service,
        "process_turn",
        debug_process_turn,
    )

    service.world_service.load()

    # =========================================================
    # EXTRACTOR DETERMINISTA
    #
    # El test prueba versionado/snapshots, no Ollama.
    # =========================================================

    create_instance_operation = (
        CreateItemInstanceOperation(
            item_id=item_id,
            instance_number=1,
            owner_id=owner_id,
            condition="oxidado",
        )
    )

    monkeypatch.setattr(
        service.extractor,
        "extract",
        lambda narrative, context: (
            [create_instance_operation]
            if narrative == "Narrativa con espada."
            else []
        ),
    )

    # =========================================================
    # V1 - Primera generación
    # =========================================================

    response_v1 = client.post(
        "/integration/turn",
        json={
            "player_input": (
                "Cojo la espada oxidada "
                "y la guardo en mi inventario."
            ),
            "narrative": "Narrativa con espada.",
            "external_turn_id": external_turn_id,
            "turn_version": 1,
        },
    )

    assert response_v1.status_code == 200, (
        f"V1 devolvió {response_v1.status_code}: "
        f"{response_v1.text}"
    )

    data_v1 = response_v1.json()

    assert data_v1["turn_version"] == 1
    assert data_v1["external_turn_id"] == (
        external_turn_id
    )

    assert data_v1["operation_count"] == 1
    assert data_v1["successful_operation_count"] == 1
    assert data_v1["failed_operation_count"] == 0
    assert data_v1["all_operations_succeeded"] is True
    assert data_v1["world_changed"] is True

    # ---------------------------------------------------------
    # V1 debe haber creado la instancia.
    # ---------------------------------------------------------

    with get_conn() as conn:
        instance_v1 = conn.execute(
            """
            SELECT
                id,
                item_id,
                instance_number,
                owner_id,
                condition,
                active
            FROM item_instances
            WHERE item_id = ?
              AND owner_id = ?
            """,
            (
                item_id,
                owner_id,
            ),
        ).fetchone()

        turns_v1 = conn.execute(
            """
            SELECT
                version,
                status,
                operation_count,
                world_changed,
                snapshot IS NOT NULL AS has_snapshot
            FROM turns
            WHERE external_turn_id = ?
            ORDER BY version
            """,
            (external_turn_id,),
        ).fetchall()

    assert instance_v1 is not None
    assert instance_v1["item_id"] == item_id
    assert instance_v1["instance_number"] == 1
    assert instance_v1["owner_id"] == owner_id
    assert instance_v1["condition"] == "oxidado"
    assert instance_v1["active"] == 1

    assert len(turns_v1) == 1

    assert turns_v1[0]["version"] == 1
    assert turns_v1[0]["status"] == "active"
    assert turns_v1[0]["operation_count"] == 1
    assert turns_v1[0]["world_changed"] == 1
    assert turns_v1[0]["has_snapshot"] == 1

    # =========================================================
    # V2 - Regeneración
    #
    # Esta versión no genera operaciones.
    #
    # Antes de aplicar V2, el servicio debe:
    #
    #   1. Restaurar el snapshot de V1.
    #   2. Marcar V1 como superseded.
    #   3. Aplicar la nueva versión.
    #
    # Como el snapshot representa el estado ANTERIOR a V1,
    # la instancia creada por V1 debe desaparecer.
    # =========================================================

    response_v2 = client.post(
        "/integration/turn",
        json={
            "player_input": (
                "Cojo la espada oxidada "
                "y la guardo en mi inventario."
            ),
            "narrative": "Narrativa alternativa.",
            "external_turn_id": external_turn_id,
            "turn_version": 2,
        },
    )

    assert response_v2.status_code == 200

    data_v2 = response_v2.json()

    assert data_v2["turn_version"] == 2
    assert data_v2["external_turn_id"] == (
        external_turn_id
    )

    assert data_v2["operation_count"] == 0
    assert data_v2["successful_operation_count"] == 0
    assert data_v2["failed_operation_count"] == 0
    assert data_v2["all_operations_succeeded"] is True
    assert data_v2["world_changed"] is False

    # ---------------------------------------------------------
    # Comprobar versiones y estado de la instancia.
    # ---------------------------------------------------------

    with get_conn() as conn:
        turns_v2 = conn.execute(
            """
            SELECT
                version,
                status,
                operation_count,
                world_changed,
                snapshot IS NOT NULL AS has_snapshot
            FROM turns
            WHERE external_turn_id = ?
            ORDER BY version
            """,
            (external_turn_id,),
        ).fetchall()

        instance_v2 = conn.execute(
            """
            SELECT id
            FROM item_instances
            WHERE item_id = ?
              AND owner_id = ?
            """,
            (
                item_id,
                owner_id,
            ),
        ).fetchone()

    assert len(turns_v2) == 2

    # V1
    assert turns_v2[0]["version"] == 1
    assert turns_v2[0]["status"] == "superseded"
    assert turns_v2[0]["operation_count"] == 1
    assert turns_v2[0]["world_changed"] == 1
    assert turns_v2[0]["has_snapshot"] == 1

    # V2
    assert turns_v2[1]["version"] == 2
    assert turns_v2[1]["status"] == "active"
    assert turns_v2[1]["operation_count"] == 0
    assert turns_v2[1]["world_changed"] == 0
    assert turns_v2[1]["has_snapshot"] == 1

    # La instancia creada por V1 desaparece al restaurar
    # el snapshot anterior a V1.
    assert instance_v2 is None

    # =========================================================
    # V3 - Nueva regeneración
    #
    # Volvemos a generar la operación.
    #
    # El estado actual es el restaurado por V2, por lo que
    # podemos aplicar de nuevo la operación desde cero.
    # =========================================================

    response_v3 = client.post(
        "/integration/turn",
        json={
            "player_input": (
                "Cojo la espada oxidada "
                "y la guardo en mi inventario."
            ),
            "narrative": "Narrativa con espada.",
            "external_turn_id": external_turn_id,
            "turn_version": 3,
        },
    )

    assert response_v3.status_code == 200

    data_v3 = response_v3.json()

    assert data_v3["turn_version"] == 3
    assert data_v3["external_turn_id"] == (
        external_turn_id
    )

    assert data_v3["operation_count"] == 1
    assert data_v3["successful_operation_count"] == 1
    assert data_v3["failed_operation_count"] == 0
    assert data_v3["all_operations_succeeded"] is True
    assert data_v3["world_changed"] is True

    # =========================================================
    # ESTADO FINAL
    # =========================================================

    with get_conn() as conn:
        final_turns = conn.execute(
            """
            SELECT
                version,
                status,
                operation_count,
                world_changed,
                snapshot IS NOT NULL AS has_snapshot
            FROM turns
            WHERE external_turn_id = ?
            ORDER BY version
            """,
            (external_turn_id,),
        ).fetchall()

        final_instance = conn.execute(
            """
            SELECT
                id,
                item_id,
                instance_number,
                owner_id,
                condition,
                active
            FROM item_instances
            WHERE item_id = ?
              AND owner_id = ?
            """,
            (
                item_id,
                owner_id,
            ),
        ).fetchone()

    assert len(final_turns) == 3

    # ---------------------------------------------------------
    # V1
    # ---------------------------------------------------------

    assert final_turns[0]["version"] == 1
    assert final_turns[0]["status"] == "superseded"
    assert final_turns[0]["operation_count"] == 1
    assert final_turns[0]["world_changed"] == 1
    assert final_turns[0]["has_snapshot"] == 1

    # ---------------------------------------------------------
    # V2
    # ---------------------------------------------------------

    assert final_turns[1]["version"] == 2
    assert final_turns[1]["status"] == "superseded"
    assert final_turns[1]["operation_count"] == 0
    assert final_turns[1]["world_changed"] == 0
    assert final_turns[1]["has_snapshot"] == 1

    # ---------------------------------------------------------
    # V3
    # ---------------------------------------------------------

    assert final_turns[2]["version"] == 3
    assert final_turns[2]["status"] == "active"
    assert final_turns[2]["operation_count"] == 1
    assert final_turns[2]["world_changed"] == 1
    assert final_turns[2]["has_snapshot"] == 1

    # ---------------------------------------------------------
    # La instancia vuelve a existir después de V3.
    # ---------------------------------------------------------

    assert final_instance is not None
    assert final_instance["item_id"] == item_id
    assert final_instance["instance_number"] == 1
    assert final_instance["owner_id"] == owner_id
    assert final_instance["condition"] == "oxidado"
    assert final_instance["active"] == 1

def test_exact_retry_returns_persisted_turn_without_running_extractor(
    client,
    monkeypatch,
):
    from database import get_conn

    service = __import__(
        "app"
    ).runtime_factory.get_runtime(1).silly_tavern_integration_service

    external_turn_id = "retry-test-turn"

    extractor_calls = []

    def fake_extract(
        narrative,
        context,
    ):
        extractor_calls.append(
            {
                "narrative": narrative,
                "context": context,
            }
        )

        return []

    monkeypatch.setattr(
        service.extractor,
        "extract",
        fake_extract,
    )

    payload = {
        "player_input": "Abro la puerta.",
        "narrative": "La puerta se abre.",
        "external_turn_id": external_turn_id,
        "turn_version": 1,
    }

    # =========================================================
    # PRIMERA PETICIÓN
    # =========================================================

    response_first = client.post(
        "/integration/turn",
        json=payload,
    )

    assert response_first.status_code == 200

    data_first = response_first.json()

    assert data_first["external_turn_id"] == (
        external_turn_id
    )

    assert data_first["turn_version"] == 1

    assert data_first["operation_count"] == 0

    assert len(extractor_calls) == 1

    # =========================================================
    # RETRY EXACTO
    # =========================================================
    #
    # Debe devolverse el turno persistido.
    #
    # IMPORTANTE:
    # El extractor NO debe volver a ejecutarse.
    # =========================================================

    response_retry = client.post(
        "/integration/turn",
        json=payload,
    )

    assert response_retry.status_code == 200

    data_retry = response_retry.json()

    assert data_retry == data_first

    assert len(extractor_calls) == 1

    # =========================================================
    # COMPROBAR QUE SOLO EXISTE UNA VERSIÓN
    # =========================================================

    with get_conn() as conn:
        turns = conn.execute(
            """
            SELECT
                external_turn_id,
                version,
                status
            FROM turns
            WHERE external_turn_id = ?
            ORDER BY version
            """,
            (external_turn_id,),
        ).fetchall()

    assert len(turns) == 1

    assert turns[0]["external_turn_id"] == (
        external_turn_id
    )

    assert turns[0]["version"] == 1

    assert turns[0]["status"] == "active"

def test_same_turn_version_with_different_content_returns_conflict(
    client,
    monkeypatch,
):
    from database import get_conn

    service = __import__(
        "app"
    ).silly_tavern_integration_service

    external_turn_id = "conflict-test-turn"

    extractor_calls = []

    def fake_extract(
        narrative,
        context,
    ):
        extractor_calls.append(
            {
                "narrative": narrative,
                "context": context,
            }
        )

        return []

    monkeypatch.setattr(
        service.extractor,
        "extract",
        fake_extract,
    )

    payload = {
        "player_input": "Abro la puerta.",
        "narrative": "La puerta se abre.",
        "external_turn_id": external_turn_id,
        "turn_version": 1,
    }

    # =========================================================
    # PRIMERA PETICIÓN
    # =========================================================

    response_first = client.post(
        "/integration/turn",
        json=payload,
    )

    assert response_first.status_code == 200

    assert len(extractor_calls) == 1

    # =========================================================
    # SEGUNDA PETICIÓN
    # =========================================================
    #
    # Mismo external_turn_id + misma versión,
    # pero narrativa diferente.
    #
    # Esto NO es un retry válido.
    # Debe producir conflicto.
    # =========================================================

    conflicting_payload = {
        "player_input": "Abro la puerta.",
        "narrative": "Detrás de la puerta aparece un dragón.",
        "external_turn_id": external_turn_id,
        "turn_version": 1,
    }

    response_conflict = client.post(
        "/integration/turn",
        json=conflicting_payload,
    )

    assert response_conflict.status_code == 409

    assert (
        "external_turn_id and version already exist"
        in response_conflict.json()["detail"]
    )

    # El extractor no debe ejecutarse para el conflicto.
    assert len(extractor_calls) == 1

    # =========================================================
    # COMPROBAR QUE NO SE CREÓ OTRA VERSIÓN
    # =========================================================

    with get_conn() as conn:
        turns = conn.execute(
            """
            SELECT
                external_turn_id,
                version,
                status,
                player_input,
                narrative
            FROM turns
            WHERE external_turn_id = ?
            ORDER BY version
            """,
            (external_turn_id,),
        ).fetchall()

    assert len(turns) == 1

    assert turns[0]["external_turn_id"] == (
        external_turn_id
    )

    assert turns[0]["version"] == 1

    assert turns[0]["status"] == "active"

    assert turns[0]["player_input"] == (
        "Abro la puerta."
    )

    assert turns[0]["narrative"] == (
        "La puerta se abre."
    )

def test_concurrent_exact_retries_persist_only_one_turn(
    monkeypatch,
):
    import app
    from database import get_conn

    external_turn_id = "concurrent-turn-001"

    extractor_calls = 0
    extractor_lock = threading.Lock()

    def fake_extract(narrative, turn_context):
        nonlocal extractor_calls

        with extractor_lock:
            extractor_calls += 1

        return []

    service = app.runtime_factory.get_runtime(1).silly_tavern_integration_service
    extractor = service.extractor

    monkeypatch.setattr(
        extractor,
        "extract",
        fake_extract,
    )

    payload = {
        "player_input": "Abro la puerta.",
        "narrative": "La puerta se abre lentamente.",
        "external_turn_id": external_turn_id,
        "turn_version": 1,
    }

    def send_request():
        return (
            service.process_turn(
                player_input=payload["player_input"],
                narrative=payload["narrative"],
                external_turn_id=payload["external_turn_id"],
                turn_version=payload["turn_version"],
            )
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(send_request)
            for _ in range(2)
        ]

        results = [
            future.result()
            for future in futures
        ]

    assert len(results) == 2

    # Solo una petición debe llegar al extractor.
    # La segunda es un retry idempotente y recupera
    # el TurnRecord ya persistido.
    assert extractor_calls == 1

    assert results[0].player_input == payload["player_input"]
    assert results[1].player_input == payload["player_input"]

    assert results[0].narrative == payload["narrative"]
    assert results[1].narrative == payload["narrative"]

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                external_turn_id,
                version,
                status
            FROM turns
            WHERE external_turn_id = ?
            ORDER BY version
            """,
            (external_turn_id,),
        ).fetchall()

    assert len(rows) == 1

    assert rows[0]["external_turn_id"] == external_turn_id
    assert rows[0]["version"] == 1
    assert rows[0]["status"] == "active"

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
    from services.campaign_state_service import (
        CampaignStateService,
    )
    from services.context_builder import (
        ContextBuilder,
    )
    from services.llm_world_extractor import (
        LLMWorldExtractor,
    )
    from services.operation_parser import (
        OperationParser,
    )
    from services.world_service import (
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

    service = SillyTavernIntegrationService(
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


def test_silly_tavern_turn_same_version_different_content_conflicts(
    monkeypatch,
):
    (
        service,
        _context_builder,
        extractor,
        _world_service,
        _turn_repository,
    ) = _build_service()

    monkeypatch.setattr(
        extractor,
        "extract",
        lambda narrative, context: [],
    )

    first_result = service.process_turn(
        player_input="Abro la puerta.",
        narrative="La puerta se abre lentamente.",
        external_turn_id="conflict-test-001",
        turn_version=1,
    )

    assert first_result.narrative == (
        "La puerta se abre lentamente."
    )

    from services.silly_tavern_integration_service import (
        SillyTavernIntegrationServiceConflictError,
    )

    with pytest.raises(
        SillyTavernIntegrationServiceConflictError
    ):
        service.process_turn(
            player_input="Abro la puerta.",
            narrative="La puerta permanece cerrada.",
            external_turn_id="conflict-test-001",
            turn_version=1,
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
    from services.campaign_state_service import (
        CampaignStateService,
    )
    from services.context_builder import (
        ContextBuilder,
    )
    from services.llm_world_extractor import (
        LLMWorldExtractor,
    )
    from services.operation_parser import (
        OperationParser,
    )
    from services.world_service import (
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

    service = SillyTavernIntegrationService(
        campaign_state_service=campaign_state_service,
        context_builder=ContextBuilder(),
        extractor=extractor,
        world_service=world_service,
        turn_repository=TurnRepository(),
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
    from services.campaign_state_service import (
        CampaignStateService,
    )
    from services.context_builder import (
        ContextBuilder,
    )
    from services.llm_world_extractor import (
        LLMWorldExtractor,
    )
    from services.operation_parser import (
        OperationParser,
    )
    from services.silly_tavern_integration_service import (
        SillyTavernIntegrationServiceError,
    )
    from services.world_service import (
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

    service = SillyTavernIntegrationService(
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

def test_failed_regeneration_rolls_back_snapshot_restore(
    client,
    monkeypatch,
):
    from database import get_conn

    service = __import__(
        "app"
    ).silly_tavern_integration_service

    external_turn_id = (
        "failed-regeneration-test"
    )

    # =========================================================
    # V1 - CREAR ESTADO INICIAL
    # =========================================================

    from operations.world_operations import (
        CreateEntityOperation,
    )

    created_entity_operation = (
        CreateEntityOperation(
            name="Entidad V1",
            entity_type="npc",
            description="Estado original.",
        )
    )

    monkeypatch.setattr(
        service.extractor,
        "extract",
        lambda narrative, context: (
            [created_entity_operation]
            if narrative == "Narrativa V1."
            else []
        ),
    )

    response_v1 = client.post(
        "/integration/turn",
        json={
            "player_input": "Creo una entidad.",
            "narrative": "Narrativa V1.",
            "external_turn_id": external_turn_id,
            "turn_version": 1,
        },
    )

    assert response_v1.status_code == 200, (
        f"V1 devolvió "
        f"{response_v1.status_code}: "
        f"{response_v1.text}"
    )

    data_v1 = response_v1.json()

    assert data_v1["turn_version"] == 1
    assert data_v1["external_turn_id"] == (
        external_turn_id
    )
    assert data_v1["operation_count"] == 1
    assert data_v1["successful_operation_count"] == 1
    assert data_v1["failed_operation_count"] == 0
    assert data_v1["all_operations_succeeded"] is True
    assert data_v1["world_changed"] is True

    # =========================================================
    # CAPTURAR ESTADO ANTES DE LA REGENERACIÓN
    # =========================================================

    with get_conn() as conn:
        entities_before = conn.execute(
            """
            SELECT
                id,
                name,
                entity_type,
                description,
                notes,
                active
            FROM entities
            ORDER BY id
            """
        ).fetchall()

        turns_before = conn.execute(
            """
            SELECT
                id,
                external_turn_id,
                version,
                status,
                operation_count,
                successful_operation_count,
                failed_operation_count,
                all_operations_succeeded,
                world_changed,
                snapshot
            FROM turns
            WHERE external_turn_id = ?
            ORDER BY version
            """,
            (external_turn_id,),
        ).fetchall()

    assert len(turns_before) == 1
    assert turns_before[0]["version"] == 1
    assert turns_before[0]["status"] == "active"

    assert any(
        entity["name"] == "Entidad V1"
        for entity in entities_before
    )

    # =========================================================
    # FORZAR FALLO DESPUÉS DEL RESTORE
    # =========================================================
    #
    # El flujo real del servicio hace:
    #
    #   restore_snapshot()
    #   load()
    #   supersede_turn()
    #   apply_turn_operations()
    #
    # Por tanto, si hacemos fallar apply_turn_operations(),
    # el fallo ocurre DESPUÉS de haber restaurado el snapshot.
    #
    # La transacción SQLite debe hacer rollback de:
    #
    #   - restore_snapshot()
    #   - supersede_turn()
    #   - cualquier cambio posterior
    #
    # y V1 debe seguir exactamente igual.
    # =========================================================

    def fail_after_snapshot_restore(
        world_operations,
        character_operations,
        *,
        conn=None,
        ordered_operations=None,
    ):
        raise RuntimeError(
            "forced regeneration failure"
        )

    monkeypatch.setattr(
        service.world_service,
        "apply_turn_operations",
        fail_after_snapshot_restore,
    )

    # =========================================================
    # V2 - REGENERACIÓN FALLIDA
    # =========================================================

    response_v2 = client.post(
        "/integration/turn",
        json={
            "player_input": "Genero una alternativa.",
            "narrative": "Narrativa V2.",
            "external_turn_id": external_turn_id,
            "turn_version": 2,
        },
    )

    assert response_v2.status_code == 400

    # =========================================================
    # COMPROBAR ROLLBACK COMPLETO
    # =========================================================

    with get_conn() as conn:
        entities_after = conn.execute(
            """
            SELECT
                id,
                name,
                entity_type,
                description,
                notes,
                active
            FROM entities
            ORDER BY id
            """
        ).fetchall()

        turns_after = conn.execute(
            """
            SELECT
                id,
                external_turn_id,
                version,
                status,
                operation_count,
                successful_operation_count,
                failed_operation_count,
                all_operations_succeeded,
                world_changed,
                snapshot
            FROM turns
            WHERE external_turn_id = ?
            ORDER BY version
            """,
            (external_turn_id,),
        ).fetchall()

    # ---------------------------------------------------------
    # EL WORLD STATE DEBE SER EXACTAMENTE EL MISMO
    # ---------------------------------------------------------

    assert [
        dict(row)
        for row in entities_after
    ] == [
        dict(row)
        for row in entities_before
    ]

    # ---------------------------------------------------------
    # V2 NO DEBE HABER QUEDADO PERSISTIDA
    # ---------------------------------------------------------

    assert len(turns_after) == 1

    # ---------------------------------------------------------
    # V1 SIGUE SIENDO EL TURNO ACTIVO
    # ---------------------------------------------------------

    assert turns_after[0]["id"] == (
        turns_before[0]["id"]
    )

    assert turns_after[0]["external_turn_id"] == (
        external_turn_id
    )

    assert turns_after[0]["version"] == 1

    assert turns_after[0]["status"] == "active"

    assert turns_after[0]["operation_count"] == 1

    assert turns_after[0][
        "successful_operation_count"
    ] == 1

    assert turns_after[0][
        "failed_operation_count"
    ] == 0

    assert turns_after[0][
        "all_operations_succeeded"
    ] == 1

    assert turns_after[0]["world_changed"] == 1

    # El snapshot original tampoco debe haber cambiado.
    assert turns_after[0]["snapshot"] == (
        turns_before[0]["snapshot"]
    )

    # =========================================================
    # IMPORTANTE:
    # No existe ninguna versión 2 persistida.
    # =========================================================

    assert not any(
        turn["version"] == 2
        for turn in turns_after
    )

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
        service.extractor,
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
        service.extractor,
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
        silly_tavern_integration_service.extractor.extract
    )

    silly_tavern_integration_service.extractor.extract = (
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
        silly_tavern_integration_service.extractor.extract = (
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

def test_integration_turn_state_endpoint_returns_missing_turn(
    client,
    monkeypatch,
):
    def fake_get_external_turn_state(
        external_turn_id,
    ):
        assert external_turn_id == (
            "external-turn-123"
        )

        return {
            "external_turn_id":
                external_turn_id,
            "exists": False,
            "active_version": 0,
            "narrative": None,
        }

    monkeypatch.setattr(
        (
            "app.silly_tavern_integration_service."
            "get_external_turn_state"
        ),
        fake_get_external_turn_state,
    )

    response = client.get(
        "/integration/turn/external-turn-123"
    )

    assert response.status_code == 200

    assert response.json() == {
        "external_turn_id":
            "external-turn-123",
        "exists": False,
        "active_version": 0,
        "narrative": None,
    }

def test_integration_turn_state_endpoint_returns_active_version(
    client,
    monkeypatch,
):
    def fake_get_external_turn_state(
        external_turn_id,
    ):
        assert external_turn_id == (
            "external-turn-123"
        )

        return {
            "external_turn_id":
                external_turn_id,
            "exists": True,
            "active_version": 3,
            "narrative":
                "La puerta se abre.",
        }

    monkeypatch.setattr(
        (
            "app.silly_tavern_integration_service."
            "get_external_turn_state"
        ),
        fake_get_external_turn_state,
    )

    response = client.get(
        "/integration/turn/external-turn-123"
    )

    assert response.status_code == 200

    assert response.json() == {
        "external_turn_id":
            "external-turn-123",
        "exists": True,
        "active_version": 3,
        "narrative":
            "La puerta se abre.",
    }

def test_integration_service_returns_missing_external_turn_state(
    isolated_database,
):
    (
        service,
        _context_builder,
        _extractor,
        _world_service,
        _turn_repository,
    ) = _build_service()

    result = (
        service.get_external_turn_state(
            "missing-turn"
        )
    )

    assert result == {
        "external_turn_id":
            "missing-turn",
        "exists": False,
        "active_version": 0,
        "narrative": None,
    }

def test_integration_service_returns_active_external_turn_state(
    isolated_database,
):
    from models.turn_record import (
        TurnRecord,
    )

    (
        service,
        _context_builder,
        _extractor,
        _world_service,
        turn_repository,
    ) = _build_service()

    turn_repository.save_turn(
        TurnRecord(
            session_id=None,
            player_input="Abro la puerta.",
            narrative="La puerta se abre.",
            operation_count=0,
            successful_operation_count=0,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=False,
            external_turn_id="external-turn-123",
            version=4,
            status="active",
            snapshot=None,
        ),
    
        scope=CampaignScope(1),
    )

    result = (
        service.get_external_turn_state(
            "external-turn-123"
        )
    )

    assert result == {
        "external_turn_id":
            "external-turn-123",
        "exists": True,
        "active_version": 4,
        "narrative":
            "La puerta se abre.",
    }

def test_integration_service_rejects_non_sequential_turn_version(
    monkeypatch,
):
    (
        service,
        _context_builder,
        extractor,
        _world_service,
        turn_repository,
    ) = _build_service()

    monkeypatch.setattr(
        extractor,
        "extract",
        lambda narrative, context: [],
    )

    first_result = service.process_turn(
        player_input="Abro la puerta.",
        narrative="La puerta se abre.",
        external_turn_id="sequential-version-test",
        turn_version=1,
    )

    assert first_result.narrative == (
        "La puerta se abre."
    )

    with pytest.raises(
        SillyTavernIntegrationServiceConflictError,
        match="must be the next sequential version",
    ):
        service.process_turn(
            player_input="Abro la puerta de nuevo.",
            narrative="La puerta se abre otra vez.",
            external_turn_id="sequential-version-test",
            turn_version=3,
        )

    active_turn = (
        turn_repository.get_active_by_external_turn_id(
            "sequential-version-test",
        
            scope=CampaignScope(1),
        )
    )

    assert active_turn is not None
    assert active_turn.version == 1

def test_integration_service_allows_next_sequential_version(
    monkeypatch,
):
    (
        service,
        _context_builder,
        extractor,
        _world_service,
        turn_repository,
    ) = _build_service()

    monkeypatch.setattr(
        extractor,
        "extract",
        lambda narrative, context: [],
    )

    v1 = service.process_turn(
        player_input="Abro la puerta.",
        narrative="La puerta se abre.",
        external_turn_id="sequential-version-test-2",
        turn_version=1,
    )

    assert v1.narrative == (
        "La puerta se abre."
    )

    v2 = service.process_turn(
        player_input="Miro dentro.",
        narrative="Dentro hay una habitación oscura.",
        external_turn_id="sequential-version-test-2",
        turn_version=2,
    )

    assert v2.narrative == (
        "Dentro hay una habitación oscura."
    )

    with pytest.raises(
        SillyTavernIntegrationServiceConflictError,
        match="must be the next sequential version",
    ):
        service.process_turn(
            player_input="Entro directamente.",
            narrative="Entras directamente.",
            external_turn_id="sequential-version-test-2",
            turn_version=4,
        )

    active_turn = (
        turn_repository.get_active_by_external_turn_id(
            "sequential-version-test-2",
        
            scope=CampaignScope(1),
        )
    )

    assert active_turn is not None
    assert active_turn.version == 2

def test_regeneration_extracts_against_state_before_previous_version(
    client,
    monkeypatch,
):
    service = __import__("app").runtime_factory.get_runtime(1).silly_tavern_integration_service

    seen_entities = []

    def fake_extract(narrative, turn_context):
        seen_entities.append(
            {
                entity.name
                for entity in turn_context.world.entities.values()
            }
        )

        if narrative == "Narrativa V1":
            return [
                CreateEntityOperation(
                    name="Entidad V1",
                    entity_type="npc",
                    description="Creada en V1.",
                )
            ]

        if narrative == "Narrativa V2":
            return []

        raise AssertionError(
            f"Narrativa inesperada: {narrative}"
        )

    monkeypatch.setattr(
        service.extractor,
        "extract",
        fake_extract,
    )

    response_v1 = client.post(
        "/integration/turn",
        json={
            "player_input": "Input V1",
            "narrative": "Narrativa V1",
            "external_turn_id": "regeneration-context-test",
            "turn_version": 1,
        },
    )

    assert response_v1.status_code == 200

    response_v2 = client.post(
        "/integration/turn",
        json={
            "player_input": "Input V2",
            "narrative": "Narrativa V2",
            "external_turn_id": "regeneration-context-test",
            "turn_version": 2,
        },
    )

    assert response_v2.status_code == 200

    assert len(seen_entities) == 2

    # V1 se extrae antes de crear Entidad V1.
    assert "Entidad V1" not in seen_entities[0]

    # V2 se regenera desde el snapshot anterior a V1.
    assert "Entidad V1" not in seen_entities[1]

def test_first_external_turn_must_use_version_one(
    monkeypatch,
):
    (
        service,
        _context_builder,
        _extractor,
        _world_service,
        turn_repository,
    ) = _build_service()

    monkeypatch.setattr(
        turn_repository,
        "get_active_by_external_turn_id",
        lambda external_turn_id, *, scope=None, conn=None: None,
    )

    with pytest.raises(
        SillyTavernIntegrationServiceConflictError,
        match="first turn version must be 1",
    ):
        service.process_turn(
            player_input="Entro en la taberna.",
            narrative="La taberna está en silencio.",
            external_turn_id="first-turn-v2",
            turn_version=2,
        )