import json
import pytest
from repositories.turn_resolution_repository import TurnResolutionRepository
from services.turns.durable_native_turn_service import DurableNativeTurnError
from durable_turn_test_support import service_with_fake_models

def test_native_turn_commits_before_narration_and_completes_durably():
    service, proposal_calls, narrative_calls = _service_with_fake_models()

    result = service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-test-turn-001",
    )

    assert result.narrative == "El personaje observa su entorno."
    assert result.already_processed is False
    assert len(proposal_calls) == 1
    assert len(narrative_calls) == 1
    assert "RESOLUCIÓN Y CONSECUENCIAS YA COMPROMETIDAS" in narrative_calls[0]
    assert '"operations": []' in narrative_calls[0]

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

def test_manual_roll_challenge_is_server_computed_and_hides_internal_decision():
    from types import SimpleNamespace

    from models.character_state import CharacterState
    from models.mechanics import MechanicsDecision, MechanicsDecisionType
    from rules_engine.dnd5e_2014.core.skills import Skill

    service, _, _ = _service_with_fake_models()
    character = CharacterState(
        entity_id=77,
        dexterity=16,
        skill_proficiencies=frozenset({Skill.STEALTH}),
    )
    decision = MechanicsDecision(
        decision=MechanicsDecisionType.SKILL_CHECK,
        skill=Skill.STEALTH,
        dc=15,
        advantage=True,
        reason="The character is moving unseen.",
    )

    pending = service.execution_service.build_manual_roll_request(
        None, decision, SimpleNamespace(active_character=character), 12
    )
    result = service._manual_roll_result(
        SimpleNamespace(id=42, player_input="Me oculto."), pending
    )

    assert pending["modifier"] == 5
    assert pending["dc"] == 15
    assert pending["count"] == 2
    assert pending["context_revision"] == 12
    assert pending["challenge_id"]
    assert result.pending_roll_id == f"42:{pending['challenge_id']}"
    assert "decision" not in result.pending_roll
    assert "challenge_id" not in result.pending_roll

def test_manual_roll_submission_rejects_malformed_challenge_and_die_results():
    from services.turns.durable_native_turn_service import DurableNativeTurnError

    service, _, _ = _service_with_fake_models()

    with pytest.raises(DurableNativeTurnError):
        service.submit_manual_roll("not-a-challenge", (12,))
    with pytest.raises(DurableNativeTurnError):
        service.submit_manual_roll("42:challenge", (0,))
    with pytest.raises(DurableNativeTurnError):
        service.submit_manual_roll("42:challenge", (12, 13, 14))

def test_native_clarification_survives_and_resumes_durably(monkeypatch):
    from services.turns.turn_resolution_service import TurnResolutionPlan

    service, _, narrative_calls = _service_with_fake_models()
    plans = [
        TurnResolutionPlan(
            player_input="Abro la puerta.",
            narrative="¿Qué puerta?",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
            clarification_question="¿Qué puerta quieres abrir?",
        ),
        TurnResolutionPlan(
            player_input="Abro la puerta de roble.",
            narrative="",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
        ),
    ]
    calls = []

    def prepare_turn(context, player_input, **kwargs):
        calls.append(player_input)
        return plans.pop(0)

    monkeypatch.setattr(service.resolver, "prepare_turn", prepare_turn)

    pending = service.play_turn(
        "Abro una puerta.",
        idempotency_key="native-clarification-001",
    )
    assert pending.pending_clarification_id
    assert pending.narrative == "¿Qué puerta quieres abrir?"
    replayed_pending = service.play_turn(
        "Abro una puerta.",
        idempotency_key="native-clarification-001",
    )
    assert (
        replayed_pending.pending_clarification_id
        == pending.pending_clarification_id
    )

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-clarification-001",
        scope=service.scope,
    )
    assert record.lifecycle_state == "awaiting_input"
    assert record.context_revision is not None
    assert json.loads(record.adjudication_json)["clarification"]["question"] == (
        "¿Qué puerta quieres abrir?"
    )

    completed = service.submit_clarification(
        pending.pending_clarification_id,
        "La puerta de roble.",
    )

    assert completed.narrative == "El personaje observa su entorno."
    assert calls == [
        "Abro una puerta.",
        (
            "Abro una puerta."
            + "\n\nAclaración del DM: ¿Qué puerta quieres abrir?"
            + "\nRespuesta del jugador: La puerta de roble."
        ),
    ]
    repeated = service.submit_clarification(
        pending.pending_clarification_id,
        "La puerta de roble.",
    )
    assert repeated.narrative == completed.narrative
    assert repeated.already_processed is True
    assert len(narrative_calls) == 1

    saved = TurnResolutionRepository().get(record.id, scope=service.scope)
    assert saved.lifecycle_state == "completed"
    assert saved.player_input == "Abro una puerta."
    assert "La puerta de roble." in service._resolved_player_input(saved)
    assert json.loads(saved.adjudication_json)["clarification_history"] == [
        {
            "question": "¿Qué puerta quieres abrir?",
            "answer": "La puerta de roble.",
        }
    ]

    with pytest.raises(DurableNativeTurnError):
        service.submit_clarification(
            pending.pending_clarification_id,
            "Respuesta duplicada.",
        )

def test_native_clarification_rotates_challenge_when_more_detail_is_needed(monkeypatch):
    from services.turns.turn_resolution_service import TurnResolutionPlan

    service, _, _ = _service_with_fake_models()
    questions = iter([
        "¿Qué puerta?",
        "¿La abres con cuidado o con fuerza?",
    ])
    calls = []

    def prepare_turn(context, player_input, **kwargs):
        calls.append(player_input)
        question = next(questions, None)
        return TurnResolutionPlan(
            player_input=player_input,
            narrative=question or "",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
            clarification_question=question,
        )

    monkeypatch.setattr(service.resolver, "prepare_turn", prepare_turn)
    first = service.play_turn(
        "Abro una puerta.",
        idempotency_key="native-clarification-002",
    )
    second = service.submit_clarification(
        first.pending_clarification_id,
        "La de roble.",
    )

    assert second.pending_clarification_id
    assert second.pending_clarification_id != first.pending_clarification_id
    assert second.narrative == "¿La abres con cuidado o con fuerza?"

    with pytest.raises(DurableNativeTurnError):
        service.submit_clarification(
            first.pending_clarification_id,
            "Respuesta antigua.",
        )

def test_unexpected_native_turn_failure_logs_original_traceback(caplog):
    service, _, _ = _service_with_fake_models()

    def fail_during_preparation(*args, **kwargs):
        raise RuntimeError("simulated provider failure")

    service.resolver.prepare_turn = fail_during_preparation

    with (
        caplog.at_level(
            "ERROR",
            logger="services.durable_native_turn_service",
        ),
        pytest.raises(
            DurableNativeTurnError,
            match="native turn execution failed",
        ),
    ):
        service.play_turn(
            "Investigo el campanario.",
            idempotency_key="native-test-unexpected-error-001",
        )

    entries = [
        record
        for record in caplog.records
        if "Unexpected native turn execution failure" in record.getMessage()
    ]
    assert len(entries) == 1
    assert entries[0].exc_info is not None
    assert isinstance(entries[0].exc_info[1], RuntimeError)
    assert str(entries[0].exc_info[1]) == "simulated provider failure"
    assert "campaign_id=1" in entries[0].getMessage()
    assert "adapter_namespace=native" in entries[0].getMessage()
    assert "lifecycle_state=planning" in entries[0].getMessage()

def test_unexpected_planning_failure_releases_lease_and_recovers_after_runtime_restart():
    service, _, _ = _service_with_fake_models()

    def fail_during_preparation(*args, **kwargs):
        raise RuntimeError("temporary extraction provider outage")

    service.resolver.prepare_turn = fail_during_preparation

    with pytest.raises(
        DurableNativeTurnError,
        match="native turn execution failed",
    ):
        service.play_turn(
            "Investigo el campanario.",
            idempotency_key="native-planning-restart-recovery",
        )

    failed_attempt = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-planning-restart-recovery",
        scope=service.scope,
    )
    assert failed_attempt.lifecycle_state == "accepted"
    assert failed_attempt.attempt_count == 1
    assert failed_attempt.lease_token is None
    assert failed_attempt.lease_expires_at is None
    assert failed_attempt.last_error_code == "planning_failed"

    # A fresh runtime simulates a process restart: recovery must rely on the
    # persisted resolution, not the failed service instance or its lock.
    restarted_service = CampaignRuntimeFactory().get_runtime(
        service.scope.campaign_id
    ).durable_native_turn_service
    restarted_service.resolver.mechanics_adjudicator = None
    proposal_calls = []
    restarted_service.resolver.extractor.provider = lambda prompt: (
        proposal_calls.append(prompt) or '{"operations": []}'
    )
    narrative_calls = []
    restarted_service.resolver.dm_service.provider.generate = lambda prompt: (
        narrative_calls.append(prompt) or "La campana permanece inmóvil."
    )

    recovered = restarted_service.play_turn(
        "Investigo el campanario.",
        idempotency_key="native-planning-restart-recovery",
    )

    assert recovered.narrative == "La campana permanece inmóvil."
    assert len(proposal_calls) == 1
    assert len(narrative_calls) == 1

    completed = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-planning-restart-recovery",
        scope=service.scope,
    )
    assert completed.lifecycle_state == "completed"
    assert completed.attempt_count == 2
    assert completed.lease_token is None
    assert completed.lease_expires_at is None

def test_invalid_llm_proposal_releases_planning_lease_and_same_identity_retries():
    service, _, _ = _service_with_fake_models()
    responses = iter([
        '{"operations": [{"type": "start_interaction"}]}',
        '{"operations": [{"type": "start_interaction"}]}',
        '{"operations": []}',
    ])
    proposal_calls = []

    def proposal_provider(prompt):
        proposal_calls.append(prompt)
        return next(responses)

    service.resolver.extractor.provider = proposal_provider

    with pytest.raises(DurableNativeTurnError):
        service.play_turn(
            "Hablo con Mara.",
            idempotency_key="native-invalid-proposal-retry",
        )

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-invalid-proposal-retry",
        scope=service.scope,
    )
    assert record.lifecycle_state == "accepted"
    assert record.lease_token is None
    assert record.lease_expires_at is None
    assert record.last_error_code == "invalid_llm_proposal"
    assert len(proposal_calls) == 2

    recovered = service.play_turn(
        "Hablo con Mara.",
        idempotency_key="native-invalid-proposal-retry",
    )

    assert recovered.narrative == "El personaje observa su entorno."
    assert len(proposal_calls) == 3

def test_context_failure_after_commit_is_recoverable_without_reapplying_operations(monkeypatch):
    service, proposal_calls, _ = _service_with_fake_models()
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

    original_context_and_history = service._context_and_history
    context_calls = {"count": 0}

    def fail_once_after_commit(conn):
        context_calls["count"] += 1
        # Calls 1 and 2 build/validate the plan; call 3 is the context
        # reload for narration, after the consequences have been committed.
        if context_calls["count"] == 3:
            raise RuntimeError("temporary context read failure")
        return original_context_and_history(conn)

    monkeypatch.setattr(service, "_context_and_history", fail_once_after_commit)

    with pytest.raises(DurableNativeTurnError):
        service.play_turn(
            "Miro alrededor.",
            idempotency_key="native-context-failure-after-commit",
        )

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-context-failure-after-commit",
        scope=service.scope,
    )
    assert record.lifecycle_state == "narration_pending"
    assert record.resulting_revision is not None
    committed_world = service.world_service.repository.load_world(campaign_id=1)
    assert any(entity.name == "Aldric" for entity in committed_world.entities.values())
    assert len(proposal_calls) == 1

    recovered = service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-context-failure-after-commit",
    )

    assert recovered.narrative == "El personaje observa su entorno."
    assert len(proposal_calls) == 1
    recovered_world = service.world_service.repository.load_world(campaign_id=1)
    assert any(entity.name == "Aldric" for entity in recovered_world.entities.values())

def test_native_idempotency_key_rejects_different_player_input():
    service, proposal_calls, narrative_calls = _service_with_fake_models()
    service.play_turn(
        "Miro alrededor.",
        idempotency_key="native-idempotency-input-conflict",
    )

    with pytest.raises(
        DurableNativeTurnError,
        match="idempotency key was already used for a different request",
    ):
        service.play_turn(
            "Abro la puerta.",
            idempotency_key="native-idempotency-input-conflict",
        )

    assert len(proposal_calls) == 1
    assert len(narrative_calls) == 1
