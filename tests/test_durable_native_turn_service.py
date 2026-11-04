import json

from repositories.turn_resolution_repository import TurnResolutionRepository
from services.campaign_runtime import CampaignRuntimeFactory


def _service_with_fake_models():
    runtime = CampaignRuntimeFactory().get_runtime(1)
    service = runtime.durable_native_turn_service
    service.resolver.mechanics_adjudicator = None
    proposal_calls = []
    service.resolver.extractor.provider = lambda prompt: (
        proposal_calls.append(prompt) or '{"operations": []}'
    )
    narrative_calls = []
    service.resolver.dm_service.provider.generate = lambda prompt: (
        narrative_calls.append(prompt) or "El personaje observa su entorno."
    )
    return service, proposal_calls, narrative_calls


def test_native_turn_commits_before_narration_and_completes_durably():
    service, proposal_calls, narrative_calls = _service_with_fake_models()

    result = service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-test-turn-001",
    )

    assert result.narrative == "El personaje observa su entorno."
    assert len(proposal_calls) == 1
    assert len(narrative_calls) == 1

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-test-turn-001",
        scope=service.scope,
    )
    assert record.lifecycle_state == "completed"
    assert record.committed_at is not None
    assert record.completed_at is not None
    assert record.context_revision is not None
    assert record.resulting_revision is not None
    assert record.turn_id is not None


def test_native_turn_retry_does_not_reapply_or_replan_completed_resolution():
    service, proposal_calls, narrative_calls = _service_with_fake_models()

    first = service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-test-turn-002",
    )
    second = service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-test-turn-002",
    )

    assert first.narrative == second.narrative
    assert second.already_processed is True
    assert len(proposal_calls) == 1
    assert len(narrative_calls) == 1


def test_narration_failure_leaves_committed_resolution_resumable():
    service, proposal_calls, _ = _service_with_fake_models()
    attempts = {"count": 0}
    proposal_payload = json.dumps({
        "operations": [{
            "type": "create_entity",
            "name": "Aldric",
            "entity_type": "npc",
            "description": "Tabernero.",
            "notes": "",
            "active": True,
        }]
    })
    service.resolver.extractor.provider = lambda prompt: (
        proposal_calls.append(prompt) or proposal_payload
    )

    def fail_once(prompt):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary narration outage")
        return "La narración se ha recuperado."

    service.resolver.dm_service.provider.generate = fail_once

    import pytest
    from services.durable_native_turn_service import DurableNativeTurnError

    with pytest.raises(DurableNativeTurnError):
        service.play_turn(
            "Miro alrededor.",
            idempotency_key="native-test-turn-003",
        )

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-test-turn-003",
        scope=service.scope,
    )
    assert record.lifecycle_state == "narration_pending"
    assert record.resulting_revision is not None
    committed_world = service.world_service.repository.load_world(campaign_id=1)
    assert len(committed_world.entities) == 1

    resumed = service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-test-turn-003",
    )

    assert resumed.narrative == "La narración se ha recuperado."
    assert len(proposal_calls) == 1
    assert attempts["count"] == 2
    recovered_world = service.world_service.repository.load_world(campaign_id=1)
    assert len(recovered_world.entities) == 1
