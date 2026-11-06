import json
from types import SimpleNamespace

from services.turns import DurableTurnPreparationMapper


def test_mapper_builds_committed_resolution_payload():
    record = SimpleNamespace(
        id=17,
        lifecycle_state="narration_pending",
        context_revision=4,
        resulting_revision=5,
        proposal_json='{"operations":[{"type":"create_entity"}]}',
        operation_results_json='[{"status":"success"}]',
        mechanics_json='{"total":12}',
        adjudication_json="{}",
        player_input="Abro la puerta.",
    )

    payload = DurableTurnPreparationMapper.committed_resolution_json(record)

    assert json.loads(payload) == {
        "resolution_id": 17,
        "lifecycle_state": "narration_pending",
        "context_revision": 4,
        "resulting_revision": 5,
        "operations": [{"type": "create_entity"}],
        "operation_results": [{"status": "success"}],
        "mechanics": {"total": 12},
    }


def test_mapper_projects_pending_clarification_and_manual_roll():
    record = SimpleNamespace(
        id=23,
        lifecycle_state="awaiting_input",
        context_revision=7,
        resulting_revision=None,
        proposal_json='{"operations":[]}',
        operation_results_json="[]",
        mechanics_json=None,
        adjudication_json=json.dumps({
            "clarification": {
                "challenge_id": "clarify-1",
                "question": "¿Qué puerta abres?",
            },
            "manual_roll": {
                "challenge_id": "roll-1",
                "decision": {"internal": True},
                "submitted_rolls": [12],
                "modifier": 3,
                "dc": 14,
            },
        }),
        player_input="Abro una puerta.",
    )

    preparation = DurableTurnPreparationMapper.from_record(record)

    assert preparation.resolution_id == 23
    assert preparation.lifecycle_state == "awaiting_input"
    assert preparation.clarification_question == "¿Qué puerta abres?"
    assert preparation.pending_clarification_id == "23:clarify-1"
    assert preparation.pending_roll_id == "23:roll-1"
    assert preparation.pending_roll == {"modifier": 3, "dc": 14}
    assert "challenge_id" not in preparation.pending_roll
    assert "decision" not in preparation.pending_roll
    assert "submitted_rolls" not in preparation.pending_roll


def test_mapper_preserves_legacy_clarification_question_shape():
    record = SimpleNamespace(
        id=31,
        lifecycle_state="awaiting_input",
        context_revision=1,
        resulting_revision=None,
        proposal_json='{"operations":[]}',
        operation_results_json="[]",
        mechanics_json=None,
        adjudication_json='{"clarification_question":"¿Qué haces?"}',
        player_input="Espero.",
    )

    preparation = DurableTurnPreparationMapper.from_record(record)

    assert preparation.clarification_question == "¿Qué haces?"
    assert preparation.pending_clarification_id is None
    assert preparation.pending_roll_id is None
