import json
from types import SimpleNamespace

from services.turns.durable_turn_narration_service import (
    DurableTurnNarrationService,
)


def test_narration_evidence_contains_only_successful_state_changes():
    record = SimpleNamespace(
        context_revision=12,
        resulting_revision=13,
        proposal_json=json.dumps({
            "operations": [
                {
                    "type": "update_entity",
                    "entity_id": 7,
                    "description": "Aldric has a new scar.",
                },
                {
                    "type": "transfer_item",
                    "instance_id": 3,
                    "new_owner_id": 8,
                    "notes": "Attempted transfer; it was rejected.",
                },
                {
                    "type": "update_entity",
                    "entity_id": 9,
                    "notes": "No new information.",
                },
                {
                    "type": "create_relation",
                    "relation_id": "secret-alliance",
                    "subject_id": 7,
                    "target_id": 9,
                },
            ]
        }),
        operation_results_json=json.dumps([
            {
                "success": True,
                "changed": True,
                "status": "applied",
            },
            {
                "success": False,
                "changed": False,
                "status": "rejected",
                "message": "No debería narrarse como un hecho.",
            },
            {
                "success": True,
                "changed": False,
                "status": "no_change",
            },
        ]),
    )

    evidence = DurableTurnNarrationService._committed_narration_evidence(record)

    assert evidence["context_revision"] == 12
    assert evidence["resulting_revision"] == 13
    assert evidence["proposed_operation_count"] == 4
    assert evidence["committed_operation_count"] == 1
    assert evidence["omitted_non_committed_count"] == 3
    assert evidence["committed_operations"] == [
        {
            "operation": {
                "type": "update_entity",
                "entity_id": 7,
                "description": "Aldric has a new scar.",
            },
            "status": "applied",
            "changed": True,
        }
    ]
    serialized = json.dumps(evidence, ensure_ascii=False)
    assert "No debería narrarse" not in serialized
    assert "secret-alliance" not in serialized
    assert "Attempted transfer" not in serialized


def test_narration_evidence_fails_closed_when_operation_result_is_missing():
    record = SimpleNamespace(
        context_revision=2,
        resulting_revision=3,
        proposal_json=json.dumps({
            "operations": [
                {"type": "update_entity", "entity_id": 1},
                {"type": "create_event", "event_id": "unconfirmed"},
            ]
        }),
        operation_results_json=json.dumps([
            {"success": True, "changed": True, "status": "applied"}
        ]),
    )

    evidence = DurableTurnNarrationService._committed_narration_evidence(record)

    assert evidence["committed_operation_count"] == 1
    assert evidence["omitted_non_committed_count"] == 1
    assert [
        item["operation"]["type"]
        for item in evidence["committed_operations"]
    ] == ["update_entity"]


def test_narration_evidence_omits_malformed_or_non_committed_result_entries():
    record = SimpleNamespace(
        context_revision=0,
        resulting_revision=0,
        proposal_json=json.dumps({
            "operations": [
                {"type": "update_entity", "entity_id": 1},
                "not-an-operation",
                {"type": "update_entity", "entity_id": 2},
            ]
        }),
        operation_results_json=json.dumps([
            {"success": True, "changed": True},
            {"success": True, "changed": True},
            "malformed-result",
        ]),
    )

    evidence = DurableTurnNarrationService._committed_narration_evidence(record)

    assert evidence["committed_operations"] == [
        {
            "operation": {"type": "update_entity", "entity_id": 1},
            "status": "success",
            "changed": True,
        }
    ]
    assert evidence["omitted_non_committed_count"] == 2
