import threading

import pytest

from app import create_campaign_turn_service
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from services.campaign_state_service import CampaignStateService
from services.context_builder import ContextBuilder
from services.memory_search_service import MemorySearchService
from services.turn_execution_lock import TurnExecutionLock
from services.world_service import WorldService


def test_create_campaign_turn_service_uses_provided_context_builder():
    world_service = WorldService()

    memory_search_service = MemorySearchService()

    context_builder = ContextBuilder(
        memory_search_service=memory_search_service,
    )

    campaign_repository = CampaignRepository()

    character_repository = CharacterRepository()

    campaign_state_service = CampaignStateService(
        campaign_repository=campaign_repository,
        character_repository=character_repository,
        world_service=world_service,
        entity_repository=EntityRepository(),
    )

    turn_execution_lock = TurnExecutionLock()

    service = create_campaign_turn_service(
        world_service=world_service,
        context_builder=context_builder,
        campaign_state_service=campaign_state_service,
        turn_execution_lock=turn_execution_lock,
    )

    assert service.turn_resolution_service is not None
    assert service.campaign_state_service is campaign_state_service

    dm_service = service.turn_resolution_service.dm_service

    assert dm_service.context_builder is context_builder


def test_create_campaign_turn_service_rejects_invalid_context_builder():
    world_service = WorldService()

    campaign_repository = CampaignRepository()

    character_repository = CharacterRepository()

    campaign_state_service = CampaignStateService(
        campaign_repository=campaign_repository,
        character_repository=character_repository,
        world_service=world_service,
        entity_repository=EntityRepository(),
    )

    with pytest.raises(
        TypeError,
        match="context_builder must be a ContextBuilder",
    ):
        create_campaign_turn_service(
            world_service=world_service,
            context_builder="invalid",
            campaign_state_service=campaign_state_service,
            turn_execution_lock=TurnExecutionLock(),
        )

def test_get_turns_accepts_limit(client):
    response = client.get(
        "/turns?limit=5"
    )

    assert response.status_code == 200

    data = response.json()

    assert isinstance(data, list)
    assert len(data) <= 5


def test_get_turns_rejects_invalid_limit(client):
    response = client.get(
        "/turns?limit=0"
    )

    assert response.status_code == 422


def test_get_turns_rejects_limit_above_maximum(client):
    response = client.get(
        "/turns?limit=101"
    )

    assert response.status_code == 422


def test_get_turns_filters_by_session_and_limit(
    client,
    monkeypatch,
):
    calls = []

    def fake_list_turns(
        *,
        session_id=None,
        limit=None,
        scope=None,
    ):
        calls.append(
            {
                "session_id": session_id,
                "limit": limit,
            }
        )

        return []

    monkeypatch.setattr(
        "app.turn_repository.list_turns",
        fake_list_turns,
    )

    response = client.get(
        "/turns?session_id=7&limit=5"
    )

    assert response.status_code == 200
    assert response.json() == []

    assert calls == [
        {
            "session_id": 7,
            "limit": 5,
        }
    ]


def test_get_turns_uses_default_limit(
    client,
    monkeypatch,
):
    calls = []

    def fake_list_turns(
        *,
        session_id=None,
        limit=None,
    ):
        calls.append(
            {
                "session_id": session_id,
                "limit": limit,
            }
        )

        return []

    monkeypatch.setattr(
        "app.turn_repository.list_turns",
        fake_list_turns,
    )

    response = client.get(
        "/turns"
    )

    assert response.status_code == 200

    assert calls == [
        {
            "session_id": None,
            "limit": 50,
        }
    ]


def test_play_turn_rejects_missing_player_input(
    client,
):
    response = client.post(
        "/turn",
        json={},
    )

    assert response.status_code == 422


def test_play_turn_returns_turn_result(
    client,
    monkeypatch,
):
    class FakeResult:
        def __init__(self):
            self.narrative = "Aldric te observa desde la barra."
            self.player_input = "Pregunto por Aldric."
            self.operation_count = 1
            self.successful_operation_count = 1
            self.failed_operation_count = 0
            self.all_operations_succeeded = True
            self.world_changed = True
            self.operations = []
            self.operation_results = []

    def fake_play_turn(
        player_input,
    ):
        assert player_input == "Pregunto por Aldric."
        return FakeResult()

    monkeypatch.setattr(
        "app.campaign_turn_service.play_turn",
        fake_play_turn,
    )

    response = client.post(
        "/turn",
        json={
            "player_input": "Pregunto por Aldric.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["narrative"] == (
        "Aldric te observa desde la barra."
    )

    assert data["player_input"] == (
        "Pregunto por Aldric."
    )

    assert data["operation_count"] == 1
    assert data["successful_operation_count"] == 1
    assert data["failed_operation_count"] == 0
    assert data["all_operations_succeeded"] is True
    assert data["world_changed"] is True

    assert data["operations"] == []
    assert data["operation_results"] == []


def test_play_turn_returns_400_when_campaign_turn_service_fails(
    client,
    monkeypatch,
):
    from services.campaign_turn_service import (
        CampaignTurnServiceError,
    )

    def fake_play_turn(
        player_input,
    ):
        raise CampaignTurnServiceError(
            "Turn resolution failed."
        )

    monkeypatch.setattr(
        "app.campaign_turn_service.play_turn",
        fake_play_turn,
    )

    response = client.post(
        "/turn",
        json={
            "player_input": "Pregunto por Aldric.",
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": "Turn resolution failed."
    }


def test_create_session_rejects_invalid_number(
    client,
):
    response = client.post(
        "/sessions",
        json={
            "number": 0,
        },
    )

    assert response.status_code == 422


def test_create_session_rejects_negative_number(
    client,
):
    response = client.post(
        "/sessions",
        json={
            "number": -1,
        },
    )

    assert response.status_code == 422

def test_play_turn_rejects_empty_player_input(
    client,
):
    response = client.post(
        "/turn",
        json={
            "player_input": "",
        },
    )

    assert response.status_code == 422

def test_play_turn_rejects_whitespace_only_player_input(
    client,
):
    response = client.post(
        "/turn",
        json={
            "player_input": "   ",
        },
    )

    assert response.status_code == 422

def test_play_turn_rejects_player_input_above_maximum(
    client,
):
    response = client.post(
        "/turn",
        json={
            "player_input": "A" * 10001,
        },
    )

    assert response.status_code == 422


def test_memory_search_rejects_query_above_maximum(
    client,
):
    response = client.get(
        "/memory/search",
        params={
            "q": "A" * 1001,
        },
    )

    assert response.status_code == 422


def test_memory_context_rejects_query_above_maximum(
    client,
):
    response = client.get(
        "/memory/context",
        params={
            "q": "A" * 1001,
        },
    )

    assert response.status_code == 422


def test_play_turn_accepts_player_input_at_maximum_length(
    client,
    monkeypatch,
):
    from types import SimpleNamespace

    calls = []

    def fake_play_turn(
        player_input,
    ):
        calls.append(player_input)

        return SimpleNamespace(
            narrative="Narrativa.",
            player_input=player_input,
            operation_count=0,
            successful_operation_count=0,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=False,
            operations=[],
            operation_results=[],
        )

    monkeypatch.setattr(
        "app.campaign_turn_service.play_turn",
        fake_play_turn,
    )

    response = client.post(
        "/turn",
        json={
            "player_input": "A" * 10000,
        },
    )

    assert response.status_code == 200
    assert calls == ["A" * 10000]

def test_application_services_share_same_turn_execution_lock():
    from app import (
        campaign_turn_service,
        silly_tavern_integration_service,
        turn_execution_lock,
    )

    assert (
        campaign_turn_service.turn_execution_lock
        is turn_execution_lock
    )

    assert (
        silly_tavern_integration_service.turn_execution_lock
        is turn_execution_lock
    )

def test_update_campaign_session_rejects_nonexistent_session(client):
    campaign_repository = CampaignRepository()
    campaign_before = campaign_repository.get_campaign()
    assert campaign_before["current_session_id"] is None
    current_session_before = campaign_before["current_session_id"]

    response = client.patch(
        "/campaign/session",
        json={
            "session_id": 999999,
        },
    )

    assert response.status_code == 400

    campaign_after = campaign_repository.get_campaign()

    assert campaign_after["current_session_id"] == current_session_before

def test_world_endpoint_waits_for_turn_execution_lock(client):
    from app import turn_execution_lock

    turn_execution_lock._lock.acquire()

    try:
        result = {}

        def make_request():
            result["response"] = client.get("/world")

        thread = threading.Thread(target=make_request)
        thread.start()

        # La petición debe quedar bloqueada mientras nosotros
        # mantenemos el lock.
        thread.join(timeout=0.2)

        assert thread.is_alive()

    finally:
        turn_execution_lock._lock.release()

    thread.join(timeout=2)

    assert not thread.is_alive()
    assert result["response"].status_code == 200