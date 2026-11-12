from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import app
from models.activity_event import ActivityEvent
from models.campaign_scope import CampaignScope
from repositories.activity_event_repository import ActivityEventRepository
from repositories.campaign_repository import CampaignRepository
from services.activity import CampaignActivityService


def make_event(
    *,
    campaign_id: int = 1,
    dedupe_key: str = "resolution:1:accepted",
    summary: str = "Turn accepted",
) -> ActivityEvent:
    return ActivityEvent(
        campaign_id=campaign_id,
        resolution_id=1,
        session_id=None,
        turn_id=None,
        event_type="turn.accepted",
        summary=summary,
        details={"adapter": "native", "dice_mode": "automatic"},
        request_id="request-123",
        dedupe_key=dedupe_key,
    )


def test_activity_repository_deduplicates_inside_campaign_and_checks_scope(
    isolated_database,
):
    repository = ActivityEventRepository()
    scope = CampaignScope(1)

    first = repository.create(
        make_event(),
        scope=scope,
    )
    duplicate = repository.create(
        make_event(),
        scope=scope,
    )

    assert first.id == duplicate.id
    assert repository.count_events(scope=scope) == 1

    with pytest.raises(ValueError, match="does not match scope"):
        repository.create(
            make_event(campaign_id=2),
            scope=scope,
        )


def test_activity_event_contract_rejects_unapproved_details_and_unknown_types():
    with pytest.raises(ValueError, match="unsupported fields"):
        ActivityEvent(
            campaign_id=1,
            event_type="turn.accepted",
            summary="Turn accepted",
            dedupe_key="unsafe",
            details={"prompt": "do not store prompts"},
        )

    with pytest.raises(ValueError, match="unsupported activity event type"):
        ActivityEvent(
            campaign_id=1,
            event_type="llm.prompt",
            summary="Prompt captured",
            dedupe_key="unsafe-type",
        )


def test_campaign_activity_service_records_only_safe_turn_metadata(isolated_database):
    service = CampaignActivityService(scope=CampaignScope(1))
    record = SimpleNamespace(
        id=9,
        campaign_id=1,
        adapter_namespace="native",
        session_id=1,
        attempt_count=1,
    )

    from database import transaction

    with transaction("IMMEDIATE") as conn:
        service.record_turn_accepted(
            record,
            dice_mode="manual",
            conn=conn,
        )
        service.record_turn_awaiting_input(
            record,
            challenge_type="manual_roll",
            conn=conn,
        )

    page = service.list_activity(limit=10)
    assert page.total == 2
    events = {item.event_type: item for item in page.items}
    assert events["turn.accepted"].details == {
        "adapter": "native",
        "dice_mode": "manual",
    }
    assert events["turn.awaiting_input"].details == {
        "challenge_type": "manual_roll",
    }
    assert all("prompt" not in item.details for item in page.items)


def test_activity_api_is_campaign_scoped_and_paginates_newest_first(isolated_database):
    repository = ActivityEventRepository()
    first_scope = CampaignScope(1)
    second = CampaignRepository().create_campaign(
        name="Second activity campaign",
        system="D&D 5e 2014",
    )
    second_scope = CampaignScope(second["id"])

    for index in range(4):
        repository.create(
            make_event(
                dedupe_key=f"resolution:{index + 1}:accepted",
                summary=f"Turn {index + 1} accepted",
            ),
            scope=first_scope,
        )
    repository.create(
        make_event(
            campaign_id=second_scope.campaign_id,
            dedupe_key="other-campaign:accepted",
            summary="Other campaign turn accepted",
        ),
        scope=second_scope,
    )

    first_client = TestClient(
        app,
        headers={"X-Campaign-Id": "1"},
    )
    response = first_client.get("/activity?limit=2&offset=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert [item["summary"] for item in payload["items"]] == [
        "Turn 3 accepted",
        "Turn 2 accepted",
    ]
    assert all("request_id" not in item for item in payload["items"])
    assert all("dedupe_key" not in item for item in payload["items"])

    second_client = TestClient(
        app,
        headers={"X-Campaign-Id": str(second_scope.campaign_id)},
    )
    other_payload = second_client.get("/activity").json()
    assert other_payload["total"] == 1
    assert other_payload["items"][0]["summary"] == "Other campaign turn accepted"


def test_activity_api_filters_by_resolution_and_event_type(isolated_database):
    repository = ActivityEventRepository()
    scope = CampaignScope(1)
    repository.create(make_event(dedupe_key="accepted-1"), scope=scope)
    committed = ActivityEvent(
        campaign_id=1,
        resolution_id=1,
        event_type="turn.committed",
        summary="World changes committed",
        details={
            "operation_count": 2,
            "successful_operation_count": 2,
            "failed_operation_count": 0,
            "world_changed": True,
        },
        dedupe_key="committed-1",
    )
    repository.create(committed, scope=scope)

    client = TestClient(app, headers={"X-Campaign-Id": "1"})
    response = client.get(
        "/activity?resolution_id=1&event_type=turn.committed"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["event_type"] == "turn.committed"
    assert payload["items"][0]["details"]["world_changed"] is True


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
        "resolution_id=0",
        "event_type=raw_prompt",
    ],
)
def test_activity_api_rejects_invalid_filters(isolated_database, query):
    client = TestClient(app, headers={"X-Campaign-Id": "1"})
    response = client.get(f"/activity?{query}")
    assert response.status_code == 422
