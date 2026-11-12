from database import get_conn
from models.operation_result import OperationResult, OperationStatus
from operations.world_operations import CreateEntityOperation


def test_failed_regeneration_keeps_previous_active_turn_and_records_failed_attempt(
    client,
    monkeypatch,
):
    service = __import__("app").runtime_factory.get_runtime(1).silly_tavern_integration_service

    external_turn_id = "failed-regeneration-history"

    failing_operation = CreateEntityOperation(
        name="Entidad que no debe persistir",
        entity_type="npc",
    )

    monkeypatch.setattr(
        service.legacy_turn_service.extractor,
        "extract",
        lambda narrative, context: (
            [] if narrative == "V1" else [failing_operation]
        ),
    )

    # V1 establishes the active version and its snapshot.
    response_v1 = client.post(
        "/integration/turn",
        json={
            "player_input": "Primera versión.",
            "narrative": "V1",
            "external_turn_id": external_turn_id,
            "turn_version": 1,
        },
    )

    assert response_v1.status_code == 200

    def fail_apply(
        world_operations,
        character_operations,
        *,
        campaign_id,
        conn=None,
        ordered_operations=None,
    ):
        return (
            OperationResult(
                status=OperationStatus.INVALID,
                message="Forced regeneration failure.",
                operation=failing_operation,
            ),
        )

    monkeypatch.setattr(
        service.legacy_turn_service.world_service,
        "apply_turn_operations",
        fail_apply,
    )

    # V2 is a regeneration. Its failure must not leave two active
    # versions or destroy the previously active version.
    response_v2 = client.post(
        "/integration/turn",
        json={
            "player_input": "Segunda versión.",
            "narrative": "V2",
            "external_turn_id": external_turn_id,
            "turn_version": 2,
        },
    )

    assert response_v2.status_code == 200

    data_v2 = response_v2.json()

    assert data_v2["turn_version"] == 2
    assert data_v2["operation_count"] == 1
    assert data_v2["successful_operation_count"] == 0
    assert data_v2["failed_operation_count"] == 1
    assert data_v2["all_operations_succeeded"] is False
    assert data_v2["world_changed"] is False

    with get_conn() as conn:
        turns = conn.execute(
            """
            SELECT
                version,
                status,
                operation_count,
                all_operations_succeeded
            FROM turns
            WHERE external_turn_id = ?
            ORDER BY version
            """,
            (external_turn_id,),
        ).fetchall()

        active_turns = conn.execute(
            """
            SELECT version
            FROM turns
            WHERE external_turn_id = ?
              AND status = 'active'
            """,
            (external_turn_id,),
        ).fetchall()

    assert len(turns) == 2

    assert turns[0]["version"] == 1
    assert turns[0]["status"] == "active"
    assert turns[0]["all_operations_succeeded"] == 1

    assert turns[1]["version"] == 2
    assert turns[1]["status"] == "failed"
    assert turns[1]["all_operations_succeeded"] == 0

    assert len(active_turns) == 1
    assert active_turns[0]["version"] == 1
