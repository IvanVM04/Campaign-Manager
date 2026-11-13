import pytest

from models.turn_resolution_record import TurnResolutionRecord


def make_record(**overrides):
    values = {
        "campaign_id": 1,
        "player_input": "Investigo.",
        "adapter_namespace": "native",
        "idempotency_key": "req-1",
        "request_fingerprint": "sha256:abc",
    }
    values.update(overrides)
    return TurnResolutionRecord(**values)


def test_record_accepts_valid_lifecycle_states():
    valid_values = {
        "accepted": {},
        "planning": {
            "attempt_count": 1,
            "lease_token": "worker-a",
            "lease_expires_at": "2099-01-01T00:00:00Z",
        },
        "awaiting_input": {},
        "prepared": {
            "context_revision": 1,
            "proposal_json": '{"operations":[]}',
        },
        "committed": {"committed_at": "2026-11-04T00:00:00Z", "resulting_revision": 2},
        "narration_pending": {"committed_at": "2026-11-04T00:00:00Z", "resulting_revision": 2},
        "completed": {
            "committed_at": "2026-11-04T00:00:00Z",
            "resulting_revision": 2,
            "completed_at": "2026-11-04T00:01:00Z",
            "narrative": "Done.",
        },
        "rejected": {},
    }
    for state, values in valid_values.items():
        assert make_record(lifecycle_state=state, **values).lifecycle_state == state


def test_record_rejects_unknown_lifecycle_state():
    with pytest.raises(ValueError, match="lifecycle_state"):
        make_record(lifecycle_state="running")


def test_record_rejects_empty_request_identity():
    with pytest.raises(ValueError):
        make_record(idempotency_key=" ")


def test_record_rejects_invalid_json_proposal():
    with pytest.raises(ValueError, match="valid JSON"):
        make_record(proposal_json="{broken")


def test_record_requires_lease_fields_together():
    with pytest.raises(ValueError, match="set together"):
        make_record(lease_token="worker-a")


def test_record_rejects_boolean_attempt_count():
    with pytest.raises(TypeError, match="attempt_count"):
        make_record(attempt_count=True)


def test_transition_graph_is_one_way_after_commit():
    record = make_record(
        lifecycle_state="committed",
        committed_at="2026-11-04T00:00:00Z",
        resulting_revision=2,
    )
    assert record.can_transition_to("narration_pending")
    assert not record.can_transition_to("planning")
    assert not record.can_transition_to("prepared")


def test_record_enforces_state_specific_requirements():
    with pytest.raises(ValueError, match="active lease"):
        make_record(lifecycle_state="planning", attempt_count=1)

    with pytest.raises(ValueError, match="context_revision"):
        make_record(lifecycle_state="prepared")

    with pytest.raises(ValueError, match="committed_at and resulting_revision"):
        make_record(lifecycle_state="committed")

    with pytest.raises(ValueError, match="narrative"):
        make_record(
            lifecycle_state="completed",
            committed_at="2026-11-04T00:00:00Z",
            resulting_revision=2,
            completed_at="2026-11-04T00:01:00Z",
        )


def test_record_rejects_invalid_json_intent_analysis():
    with pytest.raises(ValueError, match="intent_json"):
        make_record(intent_json="{broken")
