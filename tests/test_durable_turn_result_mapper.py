from types import SimpleNamespace

from models.operation_result import OperationStatus
from services.durable_turn_result_mapper import DurableTurnResultMapper


class EmptyOperationParser:
    def parse(self, payload):
        assert payload == '{"operations":[]}'
        return []


def test_mapper_reconstructs_completed_turn_result_from_persisted_projection():
    record = SimpleNamespace(
        proposal_json='{"operations":[]}',
        operation_results_json='[{"status":"success","message":"Aplicado"}]',
        mechanics_json=None,
    )
    turn = SimpleNamespace(
        player_input="Abro la puerta.",
        narrative="La puerta se abre.",
        operation_count=1,
        successful_operation_count=1,
        failed_operation_count=0,
        all_operations_succeeded=True,
        world_changed=True,
    )

    result = DurableTurnResultMapper(EmptyOperationParser()).from_completed_record(
        record,
        turn,
        already_processed=True,
    )

    assert result.player_input == "Abro la puerta."
    assert result.narrative == "La puerta se abre."
    assert result.operations == ()
    assert result.character_operations == ()
    assert len(result.operation_results) == 1
    assert result.operation_results[0].status is OperationStatus.SUCCESS
    assert result.operation_results[0].message == "Aplicado"
    assert result.operation_results[0].operation is None
    assert result.mechanics_result is None
    assert result.already_processed is True
    assert result.persisted_operation_count == 1
    assert result.persisted_successful_operation_count == 1
    assert result.persisted_failed_operation_count == 0
    assert result.persisted_all_operations_succeeded is True
    assert result.persisted_world_changed is True


def test_mapper_defaults_missing_persisted_operation_results_to_empty():
    record = SimpleNamespace(
        proposal_json=None,
        operation_results_json=None,
        mechanics_json=None,
    )
    turn = SimpleNamespace(
        player_input="Espero.",
        narrative="No ocurre nada.",
        operation_count=0,
        successful_operation_count=0,
        failed_operation_count=0,
        all_operations_succeeded=True,
        world_changed=False,
    )

    result = DurableTurnResultMapper(EmptyOperationParser()).from_completed_record(
        record,
        turn,
        already_processed=False,
    )

    assert result.operation_results == ()
    assert result.already_processed is False
    assert result.persisted_world_changed is False
