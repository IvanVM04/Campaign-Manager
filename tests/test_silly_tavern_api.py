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
)
from operations.world_operations import CreateEntityOperation
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from integrations.adapters.silly_tavern import (
    SillyTavernIntegrationService,
)
from services.turns import TurnExecutionLock
from services.turns.durable_native_turn_service import DurableNativeTurnError
from services.world import WorldService

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

    import app

    monkeypatch.setattr(
        app.runtime_factory.get_runtime(1).silly_tavern_integration_service,
        "get_context",
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
    from integrations.adapters.silly_tavern import (
        SillyTavernIntegrationServiceError,
    )

    def fake_get_context(query):
        raise SillyTavernIntegrationServiceError(
            "context failed"
        )

    import app

    monkeypatch.setattr(
        app.runtime_factory.get_runtime(1).silly_tavern_integration_service,
        "get_context",
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

def test_integration_turn_complete_endpoint_returns_processed_turn(
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
            "external_turn_id": "st-conflict-turn",
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": "processing failed",
        "code": "conflict",
    }

def test_legacy_integration_turn_route_is_removed(client):
    response = client.post(
        "/integration/turn",
        json={
            "player_input": "Abro la puerta.",
            "narrative": "La puerta se abre.",
        },
    )
    assert response.status_code == 404


# ============================================================
# SERVICE HELPERS
# ============================================================

def test_integration_clarification_state_endpoint_returns_durable_state(
    client,
    monkeypatch,
):
    expected = {
        "external_turn_id": "external-turn-clarification",
        "has_clarification": True,
        "lifecycle_state": "awaiting_input",
        "player_input": "Abro una puerta.",
        "clarification_question": "¿Qué puerta?",
        "pending_clarification_id": "42:challenge",
        "last_pending_clarification_id": None,
        "last_answer": None,
        "resolved_player_input": None,
        "narrative": None,
    }

    class FakeLock:
        def acquire(self):
            return nullcontext()

    runtime = SimpleNamespace(
        turn_execution_lock=FakeLock(),
        durable_native_turn_service=SimpleNamespace(
            get_external_clarification_state=lambda external_turn_id: expected
            if external_turn_id == "external-turn-clarification"
            else None,
        ),
    )
    monkeypatch.setattr(
        "api.routers.integration.get_current_runtime",
        lambda: runtime,
    )

    response = client.get(
        "/integration/turn/external-turn-clarification/clarification"
    )

    assert response.status_code == 200
    assert response.json() == expected

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

    import app

    monkeypatch.setattr(
        app.runtime_factory.get_runtime(1).silly_tavern_integration_service,
        "get_external_turn_state",
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

    import app

    monkeypatch.setattr(
        app.runtime_factory.get_runtime(1).silly_tavern_integration_service,
        "get_external_turn_state",
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

def test_silly_tavern_manual_roll_state_endpoint_returns_durable_challenge(client, monkeypatch):
    runtime = __import__("app").runtime_factory.get_runtime(1)
    expected = {
        "external_turn_id": "st-manual-turn",
        "has_manual_roll": True,
        "lifecycle_state": "awaiting_input",
        "player_input": "Me escondo.",
        "pending_roll_id": "42:" + "a" * 24,
        "pending_roll": {"count": 2, "dice": "d20", "modifier": 5},
    }
    monkeypatch.setattr(
        runtime.durable_native_turn_service,
        "get_external_manual_roll_state",
        lambda external_turn_id: expected,
    )
    response = client.get("/integration/turn/st-manual-turn/manual-roll")
    assert response.status_code == 200
    assert response.json() == expected

def test_silly_tavern_manual_roll_endpoint_submits_results_and_returns_resolution(client, monkeypatch):
    runtime = __import__("app").runtime_factory.get_runtime(1)
    captured = {}

    def fake_submit(pending_roll_id, rolls, *, adapter_namespace, defer_narration, answer_external_turn_id):
        captured.update({
            "pending_roll_id": pending_roll_id,
            "rolls": rolls,
            "adapter_namespace": adapter_namespace,
            "defer_narration": defer_narration,
            "answer_external_turn_id": answer_external_turn_id,
        })
        return SimpleNamespace(
            resolution_id=42,
            lifecycle_state="narration_pending",
            committed_resolution='{"mechanics":{"total":22,"success":true}}',
            pending_roll_id=None,
            pending_roll=None,
        )

    def fake_context(query):
        return {
            "campaign": {"id": 1, "name": "Campaña"},
            "session": None,
            "active_character": None,
            "context": {"query": query, "context": "Estado actual."},
        }

    monkeypatch.setattr(runtime.durable_native_turn_service, "submit_manual_roll", fake_submit)
    monkeypatch.setattr(runtime.silly_tavern_integration_service, "get_context", fake_context)

    response = client.post(
        "/integration/turn/roll",
        json={
            "pending_roll_id": "42:" + "a" * 24,
            "rolls": [17, 8],
            "query": "Estado de campaña.",
            "answer_external_turn_id": "answer-" + "b" * 24,
        },
    )

    assert response.status_code == 200
    assert response.json()["lifecycle_state"] == "narration_pending"
    assert response.json()["context"]["context"] == "Estado actual."
    assert captured == {
        "pending_roll_id": "42:" + "a" * 24,
        "rolls": (17, 8),
        "adapter_namespace": "sillytavern",
        "defer_narration": True,
        "answer_external_turn_id": "answer-" + "b" * 24,
    }

def test_silly_tavern_manual_roll_endpoint_rejects_invalid_dice_results(client):
    response = client.post(
        "/integration/turn/roll",
        json={
            "pending_roll_id": "42:" + "a" * 24,
            "rolls": [0, 21],
            "query": "Estado de campaña.",
            "answer_external_turn_id": "answer-" + "b" * 24,
        },
    )
    assert response.status_code == 422

def test_silly_tavern_clarification_endpoint_returns_manual_roll_challenge(client, monkeypatch):
    captured = {}

    class FakeLock:
        def acquire(self):
            return nullcontext()

    preparation = SimpleNamespace(
        resolution_id=42,
        lifecycle_state="awaiting_input",
        committed_resolution='{"manual_roll_required": true}',
        clarification_question=None,
        pending_clarification_id=None,
        pending_roll_id="42:" + "a" * 24,
        pending_roll={"count": 1, "ability": "dexterity", "modifier": 3, "dc": 14},
    )

    def fake_submit(pending_clarification_id, answer, **kwargs):
        captured.update({
            "pending_clarification_id": pending_clarification_id,
            "answer": answer,
            **kwargs,
        })
        return preparation

    runtime = SimpleNamespace(
        turn_execution_lock=FakeLock(),
        durable_native_turn_service=SimpleNamespace(submit_clarification=fake_submit),
        silly_tavern_integration_service=SimpleNamespace(
            get_context=lambda query: {
                "campaign": {"id": 1, "name": "Campaña"},
                "session": None,
                "active_character": None,
                "context": {"query": query, "context": "Estado actual."},
            }
        ),
    )
    monkeypatch.setattr("api.routers.integration.get_current_runtime", lambda: runtime)

    response = client.post(
        "/integration/turn/clarification",
        json={
            "pending_clarification_id": "41:" + "b" * 24,
            "answer": "La puerta de roble.",
            "answer_external_turn_id": "answer-" + "c" * 24,
            "query": "Estado de campaña.",
        },
    )

    assert response.status_code == 200
    assert response.json()["pending_roll_id"] == "42:" + "a" * 24
    assert response.json()["pending_roll"]["count"] == 1
    assert captured["adapter_namespace"] == "sillytavern"
    assert captured["defer_narration"] is True

def test_integration_resolve_maps_wrapped_provider_failure_to_503(
    client,
    monkeypatch,
):
    from services.providers import LLMProviderError
    from services.turns.durable_native_turn_service import DurableNativeTurnError
    from services.turns.turn_resolution_service import TurnResolutionServiceError

    runtime = __import__("app").runtime_factory.get_runtime(1)

    def fail_prepare(*args, **kwargs):
        try:
            try:
                raise LLMProviderError("connection refused")
            except LLMProviderError as provider_error:
                raise TurnResolutionServiceError("proposal failed") from provider_error
        except TurnResolutionServiceError as resolver_error:
            raise DurableNativeTurnError("native turn execution failed") from resolver_error

    monkeypatch.setattr(
        runtime.durable_native_turn_service,
        "prepare_external_turn",
        fail_prepare,
    )

    response = client.post(
        "/integration/turn/resolve",
        json={
            "player_input": "Hablo con Mara.",
            "external_turn_id": "st-provider-outage",
            "query": "Contexto.",
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The language model provider is temporarily unavailable.",
        "code": "llm_provider_unavailable",
    }

def test_integration_resolve_maps_invalid_model_response_to_502(
    client,
    monkeypatch,
):
    from services.llm_world import LLMExtractionError
    from services.turns.durable_native_turn_service import DurableNativeTurnError
    from services.turns.turn_resolution_service import TurnResolutionServiceError

    runtime = __import__("app").runtime_factory.get_runtime(1)

    def fail_prepare(*args, **kwargs):
        try:
            try:
                raise LLMExtractionError("Unknown operation type")
            except LLMExtractionError as extraction_error:
                raise TurnResolutionServiceError("proposal failed") from extraction_error
        except TurnResolutionServiceError as resolver_error:
            raise DurableNativeTurnError("native turn execution failed") from resolver_error

    monkeypatch.setattr(
        runtime.durable_native_turn_service,
        "prepare_external_turn",
        fail_prepare,
    )

    response = client.post(
        "/integration/turn/resolve",
        json={
            "player_input": "Hablo con Mara.",
            "external_turn_id": "st-invalid-model-response",
            "query": "Contexto.",
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Internal server error",
        "code": "invalid_llm_response",
    }

def test_adapter_exposes_only_active_read_contract():
    assert not hasattr(
        integration_module.SillyTavernIntegrationService,
        "process_turn",
    )
    assert not hasattr(
        integration_module.SillyTavernIntegrationService,
        "_restore_world_state",
    )


# ============================================================
# DURABLE INTEGRATION ROUTE ERROR CONTRACTS
# ============================================================


def _runtime_with_fake_lock(**services):
    class FakeLock:
        def acquire(self):
            return nullcontext()

    return SimpleNamespace(
        turn_execution_lock=FakeLock(),
        **services,
    )


def _raise_error(error):
    def fail(*args, **kwargs):
        raise error

    return fail


def test_integration_context_endpoint_maps_unexpected_service_failure(
    client,
    monkeypatch,
):
    from types import SimpleNamespace

    runtime = _runtime_with_fake_lock(
        silly_tavern_integration_service=SimpleNamespace(
            get_context=_raise_error(RuntimeError("unexpected context failure"))
        )
    )
    monkeypatch.setattr(
        "api.routers.integration.get_current_runtime",
        lambda: runtime,
    )

    response = client.post(
        "/integration/context",
        json={"query": "Estado de campaña."},
    )

    assert response.status_code == 500


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (ValueError("invalid external turn id"), 400),
        (integration_module.SillyTavernIntegrationServiceError("storage failed"), 500),
        (RuntimeError("unexpected storage failure"), 500),
    ],
)
def test_integration_turn_state_endpoint_maps_read_errors(
    client,
    monkeypatch,
    error,
    expected_status,
):
    from types import SimpleNamespace

    runtime = _runtime_with_fake_lock(
        silly_tavern_integration_service=SimpleNamespace(
            get_external_turn_state=_raise_error(error)
        )
    )
    monkeypatch.setattr(
        "api.routers.integration.get_current_runtime",
        lambda: runtime,
    )

    response = client.get("/integration/turn/external-turn-error")

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (
            DurableNativeTurnError("clarification missing"),
            400,
        ),
        (RuntimeError("unexpected clarification failure"), 500),
    ],
)
def test_integration_clarification_state_endpoint_maps_read_errors(
    client,
    monkeypatch,
    error,
    expected_status,
):
    from types import SimpleNamespace

    runtime = _runtime_with_fake_lock(
        durable_native_turn_service=SimpleNamespace(
            get_external_clarification_state=_raise_error(error)
        )
    )
    monkeypatch.setattr(
        "api.routers.integration.get_current_runtime",
        lambda: runtime,
    )

    response = client.get(
        "/integration/turn/external-turn-error/clarification"
    )

    assert response.status_code == expected_status


def test_integration_manual_roll_state_endpoint_maps_durable_error(
    client,
    monkeypatch,
):
    from types import SimpleNamespace

    runtime = _runtime_with_fake_lock(
        durable_native_turn_service=SimpleNamespace(
            get_external_manual_roll_state=_raise_error(
                DurableNativeTurnError("manual roll missing")
            )
        )
    )
    monkeypatch.setattr(
        "api.routers.integration.get_current_runtime",
        lambda: runtime,
    )

    response = client.get("/integration/turn/external-turn-error/manual-roll")

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (
            integration_module.SillyTavernIntegrationServiceError(
                "context projection failed"
            ),
            500,
        ),
        (RuntimeError("unexpected context failure"), 500),
    ],
)
def test_integration_resolve_endpoint_maps_context_failures(
    client,
    monkeypatch,
    error,
    expected_status,
):
    from types import SimpleNamespace

    runtime = _runtime_with_fake_lock(
        durable_native_turn_service=SimpleNamespace(
            prepare_external_turn=lambda *args, **kwargs: SimpleNamespace(
                resolution_id=12,
                lifecycle_state="narration_pending",
                committed_resolution="{}",
                clarification_question=None,
            )
        ),
        silly_tavern_integration_service=SimpleNamespace(
            get_context=_raise_error(error)
        ),
    )
    monkeypatch.setattr(
        "api.routers.integration.get_current_runtime",
        lambda: runtime,
    )

    response = client.post(
        "/integration/turn/resolve",
        json={
            "player_input": "Abro la puerta.",
            "external_turn_id": "st-context-error",
            "query": "Estado.",
        },
    )

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (DurableNativeTurnError("invalid roll"), 409),
        (
            integration_module.SillyTavernIntegrationServiceError(
                "context projection failed"
            ),
            500,
        ),
        (RuntimeError("unexpected roll failure"), 500),
    ],
)
def test_integration_manual_roll_endpoint_maps_submission_errors(
    client,
    monkeypatch,
    error,
    expected_status,
):
    from types import SimpleNamespace

    runtime = _runtime_with_fake_lock(
        durable_native_turn_service=SimpleNamespace(
            submit_manual_roll=_raise_error(error)
        ),
        silly_tavern_integration_service=SimpleNamespace(
            get_context=lambda query: {}
        ),
    )
    monkeypatch.setattr(
        "api.routers.integration.get_current_runtime",
        lambda: runtime,
    )

    response = client.post(
        "/integration/turn/roll",
        json={
            "pending_roll_id": "42:challenge",
            "rolls": [12],
            "query": "Estado.",
            "answer_external_turn_id": "st-roll-reply-error",
        },
    )

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (
            DurableNativeTurnError("invalid clarification"),
            409,
        ),
        (
            integration_module.SillyTavernIntegrationServiceError(
                "context projection failed"
            ),
            500,
        ),
        (RuntimeError("unexpected clarification failure"), 500),
    ],
)
def test_integration_clarification_endpoint_maps_submission_errors(
    client,
    monkeypatch,
    error,
    expected_status,
):
    from types import SimpleNamespace

    runtime = _runtime_with_fake_lock(
        durable_native_turn_service=SimpleNamespace(
            submit_clarification=_raise_error(error)
        ),
        silly_tavern_integration_service=SimpleNamespace(
            get_context=lambda query: {}
        ),
    )
    monkeypatch.setattr(
        "api.routers.integration.get_current_runtime",
        lambda: runtime,
    )

    response = client.post(
        "/integration/turn/clarification",
        json={
            "pending_clarification_id": "42:challenge",
            "answer": "La puerta de roble.",
            "query": "Estado.",
            "answer_external_turn_id": "st-clarification-reply-error",
        },
    )

    assert response.status_code == expected_status


def test_integration_complete_endpoint_maps_unexpected_persistence_failure(
    client,
    monkeypatch,
):
    from types import SimpleNamespace

    runtime = SimpleNamespace(
        durable_native_turn_service=SimpleNamespace(
            complete_external_narration=_raise_error(
                RuntimeError("unexpected persistence failure")
            )
        )
    )
    monkeypatch.setattr(
        "api.routers.integration.get_current_runtime",
        lambda: runtime,
    )

    response = client.post(
        "/integration/turn/complete",
        json={
            "player_input": "Abro la puerta.",
            "narrative": "La puerta se abre.",
            "external_turn_id": "st-complete-error",
        },
    )

    assert response.status_code == 500
