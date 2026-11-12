from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest

import integrations.adapters.silly_tavern.context_adapter as adapter_module
from bootstrap.campaign_runtime import CampaignRuntimeFactory
from integrations.adapters.silly_tavern import (
    SillyTavernContextAdapter,
    SillyTavernIntegrationService,
    SillyTavernIntegrationServiceError,
)
from models.campaign_scope import CampaignScope
from models.character_state import CharacterState
from models.session_state import SessionState
from services.campaign import CampaignStateServiceError


@pytest.fixture
def runtime():
    return CampaignRuntimeFactory().get_runtime(1)


@pytest.fixture
def adapter(runtime):
    return runtime.silly_tavern_integration_service.context_adapter


def test_context_adapter_reads_and_normalizes_campaign_context(adapter):
    result = adapter.get_context("  Investigo la taberna.  ")

    assert result["campaign"]["id"] == 1
    assert result["query"] == "Investigo la taberna."
    assert result["context"]["query"] == "Investigo la taberna."
    assert result["session"] is None
    assert result["active_character"] is None


@pytest.mark.parametrize(
    ("query", "error"),
    [
        (None, TypeError),
        ("  ", ValueError),
    ],
)
def test_context_adapter_rejects_invalid_queries(adapter, query, error):
    with pytest.raises(error):
        adapter.get_context(query)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (CampaignStateServiceError("database unavailable"), "failed to obtain"),
        (RuntimeError("unexpected"), "CampaignStateService failed"),
    ],
)
def test_context_adapter_wraps_campaign_state_failures(
    adapter, monkeypatch, failure, message
):
    def fail(**kwargs):
        raise failure

    monkeypatch.setattr(adapter.campaign_state_service, "get_turn_context", fail)

    with pytest.raises(SillyTavernIntegrationServiceError, match=message):
        adapter.get_context("Miro alrededor.")


def test_context_adapter_rejects_invalid_turn_context(adapter, monkeypatch):
    monkeypatch.setattr(
        adapter.campaign_state_service, "get_turn_context", lambda **kwargs: object()
    )

    with pytest.raises(SillyTavernIntegrationServiceError, match="invalid TurnContext"):
        adapter.get_context("Miro alrededor.")


def test_context_adapter_wraps_recent_turn_repository_failure(adapter, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("read failure")

    monkeypatch.setattr(adapter.turn_repository, "list_recent_active_turns", fail)

    with pytest.raises(
        SillyTavernIntegrationServiceError, match="recent active turn history"
    ):
        adapter.get_context("Miro alrededor.")


def test_context_adapter_wraps_context_builder_failure(adapter, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("render failure")

    monkeypatch.setattr(adapter.context_builder, "build", fail)

    with pytest.raises(SillyTavernIntegrationServiceError, match="build context"):
        adapter.get_context("Miro alrededor.")


def test_context_adapter_excludes_requested_turn_and_serializes_optional_state(
    adapter, runtime, monkeypatch
):
    context = runtime.campaign_state_service.get_turn_context(campaign_id=1)
    session = SessionState(
        session_id=12,
        number=3,
        title="La taberna",
        summary="Una noche lluviosa.",
        start_location="Puenteviejo",
        end_location="",
        notes="Hablar con Aldric",
    )
    character = CharacterState(entity_id=44, level=4, class_name="Rogue")
    context = replace(context, current_session=session, active_character=character)
    monkeypatch.setattr(
        adapter.campaign_state_service, "get_turn_context", lambda **kwargs: context
    )
    monkeypatch.setattr(
        adapter.turn_repository,
        "list_recent_active_turns",
        lambda **kwargs: [
            SimpleNamespace(external_turn_id="current-turn"),
            SimpleNamespace(external_turn_id="older-turn"),
        ],
    )
    captured = {}

    def build(world, query, *, recent_turns):
        captured["recent_turns"] = recent_turns
        return {"query": query, "context": "Contexto filtrado."}

    monkeypatch.setattr(adapter.context_builder, "build", build)

    result = adapter.get_context(
        "Aldric", exclude_external_turn_id="current-turn"
    )

    assert [turn.external_turn_id for turn in captured["recent_turns"]] == [
        "older-turn"
    ]
    assert result["session"] == {
        "id": 12,
        "number": 3,
        "title": "La taberna",
        "summary": "Una noche lluviosa.",
        "start_location": "Puenteviejo",
        "end_location": "",
        "notes": "Hablar con Aldric",
    }
    assert result["active_character"] == {
        "entity_id": 44,
        "level": 4,
        "class_name": "Rogue",
        "current_hp": 0,
        "max_hp": 0,
        "armor_class": 10,
        "strength": 10,
        "dexterity": 10,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10,
        "proficiency_bonus": 2,
    }
    assert result["context"]["context"] == "Contexto filtrado."


def test_context_adapter_external_turn_state_when_no_transcript_exists(
    adapter, monkeypatch
):
    monkeypatch.setattr(
        adapter_module, "get_conn", lambda: nullcontext(object())
    )
    monkeypatch.setattr(
        adapter.turn_repository,
        "get_active_by_external_turn_id",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        adapter.turn_repository,
        "get_versions_by_external_turn_id",
        lambda *args, **kwargs: [
            SimpleNamespace(version=2),
            SimpleNamespace(version=4),
        ],
    )

    state = adapter.get_external_turn_state("  external-123  ")

    assert state == {
        "external_turn_id": "external-123",
        "exists": False,
        "active_version": 0,
        "next_version": 5,
        "narrative": None,
    }


def test_context_adapter_external_turn_state_returns_active_version(
    adapter, monkeypatch
):
    monkeypatch.setattr(
        adapter_module, "get_conn", lambda: nullcontext(object())
    )
    monkeypatch.setattr(
        adapter.turn_repository,
        "get_active_by_external_turn_id",
        lambda *args, **kwargs: SimpleNamespace(version=3, narrative="La puerta se abre."),
    )
    monkeypatch.setattr(
        adapter.turn_repository,
        "get_versions_by_external_turn_id",
        lambda *args, **kwargs: [
            SimpleNamespace(version=1),
            SimpleNamespace(version=2),
            SimpleNamespace(version=3),
        ],
    )

    state = adapter.get_external_turn_state("external-123")

    assert state == {
        "external_turn_id": "external-123",
        "exists": True,
        "active_version": 3,
        "next_version": 4,
        "narrative": "La puerta se abre.",
    }


@pytest.mark.parametrize(
    ("external_turn_id", "error"),
    [
        (None, TypeError),
        ("  ", ValueError),
        ("x" * 501, ValueError),
    ],
)
def test_context_adapter_rejects_invalid_external_turn_ids(
    adapter, external_turn_id, error
):
    with pytest.raises(error):
        adapter.get_external_turn_state(external_turn_id)


def test_context_adapter_wraps_active_turn_repository_failure(adapter, monkeypatch):
    monkeypatch.setattr(
        adapter_module, "get_conn", lambda: nullcontext(object())
    )

    def fail(*args, **kwargs):
        raise RuntimeError("database read failed")

    monkeypatch.setattr(
        adapter.turn_repository, "get_active_by_external_turn_id", fail
    )

    with pytest.raises(
        SillyTavernIntegrationServiceError, match="external turn state"
    ):
        adapter.get_external_turn_state("external-123")


def test_context_adapter_wraps_version_history_failure(adapter, monkeypatch):
    monkeypatch.setattr(
        adapter_module, "get_conn", lambda: nullcontext(object())
    )
    monkeypatch.setattr(
        adapter.turn_repository,
        "get_active_by_external_turn_id",
        lambda *args, **kwargs: None,
    )

    def fail(*args, **kwargs):
        raise RuntimeError("version read failed")

    monkeypatch.setattr(
        adapter.turn_repository, "get_versions_by_external_turn_id", fail
    )

    with pytest.raises(
        SillyTavernIntegrationServiceError, match="turn version history"
    ):
        adapter.get_external_turn_state("external-123")


def test_context_adapter_constructor_validates_each_dependency(runtime):
    valid = {
        "campaign_scope": CampaignScope(1),
        "campaign_state_service": runtime.campaign_state_service,
        "context_builder": runtime.context_builder,
        "turn_repository": runtime.turn_repository,
    }
    for name in valid:
        invalid = dict(valid)
        invalid[name] = object()
        with pytest.raises(TypeError, match=name):
            SillyTavernContextAdapter(**invalid)


def test_integration_service_is_a_thin_delegating_facade(adapter, monkeypatch):
    service = SillyTavernIntegrationService(context_adapter=adapter)
    monkeypatch.setattr(adapter, "get_context", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(
        adapter,
        "get_external_turn_state",
        lambda external_turn_id: {"external_turn_id": external_turn_id},
    )

    assert service.get_context("consulta") == {"ok": True}
    assert service.get_external_turn_state("turn-9") == {
        "external_turn_id": "turn-9"
    }


def test_integration_service_rejects_invalid_context_adapter():
    with pytest.raises(TypeError, match="context_adapter"):
        SillyTavernIntegrationService(context_adapter=object())




def test_context_adapter_keeps_additional_retrieval_queries_separate(
    adapter, monkeypatch
):
    context = adapter.campaign_state_service.get_turn_context(campaign_id=1)
    monkeypatch.setattr(
        adapter.campaign_state_service,
        "get_turn_context",
        lambda **kwargs: context,
    )
    monkeypatch.setattr(
        adapter.turn_repository,
        "list_recent_active_turns",
        lambda **kwargs: [],
    )
    captured = {}

    def build(world, query, *, recent_turns, supplemental_queries):
        captured["query"] = query
        captured["supplemental_queries"] = supplemental_queries
        return {
            "query": query,
            "entities": [{"id": 1}],
            "items": [],
            "item_instances": [],
            "resources": [],
            "resource_balances": [],
            "relations": [],
            "events": [],
            "context": "Contexto recuperado.",
        }

    monkeypatch.setattr(adapter.context_builder, "build", build)
    result = adapter.get_context(
        "Me acerco al tabernero y le pregunto por los rumores.",
        additional_queries=("Estado general de la campaña.",),
    )

    assert captured == {
        "query": "Me acerco al tabernero y le pregunto por los rumores.",
        "supplemental_queries": ("Estado general de la campaña.",),
    }
    assert result["retrieval_diagnostics"] == {
        "query_count": 2,
        "supplemental_query_count": 1,
        "included_record_counts": {
            "entities": 1,
            "items": 0,
            "item_instances": 0,
            "resources": 0,
            "resource_balances": 0,
            "relations": 0,
            "events": 0,
        },
    }


def test_context_adapter_deduplicates_additional_queries(
    adapter, monkeypatch
):
    context = adapter.campaign_state_service.get_turn_context(campaign_id=1)
    monkeypatch.setattr(
        adapter.campaign_state_service,
        "get_turn_context",
        lambda **kwargs: context,
    )
    monkeypatch.setattr(
        adapter.turn_repository,
        "list_recent_active_turns",
        lambda **kwargs: [],
    )
    captured = {}

    def build(world, query, *, recent_turns, supplemental_queries):
        captured["supplemental_queries"] = supplemental_queries
        return {"query": query, "context": "Contexto.", "entities": []}

    monkeypatch.setattr(adapter.context_builder, "build", build)
    result = adapter.get_context(
        "Aldric",
        additional_queries=("Aldric", "  ", "Campaña general"),
    )

    assert captured["supplemental_queries"] == ("Campaña general",)
    assert result["retrieval_diagnostics"]["query_count"] == 2
