# ruff: noqa: F401, I001

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
from services.turns import TurnExecutionLock
from services.world import WorldService

from tests.silly_tavern_integration_support import _build_service

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
