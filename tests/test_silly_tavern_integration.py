import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

import pytest

import services.silly_tavern_integration_service as integration_module
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
from services.silly_tavern_integration_service import (
    SillyTavernIntegrationService,
    SillyTavernIntegrationServiceConflictError,
)
from services.turn_execution_lock import TurnExecutionLock
from services.world_service import WorldService

# ============================================================
# SCHEMAS
# ============================================================


def test_silly_tavern_clarification_schema_requires_stable_answer_identity():
    data = SillyTavernClarificationIn(
        pending_clarification_id="42:challenge-token-long-enough",
        answer="La puerta de roble.",
        answer_external_turn_id="stable-answer-message-id",
        query="Estado actual de la campaña.",
    )

    assert data.answer_external_turn_id == "stable-answer-message-id"


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
        "detail": "Internal server error",
        "code": "internal_error",
    }


def test_integration_resolve_endpoint_commits_before_returning_context(
    client,
    monkeypatch,
):
    from types import SimpleNamespace

    runtime = __import__("app").runtime_factory.get_runtime(1)
    captured = {}

    def fake_prepare(player_input, *, external_turn_id, dice_mode="automatic"):
        captured["player_input"] = player_input
        captured["external_turn_id"] = external_turn_id
        captured["dice_mode"] = dice_mode
        return SimpleNamespace(
            resolution_id=41,
            lifecycle_state="narration_pending",
            committed_resolution='{"resulting_revision": 2}',
            clarification_question=None,
            legacy_replay=False,
        )

    def fake_context(query, *, exclude_external_turn_id=None):
        captured["query"] = query
        captured["exclude_external_turn_id"] = exclude_external_turn_id
        return {
            "campaign": {"id": 1, "name": "Campaña"},
            "session": None,
            "active_character": None,
            "context": {"query": query, "context": "Estado confirmado."},
        }

    monkeypatch.setattr(
        runtime.durable_native_turn_service,
        "prepare_external_turn",
        fake_prepare,
    )
    monkeypatch.setattr(
        runtime.silly_tavern_integration_service,
        "get_context",
        fake_context,
    )

    response = client.post(
        "/integration/turn/resolve",
        json={
            "player_input": "Abro la puerta.",
            "external_turn_id": "st-chat-turn",
            "query": "Estado actual + acción.",
            "dice_mode": "manual",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["resolution_id"] == 41
    assert data["lifecycle_state"] == "narration_pending"
    assert data["committed_resolution"] == '{"resulting_revision": 2}'
    assert data["context"]["context"] == "Estado confirmado."
    assert captured == {
        "player_input": "Abro la puerta.",
        "external_turn_id": "st-chat-turn",
        "dice_mode": "manual",
        "query": "Estado actual + acción.",
        "exclude_external_turn_id": "st-chat-turn",
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

    def fake_complete_external_narration(
        *,
        external_turn_id,
        player_input,
        narrative,
        turn_version,
    ):
        assert external_turn_id == "st-test-turn"
        assert player_input == "Abro la puerta."
        assert narrative == "La puerta se abre."
        assert turn_version == 1
        return FakeResult()

    runtime = __import__("app").runtime_factory.get_runtime(1)
    monkeypatch.setattr(
        runtime.durable_native_turn_service,
        "complete_external_narration",
        fake_complete_external_narration,
    )

    response = client.post(
        "/integration/turn/complete",
        json={
            "player_input": "Abro la puerta.",
            "narrative": "La puerta se abre.",
            "external_turn_id": "st-test-turn",
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


def test_integration_turn_endpoint_returns_409_on_durable_conflict(
    client,
    monkeypatch,
):
    from services.turns.durable_native_turn_service import DurableNativeTurnError

    runtime = __import__("app").runtime_factory.get_runtime(1)

    def fake_complete_external_narration(**kwargs):
        raise DurableNativeTurnError("processing failed")

    monkeypatch.setattr(
        runtime.durable_native_turn_service,
        "complete_external_narration",
        fake_complete_external_narration,
    )

    response = client.post(
        "/integration/turn/complete",
        json={
            "player_input": "Abro la puerta.",
            "narrative": "La puerta se abre.",
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": "processing failed",
        "code": "conflict",
    }


def test_legacy_integration_turn_is_deprecated_in_openapi(client):
    openapi = client.get("/openapi.json").json()
    operation = openapi["paths"]["/integration/turn"]["post"]

    assert operation["deprecated"] is True


def test_legacy_integration_turn_logs_compatibility_usage(
    client,
    monkeypatch,
    caplog,
):
    from types import SimpleNamespace

    runtime = __import__("app").runtime_factory.get_runtime(1)
    result = SimpleNamespace(
        narrative="La puerta se abre.",
        player_input="Abro la puerta.",
        operation_count=0,
        successful_operation_count=0,
        failed_operation_count=0,
        all_operations_succeeded=True,
        world_changed=False,
        operations=(),
        character_operations=(),
        operation_results=(),
    )

    monkeypatch.setattr(
        runtime.silly_tavern_integration_service,
        "process_turn",
        lambda **kwargs: result,
    )

    response = client.post(
        "/integration/turn",
        json={
            "player_input": "Abro la puerta.",
            "narrative": "La puerta se abre.",
            "external_turn_id": "legacy-test-turn",
        },
    )

    assert response.status_code == 200
    warning = next(
        record
        for record in caplog.records
        if "Deprecated legacy SillyTavern turn endpoint" in record.message
    )
    assert warning.campaign_id == 1
    assert warning.external_turn_id == "legacy-test-turn"


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
    ).runtime_factory.get_runtime(1).silly_tavern_integration_service

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
