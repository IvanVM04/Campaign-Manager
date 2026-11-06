import json
from types import SimpleNamespace

import pytest

from services.turns import (
    DurableTurnChallengeStateService,
)
from services.turns.durable_native_turn_service import DurableNativeTurnError


class FakeResolutionRepository:
    def __init__(self, record=None):
        self.record = record
        self.request = None

    def get_by_idempotency_key(self, namespace, key, *, scope):
        self.request = (namespace, key, scope)
        return self.record


class FakeTurnRepository:
    def __init__(self, active_turn=None):
        self.active_turn = active_turn
        self.request = None

    def get_active_by_external_turn_id(self, external_turn_id, *, scope):
        self.request = (external_turn_id, scope)
        return self.active_turn


def make_service(record=None, active_turn=None):
    scope = object()
    resolution_repository = FakeResolutionRepository(record)
    turn_repository = FakeTurnRepository(active_turn)
    service = DurableTurnChallengeStateService(
        scope=scope,
        turn_repository=turn_repository,
        resolution_repository=resolution_repository,
        error_type=DurableNativeTurnError,
    )
    return service, scope, resolution_repository, turn_repository


def test_clarification_state_reports_missing_turn_without_leaking_other_data():
    service, scope, repository, _ = make_service()

    state = service.get_external_clarification_state("  external-1  ")

    assert state == {
        "external_turn_id": "external-1",
        "has_clarification": False,
        "lifecycle_state": None,
    }
    assert repository.request == ("sillytavern", "external-1", scope)


def test_clarification_state_exposes_active_challenge_and_recovery_data():
    record = SimpleNamespace(
        id=7,
        lifecycle_state="awaiting_input",
        player_input="Abro la puerta.",
        adjudication_json=json.dumps({
            "clarification": {
                "challenge_id": "opaque-token",
                "question": "¿Qué puerta?",
            },
            "clarification_history": [{"question": "¿Dónde?", "answer": "Norte"}],
            "last_challenge_id": "previous-token",
            "last_answer": "Norte",
            "last_answer_external_turn_id": "answer-1",
            "resolved_player_input": "Abro la puerta norte.",
        }),
    )
    service, scope, _, turn_repository = make_service(
        record, SimpleNamespace(narrative="La puerta se abre.")
    )

    state = service.get_external_clarification_state("external-2")

    assert state["has_clarification"] is True
    assert state["pending_clarification_id"] == "7:opaque-token"
    assert state["last_pending_clarification_id"] == "7:previous-token"
    assert state["clarification_question"] == "¿Qué puerta?"
    assert state["last_answer_external_turn_id"] == "answer-1"
    assert state["narrative"] == "La puerta se abre."
    assert turn_repository.request == ("external-2", scope)


def test_manual_roll_state_sanitizes_internal_adjudication_fields():
    pending = {
        "challenge_id": "opaque-token",
        "count": 2,
        "dice": "d20",
        "kind": "skill_check",
        "modifier": 5,
        "decision": {"dc": 15, "reason": "private"},
    }
    record = SimpleNamespace(
        id=42,
        lifecycle_state="awaiting_input",
        player_input="Me escondo.",
        adjudication_json=json.dumps({"manual_roll": pending}),
    )
    service, _, _, _ = make_service(record)

    state = service.get_external_manual_roll_state("external-3")

    assert state["has_manual_roll"] is True
    assert state["pending_roll_id"] == "42:opaque-token"
    assert state["pending_roll"] == {
        "count": 2,
        "dice": "d20",
        "kind": "skill_check",
        "modifier": 5,
    }


def test_completed_manual_roll_is_recoverable_for_same_external_reply():
    pending = {
        "challenge_id": "opaque-token",
        "submitted_external_turn_id": "answer-1",
        "submitted_rolls": [14],
        "count": 1,
    }
    record = SimpleNamespace(
        id=12,
        lifecycle_state="completed",
        player_input="Me escondo.",
        adjudication_json=json.dumps({"manual_roll": pending}),
    )
    service, _, _, _ = make_service(record)

    state = service.get_external_manual_roll_state("external-4")

    assert state["has_manual_roll"] is True
    assert state["submitted_external_turn_id"] == "answer-1"
    assert state["pending_roll_id"] == "12:opaque-token"
    assert "submitted_rolls" not in state["pending_roll"]


def test_challenge_state_rejects_invalid_external_turn_identity():
    service, _, _, _ = make_service()

    with pytest.raises(DurableNativeTurnError, match="external_turn_id"):
        service.get_external_clarification_state(" ")
    with pytest.raises(DurableNativeTurnError, match="external_turn_id"):
        service.get_external_manual_roll_state("")
