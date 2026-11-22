from __future__ import annotations

from dataclasses import replace

import pytest

from models.player_action_checkpoint import (
    ActionCheckpointNode,
    ActionExecutionState,
    ActionOutcome,
    PlayerActionCheckpoint,
)
from models.player_turn_interpretation_v3 import (
    GameplayActionCandidate,
    GameplayActionEligibility,
    GameplayActionReason,
    GameplayProcessingState,
    GameplayResolvedReference,
    GameplayResolvedReferenceKind,
    GameplayUnlockCondition,
    GameplayWorkflow,
)
from models.semantic_frames import SemanticMention
from services.turns.player_action_selector import (
    ActionSelectorError,
    resume_after_clarification,
)
from services.turns.v3_compound_action_orchestrator import (
    CompoundActionExecution,
    CompoundActionRunStatus,
    V3CompoundActionOrchestrator,
)


def _candidate(
    event_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    blocked: bool = False,
    awaiting_input: bool = False,
) -> GameplayActionCandidate:
    if awaiting_input:
        eligibility = GameplayActionEligibility.REQUIRES_CLARIFICATION
        reason = GameplayActionReason.CLARIFICATION_REQUIRED
        workflow = GameplayWorkflow.CLARIFICATION
        unlock = GameplayUnlockCondition.NONE
        processing = GameplayProcessingState.AWAITING_INPUT
    elif blocked:
        eligibility = GameplayActionEligibility.BLOCKED_BY_DEPENDENCY
        reason = GameplayActionReason.DEPENDENCY_PENDING
        workflow = GameplayWorkflow.MECHANICS
        unlock = GameplayUnlockCondition.DEPENDENCY_SUCCESS
        processing = GameplayProcessingState.PENDING
    else:
        eligibility = GameplayActionEligibility.ELIGIBLE
        reason = GameplayActionReason.ELIGIBLE
        workflow = GameplayWorkflow.MECHANICS
        unlock = GameplayUnlockCondition.NONE
        processing = GameplayProcessingState.PENDING
    return GameplayActionCandidate(
        local_id=f"action_{event_id.removeprefix('event_')}",
        source_event_id=event_id,
        actor=SemanticMention("Yo"),
        action_type="interaction",
        eligibility=eligibility,
        reason=reason,
        workflow=workflow,
        unlock_condition=unlock,
        processing_state=processing,
        target_mentions=(SemanticMention("la puerta"),),
        dependency_event_ids=dependencies,
    )


def _checkpoint(*, awaiting_first: bool = False) -> PlayerActionCheckpoint:
    first = _candidate("event_open", awaiting_input=awaiting_first)
    second = _candidate(
        "event_enter",
        dependencies=("event_open",),
        blocked=True,
    )
    independent = _candidate("event_search")
    nodes = (
        ActionCheckpointNode(
            candidate=first,
            source_order=0,
            state=(
                ActionExecutionState.AWAITING_INPUT
                if awaiting_first
                else ActionExecutionState.PENDING
            ),
            execution_key="1" * 64,
            clarification_slots=("target",) if awaiting_first else (),
        ),
        ActionCheckpointNode(
            candidate=second,
            source_order=1,
            state=ActionExecutionState.PENDING,
            execution_key="2" * 64,
        ),
        ActionCheckpointNode(
            candidate=independent,
            source_order=2,
            state=ActionExecutionState.PENDING,
            execution_key="3" * 64,
        ),
    )
    return PlayerActionCheckpoint(
        resolution_id=17,
        context_revision=4,
        source_sha256="a" * 64,
        interpretation_sha256="b" * 64,
        nodes=nodes,
    )


def _node(checkpoint: PlayerActionCheckpoint, event_id: str) -> ActionCheckpointNode:
    return next(
        item for item in checkpoint.nodes
        if item.candidate.source_event_id == event_id
    )


def test_orchestrator_runs_only_one_action_at_a_time_and_persists_each_transition():
    checkpoint = _checkpoint()
    persisted = []
    executed = []

    def persist(value):
        persisted.append(value)

    def execute(candidate, execution_key, resumed):
        # IN_PROGRESS must already be durable before mechanics is invoked.
        saved = _node(persisted[-1], candidate.source_event_id)
        assert saved.state is ActionExecutionState.IN_PROGRESS
        executed.append((candidate.source_event_id, execution_key, resumed))
        return CompoundActionExecution(ActionOutcome.SUCCESS)

    result = V3CompoundActionOrchestrator().run(
        checkpoint,
        execute=execute,
        persist_checkpoint=persist,
    )

    assert result.status is CompoundActionRunStatus.COMPLETED
    assert [item[0] for item in executed] == [
        "event_open",
        "event_enter",
        "event_search",
    ]
    assert [item.state for item in result.checkpoint.nodes] == [
        ActionExecutionState.RESOLVED,
        ActionExecutionState.RESOLVED,
        ActionExecutionState.RESOLVED,
    ]
    assert all(item.outcome is ActionOutcome.SUCCESS for item in result.checkpoint.nodes)
    assert len(persisted) == 6  # start + resolve for each of three actions


def test_infrastructure_failure_is_not_a_gameplay_outcome_and_retry_reuses_key():
    orchestrator = V3CompoundActionOrchestrator()
    first_run_persisted = []

    def fail(_candidate, _key, _resumed):
        raise TimeoutError("provider timed out")

    failed = orchestrator.run(
        _checkpoint(),
        execute=fail,
        persist_checkpoint=first_run_persisted.append,
    )

    node = _node(failed.checkpoint, "event_open")
    assert failed.status is CompoundActionRunStatus.EXECUTION_FAILED
    assert node.state is ActionExecutionState.EXECUTION_FAILED
    assert node.outcome is None
    assert node.attempt_count == 1
    first_key = node.execution_key

    seen = []

    def retry(candidate, key, resumed):
        seen.append((candidate.source_event_id, key, resumed))
        return CompoundActionExecution(ActionOutcome.SUCCESS)

    completed = orchestrator.run(
        failed.checkpoint,
        execute=retry,
        persist_checkpoint=lambda _value: None,
    )

    assert seen[0] == ("event_open", first_key, True)
    assert _node(completed.checkpoint, "event_open").attempt_count == 2
    assert completed.status is CompoundActionRunStatus.COMPLETED


def test_gameplay_failure_skips_only_conditional_branch_and_runs_independent_action():
    executed = []

    def execute(candidate, _key, _resumed):
        executed.append(candidate.source_event_id)
        if candidate.source_event_id == "event_open":
            return CompoundActionExecution(ActionOutcome.FAILURE)
        return ActionOutcome.SUCCESS

    result = V3CompoundActionOrchestrator().run(
        _checkpoint(),
        execute=execute,
        persist_checkpoint=lambda _value: None,
    )

    assert result.status is CompoundActionRunStatus.COMPLETED
    assert executed == ["event_open", "event_search"]
    assert _node(result.checkpoint, "event_enter").state is ActionExecutionState.SKIPPED
    assert _node(result.checkpoint, "event_search").outcome is ActionOutcome.SUCCESS


def test_orchestrator_pauses_for_clarification_then_resumes_same_graph():
    orchestrator = V3CompoundActionOrchestrator()
    initial = _checkpoint(awaiting_first=True)

    paused = orchestrator.run(
        initial,
        execute=lambda *_args: pytest.fail("must not execute before clarification"),
        persist_checkpoint=lambda _value: None,
    )
    assert paused.status is CompoundActionRunStatus.NEEDS_CLARIFICATION
    assert paused.event_id == "event_open"
    assert paused.clarification_slots == ("target",)

    old = _node(paused.checkpoint, "event_open").candidate
    reference = GameplayResolvedReference(
        mention=SemanticMention("la puerta"),
        category=GameplayResolvedReferenceKind.ENTITY,
        referent_id=91,
        name="Puerta de roble",
    )
    corrected = replace(
        old,
        eligibility=GameplayActionEligibility.ELIGIBLE,
        reason=GameplayActionReason.ELIGIBLE,
        workflow=GameplayWorkflow.MECHANICS,
        processing_state=GameplayProcessingState.PENDING,
        resolved_references=(reference,),
    )
    persisted = []
    result = orchestrator.resume_after_clarification(
        paused.checkpoint,
        "event_open",
        corrected,
        execute=lambda *_args: CompoundActionExecution(ActionOutcome.SUCCESS),
        persist_checkpoint=persisted.append,
    )

    clarification, resumed = result
    assert clarification.affected_descendant_event_ids == ("event_enter",)
    assert resumed.affected_descendant_event_ids == ("event_enter",)
    assert _node(resumed.checkpoint, "event_open").state is ActionExecutionState.RESOLVED
    assert _node(resumed.checkpoint, "event_enter").state is ActionExecutionState.RESOLVED
    assert _node(resumed.checkpoint, "event_search").state is ActionExecutionState.RESOLVED
    assert len(persisted) >= 4


def test_failed_start_checkpoint_persistence_prevents_action_execution():
    executed = []

    def persist(_checkpoint):
        raise RuntimeError("CAS rejected")

    with pytest.raises(RuntimeError, match="CAS rejected"):
        V3CompoundActionOrchestrator().run(
            _checkpoint(),
            execute=lambda *args: executed.append(args) or CompoundActionExecution(ActionOutcome.SUCCESS),
            persist_checkpoint=persist,
        )

    assert executed == []


@pytest.mark.parametrize(
    ("checkpoint", "execute", "persist", "error", "message"),
    [
        (None, lambda *_args: CompoundActionExecution(ActionOutcome.SUCCESS), lambda _value: None, TypeError, "checkpoint"),
        (_checkpoint(), None, lambda _value: None, TypeError, "execute"),
        (_checkpoint(), lambda *_args: ActionOutcome.SUCCESS, None, TypeError, "persist_checkpoint"),
    ],
)
def test_orchestrator_rejects_invalid_public_arguments(
    checkpoint, execute, persist, error, message
):
    with pytest.raises(error, match=message):
        V3CompoundActionOrchestrator().run(
            checkpoint,
            execute=execute,
            persist_checkpoint=persist,
        )


def test_orchestrator_reuses_in_progress_execution_key_after_result_persistence_crash():
    orchestrator = V3CompoundActionOrchestrator()
    durable = []

    def persist_first_attempt(value):
        durable.append(value)
        node = _node(value, "event_open")
        if node.state is ActionExecutionState.RESOLVED:
            raise RuntimeError("database unavailable after mechanics")

    seen = []

    def execute(candidate, key, resumed):
        seen.append((candidate.source_event_id, key, resumed))
        return ActionOutcome.SUCCESS

    with pytest.raises(RuntimeError, match="database unavailable"):
        orchestrator.run(
            _checkpoint(),
            execute=execute,
            persist_checkpoint=persist_first_attempt,
        )

    # The last durable checkpoint is IN_PROGRESS: execution may have happened,
    # but its result was not committed. Recovery must use that same key.
    in_progress = durable[-2]
    assert _node(in_progress, "event_open").state is ActionExecutionState.IN_PROGRESS
    stable_key = _node(in_progress, "event_open").execution_key

    replayed = []

    def replay(candidate, key, resumed):
        replayed.append((candidate.source_event_id, key, resumed))
        return ActionOutcome.SUCCESS

    result = orchestrator.run(
        in_progress,
        execute=replay,
        persist_checkpoint=lambda _value: None,
    )

    assert result.status is CompoundActionRunStatus.COMPLETED
    assert replayed[0] == ("event_open", stable_key, True)
    assert seen[0] == ("event_open", stable_key, False)


def test_orchestrator_treats_invalid_executor_result_as_technical_failure():
    result = V3CompoundActionOrchestrator().run(
        _checkpoint(),
        execute=lambda *_args: "success",
        persist_checkpoint=lambda _value: None,
    )

    node = _node(result.checkpoint, "event_open")
    assert result.status is CompoundActionRunStatus.EXECUTION_FAILED
    assert result.technical_error_type == "TypeError"
    assert node.state is ActionExecutionState.EXECUTION_FAILED
    assert node.outcome is None


def test_orchestrator_does_not_execute_when_failure_checkpoint_cannot_be_saved():
    persisted = []

    def persist(value):
        persisted.append(value)
        if _node(value, "event_open").state is ActionExecutionState.EXECUTION_FAILED:
            raise RuntimeError("failure checkpoint CAS rejected")

    with pytest.raises(RuntimeError, match="failure checkpoint CAS rejected"):
        V3CompoundActionOrchestrator().run(
            _checkpoint(),
            execute=lambda *_args: (_ for _ in ()).throw(TimeoutError("provider")),
            persist_checkpoint=persist,
        )

    assert _node(persisted[0], "event_open").state is ActionExecutionState.IN_PROGRESS
    assert _node(persisted[-1], "event_open").state is ActionExecutionState.EXECUTION_FAILED


def test_orchestrator_persists_dependency_skip_transition_before_finishing():
    persisted = []
    outcomes = iter((
        CompoundActionExecution(ActionOutcome.FAILURE),
        CompoundActionExecution(ActionOutcome.SUCCESS),
    ))

    result = V3CompoundActionOrchestrator().run(
        _checkpoint(),
        execute=lambda *_args: next(outcomes),
        persist_checkpoint=persisted.append,
    )

    skipped_snapshots = [
        checkpoint
        for checkpoint in persisted
        if _node(checkpoint, "event_enter").state is ActionExecutionState.SKIPPED
    ]
    assert skipped_snapshots
    assert result.status is CompoundActionRunStatus.COMPLETED
    assert _node(result.checkpoint, "event_enter").state is ActionExecutionState.SKIPPED


def test_clarification_resume_can_remain_paused_when_backend_still_cannot_resolve_slot():
    orchestrator = V3CompoundActionOrchestrator()
    paused = orchestrator.run(
        _checkpoint(awaiting_first=True),
        execute=lambda *_args: pytest.fail("must stay paused"),
        persist_checkpoint=lambda _value: None,
    )
    candidate = _node(paused.checkpoint, "event_open").candidate
    still_ambiguous = replace(
        candidate,
        reason=GameplayActionReason.AMBIGUOUS_REFERENCE,
    )

    clarification, resumed = orchestrator.resume_after_clarification(
        paused.checkpoint,
        "event_open",
        still_ambiguous,
        clarification_slots=("target",),
        execute=lambda *_args: pytest.fail("must remain paused"),
        persist_checkpoint=lambda _value: None,
    )

    assert clarification.checkpoint.nodes[0].state is ActionExecutionState.AWAITING_INPUT
    assert resumed.status is CompoundActionRunStatus.NEEDS_CLARIFICATION
    assert resumed.clarification_slots == ("target",)
    assert resumed.attempts == ()


def test_clarification_resume_rejects_wrong_event_and_non_candidate():
    checkpoint = _checkpoint(awaiting_first=True)
    with pytest.raises(ActionSelectorError):
        V3CompoundActionOrchestrator().resume_after_clarification(
            checkpoint,
            "event_missing",
            _node(checkpoint, "event_open").candidate,
            execute=lambda *_args: ActionOutcome.SUCCESS,
            persist_checkpoint=lambda _value: None,
        )
    with pytest.raises(TypeError, match="updated_candidate"):
        resume_after_clarification(
            checkpoint,
            "event_open",
            "not a candidate",
        )


def test_staged_action_json_is_forwarded_with_the_resolved_checkpoint_cas():
    checkpoint = replace(_checkpoint(), nodes=(_checkpoint().nodes[0],))
    persisted = []
    updates = {
        "proposal_json": '{"operations":[]}',
        "mechanics_json": '{"outcome":"success"}',
    }

    def persist(value, progress_updates=None):
        persisted.append((value, progress_updates))

    result = V3CompoundActionOrchestrator().run(
        checkpoint,
        execute=lambda *_args: CompoundActionExecution(
            ActionOutcome.SUCCESS,
            updates,
        ),
        persist_checkpoint=persist,
    )

    assert result.status is CompoundActionRunStatus.COMPLETED
    assert len(persisted) == 2
    assert persisted[0][1] is None
    assert _node(persisted[1][0], "event_open").state is ActionExecutionState.RESOLVED
    assert persisted[1][1] == updates


def test_compound_action_execution_rejects_invalid_staged_json_contract():
    with pytest.raises(TypeError, match="authoritative ActionOutcome"):
        CompoundActionExecution("success")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="progress_updates must be a mapping"):
        CompoundActionExecution(
            ActionOutcome.SUCCESS,
            "not a mapping",  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="protected field"):
        CompoundActionExecution(
            ActionOutcome.SUCCESS,
            {"last_error_code": '{"reason":"bad"}'},
        )

    with pytest.raises(ValueError, match="valid JSON"):
        CompoundActionExecution(
            ActionOutcome.SUCCESS,
            {"proposal_json": "not json"},
        )

    with pytest.raises(ValueError, match="byte budget"):
        CompoundActionExecution(
            ActionOutcome.SUCCESS,
            {"proposal_json": '"' + ("x" * 131_073) + '"'},
        )
