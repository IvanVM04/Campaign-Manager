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

from tests.silly_tavern_integration_support import _build_service

def test_regenerate_turn_restores_snapshot_and_allows_new_version(
    client,
    monkeypatch,
):
    from database import get_conn
    from operations.world_operations import (
        CreateItemInstanceOperation,
    )

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

    service.legacy_turn_service.world_service.load()

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
        service.legacy_turn_service.extractor,
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

def test_failed_regeneration_rolls_back_snapshot_restore(
    client,
    monkeypatch,
):
    from database import get_conn

    service = __import__(
        "app"
    ).runtime_factory.get_runtime(1).silly_tavern_integration_service

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
        service.legacy_turn_service.extractor,
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
        service.legacy_turn_service.world_service,
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
        service.legacy_turn_service.extractor,
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
