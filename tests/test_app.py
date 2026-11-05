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
        self,
        player_input,
        *,
        idempotency_key=None,
    ):
        assert player_input == "Pregunto por Aldric."
        return FakeResult()

    monkeypatch.setattr(
        "services.durable_native_turn_service.DurableNativeTurnService.play_turn",
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
    assert data["mechanics"] is None


def test_play_turn_returns_400_when_campaign_turn_service_fails(
    client,
    monkeypatch,
):
    def fake_play_turn(
        self,
        player_input,
        *,
        idempotency_key=None,
    ):
        from services.durable_native_turn_service import DurableNativeTurnError
        raise DurableNativeTurnError(
            "Turn resolution failed."
        )

    monkeypatch.setattr(
        "services.durable_native_turn_service.DurableNativeTurnService.play_turn",
        fake_play_turn,
    )

    response = client.post(
        "/turn",
        json={
            "player_input": "Pregunto por Aldric.",
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": "Turn resolution failed.",
        "code": "conflict",
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
        self,
        player_input,
        *,
        idempotency_key=None,
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
        "services.durable_native_turn_service.DurableNativeTurnService.play_turn",
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
    from app import runtime_factory

    runtime = runtime_factory.get_runtime(1)
    assert (
        runtime.campaign_turn_service.turn_execution_lock
        is runtime.turn_execution_lock
    )
    assert (
        runtime.silly_tavern_integration_service.turn_execution_lock
        is runtime.turn_execution_lock
    )

def test_update_campaign_session_rejects_nonexistent_session(client):
    campaign_repository = CampaignRepository()
    campaign_before = campaign_repository.get_campaign(1)
    assert campaign_before["current_session_id"] is None
    current_session_before = campaign_before["current_session_id"]

    response = client.patch(
        "/campaign/session",
        json={
            "session_id": 999999,
        },
    )

    assert response.status_code == 400

    campaign_after = campaign_repository.get_campaign(1)

    assert campaign_after["current_session_id"] == current_session_before

def test_world_endpoint_waits_for_turn_execution_lock(client):
    from app import runtime_factory

    turn_execution_lock = runtime_factory.get_runtime(1).turn_execution_lock
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


def test_campaign_header_is_required_for_campaign_endpoints():
    from fastapi.testclient import TestClient

    from app import app

    response = TestClient(app).get("/campaign/state")

    assert response.status_code == 400
    assert response.json() == {
        "detail": "X-Campaign-Id header is required",
        "code": "bad_request",
    }


def test_campaign_header_rejects_unknown_campaign(client):
    response = client.get(
        "/campaign/state",
        headers={"X-Campaign-Id": "999999"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_runtime_factory_builds_isolated_services_for_each_campaign(
    isolated_database,
):
    from database import execute
    from services.campaign_runtime import CampaignRuntimeFactory

    execute(
        "INSERT INTO campaign (id, name, system) VALUES (?, ?, ?)",
        (2, "Second campaign", "D&D 5e 2014"),
    )

    factory = CampaignRuntimeFactory()
    first = factory.get_runtime(1)
    second = factory.get_runtime(2)

    assert first is not second
    assert first.scope.campaign_id == 1
    assert second.scope.campaign_id == 2
    assert first.world_service is not second.world_service
    assert first.world_service.world is not second.world_service.world
    assert first.turn_execution_lock is not second.turn_execution_lock
    assert first.campaign_state_service.campaign_id == 1
    assert second.campaign_state_service.campaign_id == 2


def test_campaigns_can_be_created_and_selected(client):
    created = client.post(
        "/campaigns",
        json={
            "name": "Second campaign",
            "system": "D&D 5e 2014",
        },
    )

    assert created.status_code == 201
    campaign = created.json()
    assert campaign["id"] == 2
    assert campaign["name"] == "Second campaign"

    listed = client.get("/campaigns")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [1, 2]

    selected = client.get(
        "/campaign/state",
        headers={"X-Campaign-Id": "2"},
    )
    assert selected.status_code == 200
    assert selected.json()["campaign_id"] == 2



def test_campaign_header_rejects_non_integer_campaign_id(client):
    response = client.get(
        "/campaign/state",
        headers={"X-Campaign-Id": "not-an-id"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"



@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"name": "   "},
        {"system": ""},
        {"system": "   "},
    ],
)
def test_update_campaign_rejects_blank_required_fields(
    client,
    payload,
):
    response = client.patch("/campaign", json=payload)

    assert response.status_code == 422


def test_update_campaign_trims_optional_text_fields(
    client,
):
    response = client.patch(
        "/campaign",
        json={
            "tone": "  heroic fantasy  ",
            "summary": "  A short campaign summary.  ",
        },
    )

    assert response.status_code == 200
    assert response.json()["tone"] == "heroic fantasy"
    assert response.json()["summary"] == "A short campaign summary."



def test_readiness_reports_database_ready(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "database": "ready",
    }


def test_readiness_returns_503_when_database_is_unavailable(
    client,
    monkeypatch,
):
    import database

    def fail_get_conn():
        raise OSError("private database path detail")

    monkeypatch.setattr(database, "get_conn", fail_get_conn)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "database unavailable",
        "code": "service_unavailable",
    }


def test_serialize_mechanics_result_exposes_dice_audit_data():
    from types import SimpleNamespace

    from app import _serialize_mechanics_result
    from rules_engine.dnd5e_2014.core.abilities import Ability
    from rules_engine.dnd5e_2014.core.dice import RollMode
    from rules_engine.dnd5e_2014.core.skills import Skill

    mechanics_result = SimpleNamespace(
        decision=SimpleNamespace(
            decision=SimpleNamespace(value="skill_check"),
            skill=Skill.STEALTH,
            reason="Evitar al guardia",
        ),
        check=SimpleNamespace(
            ability=Ability.DEXTERITY,
            dc=15,
            roll=SimpleNamespace(
                rolls=(12,),
                selected=12,
                mode=RollMode.NORMAL,
                modifier=5,
            ),
            total=17,
            success=True,
        ),
    )

    payload = _serialize_mechanics_result(mechanics_result)

    assert payload == {
        "decision": "skill_check",
        "skill": "stealth",
        "ability": "dexterity",
        "dc": 15,
        "rolls": [12],
        "selected": 12,
        "roll_mode": "normal",
        "modifier": 5,
        "total": 17,
        "success": True,
        "reason": "Evitar al guardia",
    }


def test_world_entity_bootstrap_is_atomic_and_idempotent(client):
    payload = {
        "entities": [
            {
                "name": "Mara",
                "entity_type": "npc",
                "description": "Posadera de la posada.",
                "notes": "Vio salir a Nilo.",
            },
            {
                "name": "Viejo puente",
                "entity_type": "location",
                "description": "Puente de piedra.",
            },
        ]
    }

    first = client.post("/world/entities/bootstrap", json=payload)
    assert first.status_code == 200
    first_data = first.json()
    assert len(first_data["created"]) == 2
    assert [entity["name"] for entity in first_data["entities"]] == [
        "Mara",
        "Viejo puente",
    ]

    second = client.post("/world/entities/bootstrap", json=payload)
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["created"] == []
    assert second_data["entities"] == first_data["entities"]

    world = client.get("/world")
    assert world.status_code == 200
    assert len(world.json()["entities"]) == 2


def test_world_entity_bootstrap_rejects_duplicate_names_in_request(client):
    response = client.post(
        "/world/entities/bootstrap",
        json={
            "entities": [
                {"name": "Mara", "entity_type": "npc"},
                {"name": " mara ", "entity_type": "npc"},
            ]
        },
    )

    assert response.status_code == 422
