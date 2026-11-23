from dataclasses import replace
from types import SimpleNamespace

import pytest

from models.entity import Entity
from models.mechanics import MechanicsDecision, MechanicsDecisionType
from models.player_action_checkpoint import (
    ActionExecutionState,
    ActionOutcome,
    PlayerActionCheckpoint,
)
from models.world_state import WorldState
from services.context import ContextBuilder
from services.llm_world import LLMWorldExtractor, OperationParser
from services.providers import FakeLLMProvider
from services.turns.dm_service import DMService
from services.turns.durable_turn_narration_service import DurableTurnNarrationService
from services.turns.player_action_selector import (
    ActionSelectionStatus,
    mark_action_awaiting_input,
    mark_action_completed,
    mark_action_started,
    select_next_action,
)
from services.turns.turn_resolution_service import (
    TurnResolutionPlan,
    TurnResolutionService,
)
from services.turns.v3_action_progress_codec import V3ActionProgressSnapshot
from services.turns.v3_compound_action_runtime import (
    V3CompoundActionRuntime,
    V3CompoundRuntimeError,
    V3CompoundRuntimeResult,
)
from services.world import WorldService
from tests.test_v3_action_preview_service import (
    _context,
    _preview_service,
    _v3_response,
)


def _runtime_fixture(monkeypatch):
    source = "Yo intento abrir la puerta"
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(
                id=8,
                name="Puerta de hierro",
                entity_type="location",
                aliases=["la puerta"],
            ),
        }
    )
    preview_service, interpreter_provider, _builder = _preview_service(
        world, _v3_response(source)
    )
    context = _context(world)
    preview = preview_service.preview(
        context,
        source,
        resolution_id=501,
        context_revision=33,
    )

    world_service = WorldService(campaign_id=1)
    world_service.world = world
    context_builder = ContextBuilder()
    resolver = TurnResolutionService(
        dm_service=DMService(
            FakeLLMProvider(response="narrative"),
            context_builder,
        ),
        extractor=LLMWorldExtractor(
            lambda _prompt: '{"operations":[]}',
            OperationParser(),
        ),
        world_service=world_service,
        context_builder=context_builder,
    )
    planning_calls = []

    def prepare_turn(turn_context, evidence, **kwargs):
        planning_calls.append(evidence)
        return TurnResolutionPlan(
            player_input=evidence,
            narrative="",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
            mechanics_decision=MechanicsDecision(
                decision=MechanicsDecisionType.NONE
            ),
            intent_analysis=kwargs.get("intent_analysis_override"),
            intent_evidence_text=kwargs.get("intent_evidence_text"),
        )

    monkeypatch.setattr(resolver, "prepare_turn", prepare_turn)
    record = SimpleNamespace(
        proposal_json=None,
        action_checkpoint_json=preview.checkpoint.to_json(),
    )
    persistence_calls = {"count": 0}
    fail_final_once = {"value": False}

    def persist_checkpoint(checkpoint, progress_updates=None):
        persistence_calls["count"] += 1
        # Simulate a process interruption after staged proposal persistence but
        # before the final RESOLVED checkpoint CAS.
        if fail_final_once["value"] and persistence_calls["count"] == 3:
            fail_final_once["value"] = False
            raise RuntimeError("simulated checkpoint CAS interruption")
        previous = PlayerActionCheckpoint.from_json(
            record.action_checkpoint_json
        )
        checkpoint.validate_progress_from(previous)
        record.action_checkpoint_json = checkpoint.to_json()
        if progress_updates is not None:
            record.proposal_json = progress_updates["proposal_json"]
        return record

    return (
        source,
        world,
        context,
        preview_service,
        interpreter_provider,
        preview,
        resolver,
        record,
        planning_calls,
        persistence_calls,
        fail_final_once,
        persist_checkpoint,
    )


def test_durable_v3_runtime_resolves_graph_and_persists_one_staged_plan(monkeypatch):
    (
        source,
        world,
        context,
        preview_service,
        interpreter_provider,
        preview,
        resolver,
        record,
        planning_calls,
        persistence_calls,
        _fail_final_once,
        persist_checkpoint,
    ) = _runtime_fixture(monkeypatch)
    runtime = V3CompoundActionRuntime(resolver, preview_service)

    result = runtime.run(
        record,
        preview,
        context=context,
        player_input=source,
        recent_turns=[],
        manual_mode=False,
        persist_checkpoint=persist_checkpoint,
    )

    assert result.checkpoint.nodes[0].state is ActionExecutionState.RESOLVED
    assert result.checkpoint.nodes[0].outcome.value == "success"
    assert result.plan.ordered_operations == ()
    assert len(result.progress.entries) == 1
    assert result.action_outcomes[0]["outcome"] == "success"
    assert result.action_outcomes[0]["mechanics_decision"]["decision"] == "none"
    assert result.action_outcomes[0]["mechanics_result"] is None
    assert record.proposal_json is not None
    assert planning_calls == ["Yo intento abrir la puerta"]
    assert interpreter_provider.call_count == 1
    assert persistence_calls["count"] == 3
    assert resolver.world_service.world is world


def test_durable_v3_runtime_recovers_staged_plan_without_replanning(monkeypatch):
    (
        source,
        _world,
        context,
        preview_service,
        interpreter_provider,
        preview,
        resolver,
        record,
        planning_calls,
        _persistence_calls,
        fail_final_once,
        persist_checkpoint,
    ) = _runtime_fixture(monkeypatch)
    runtime = V3CompoundActionRuntime(resolver, preview_service)
    fail_final_once["value"] = True

    with pytest.raises(RuntimeError, match="simulated checkpoint CAS interruption"):
        runtime.run(
            record,
            preview,
            context=context,
            player_input=source,
            recent_turns=[],
            manual_mode=False,
            persist_checkpoint=persist_checkpoint,
        )

    interrupted = PlayerActionCheckpoint.from_json(record.action_checkpoint_json)
    assert interrupted.nodes[0].state is ActionExecutionState.IN_PROGRESS
    assert record.proposal_json is not None
    assert len(planning_calls) == 1
    assert interpreter_provider.call_count == 1

    restored = preview_service.restore(
        interrupted,
        context,
        source,
        recent_turns=[],
    )
    resumed = runtime.run(
        record,
        restored,
        context=context,
        player_input=source,
        recent_turns=[],
        manual_mode=False,
        persist_checkpoint=persist_checkpoint,
    )

    assert resumed.checkpoint.nodes[0].state is ActionExecutionState.RESOLVED
    assert len(resumed.progress.entries) == 1
    assert len(planning_calls) == 1
    assert interpreter_provider.call_count == 1



def test_committed_narration_evidence_preserves_only_valid_per_action_outcomes():
    record = SimpleNamespace(
        proposal_json='{"operations":[]}',
        operation_results_json="[]",
        adjudication_json=(
            '{"v3_action_outcomes":['
            '{"event_id":"event_open","action_id":"action_open",'
            '"source_order":0,"evidence_excerpt":"Abro la puerta",'
            '"outcome":"success","mechanics_result":null,'
            '"mechanics_decision":{"decision":"none"}},'
            '{"event_id":"bad","action_id":"bad","source_order":true,'
            '"evidence_excerpt":"invalid","outcome":"success",'
            '"mechanics_result":null,"mechanics_decision":null}'
            ']}'
        ),
        context_revision=4,
        resulting_revision=5,
    )

    evidence = DurableTurnNarrationService._committed_narration_evidence(record)

    assert evidence["action_outcomes"] == [{
        "event_id": "event_open",
        "action_id": "action_open",
        "source_order": 0,
        "evidence_excerpt": "Abro la puerta",
        "outcome": "success",
        "mechanics_result": None,
        "mechanics_decision": {"decision": "none"},
    }]



def test_supports_graph_only_accepts_safe_start_or_real_resumable_progress(monkeypatch):
    (
        _source,
        _world,
        _context_value,
        _preview_service_value,
        _interpreter_provider,
        preview,
        _resolver,
        _record,
        _planning_calls,
        _persistence_calls,
        _fail_final_once,
        _persist_checkpoint,
    ) = _runtime_fixture(monkeypatch)

    assert V3CompoundActionRuntime.supports_graph(
        preview,
        manual_mode=False,
    )
    assert not V3CompoundActionRuntime.supports_graph(
        preview,
        manual_mode=True,
    )

    initially_exhausted = replace(
        preview,
        selection=replace(
            preview.selection,
            status=ActionSelectionStatus.EXHAUSTED,
        ),
    )
    assert not V3CompoundActionRuntime.supports_graph(
        initially_exhausted,
        manual_mode=False,
    )

    event_id = preview.checkpoint.nodes[0].candidate.source_event_id
    awaiting_checkpoint = mark_action_awaiting_input(
        preview.checkpoint,
        event_id,
        ("target",),
    )
    awaiting = replace(
        preview,
        checkpoint=awaiting_checkpoint,
        selection=select_next_action(awaiting_checkpoint),
    )
    assert not V3CompoundActionRuntime.supports_graph(
        awaiting,
        manual_mode=False,
    )

    started, _execution_key, _resumed = mark_action_started(
        preview.checkpoint,
        event_id,
    )
    completed = mark_action_completed(
        started,
        event_id,
        ActionOutcome.SUCCESS,
    )
    exhausted = replace(
        preview,
        checkpoint=completed,
        selection=select_next_action(completed),
    )
    assert exhausted.selection.status is ActionSelectionStatus.EXHAUSTED
    assert V3CompoundActionRuntime.supports_graph(
        exhausted,
        manual_mode=False,
    )



def test_v3_progress_snapshot_empty_invalid_and_identity_mismatch(monkeypatch):
    (
        _source,
        _world,
        _context_value,
        _preview_service_value,
        _interpreter_provider,
        preview,
        _resolver,
        _record,
        _planning_calls,
        _persistence_calls,
        _fail_final_once,
        _persist_checkpoint,
    ) = _runtime_fixture(monkeypatch)

    empty = V3CompoundActionRuntime._progress_snapshot(
        SimpleNamespace(proposal_json=None),
        preview.checkpoint,
    )
    assert empty.entries == ()
    assert empty.resolution_id == preview.checkpoint.resolution_id

    with pytest.raises(V3CompoundRuntimeError) as invalid:
        V3CompoundActionRuntime._progress_snapshot(
            SimpleNamespace(proposal_json="{broken"),
            preview.checkpoint,
        )
    assert invalid.value.code == "staged_progress_invalid"

    foreign = V3ActionProgressSnapshot.empty(
        resolution_id=preview.checkpoint.resolution_id + 1,
        context_revision=preview.checkpoint.context_revision,
        source_sha256=preview.checkpoint.source_sha256,
    )
    with pytest.raises(V3CompoundRuntimeError) as mismatch:
        V3CompoundActionRuntime._progress_snapshot(
            SimpleNamespace(proposal_json=foreign.to_json()),
            preview.checkpoint,
        )
    assert mismatch.value.code == "staged_progress_identity_mismatch"


def test_v3_virtual_projection_requires_projection_and_preserves_empty_projection(monkeypatch):
    (
        source,
        _world,
        _context_value,
        preview_service,
        _interpreter_provider,
        preview,
        resolver,
        _record,
        _planning_calls,
        _persistence_calls,
        _fail_final_once,
        _persist_checkpoint,
    ) = _runtime_fixture(monkeypatch)
    runtime = V3CompoundActionRuntime(resolver, preview_service)
    progress = V3ActionProgressSnapshot.empty(
        resolution_id=preview.checkpoint.resolution_id,
        context_revision=preview.checkpoint.context_revision,
        source_sha256=preview.checkpoint.source_sha256,
    )

    unchanged = runtime._virtual_preview(
        preview,
        progress,
        source,
        preview.checkpoint.nodes[0].candidate.source_event_id,
    )
    assert unchanged is preview

    invalid_projection = replace(preview, visible_projection=None)
    with pytest.raises(V3CompoundRuntimeError) as missing:
        runtime._virtual_preview(
            invalid_projection,
            progress,
            source,
            preview.checkpoint.nodes[0].candidate.source_event_id,
        )
    assert missing.value.code == "visible_projection_unavailable"


def test_v3_aggregate_plan_rejects_missing_and_unstaged_resolved_actions(monkeypatch):
    (
        source,
        _world,
        _context_value,
        preview_service,
        _interpreter_provider,
        preview,
        resolver,
        _record,
        _planning_calls,
        _persistence_calls,
        _fail_final_once,
        _persist_checkpoint,
    ) = _runtime_fixture(monkeypatch)
    runtime = V3CompoundActionRuntime(resolver, preview_service)
    empty_progress = V3ActionProgressSnapshot.empty(
        resolution_id=preview.checkpoint.resolution_id,
        context_revision=preview.checkpoint.context_revision,
        source_sha256=preview.checkpoint.source_sha256,
    )

    with pytest.raises(V3CompoundRuntimeError) as no_plans:
        runtime._aggregate_plan(
            replace(preview.checkpoint, nodes=()),
            empty_progress,
            source,
        )
    assert no_plans.value.code == "completed_graph_has_no_action_plans"

    event_id = preview.checkpoint.nodes[0].candidate.source_event_id
    started, _execution_key, _resumed = mark_action_started(
        preview.checkpoint,
        event_id,
    )
    resolved = mark_action_completed(
        started,
        event_id,
        ActionOutcome.SUCCESS,
    )
    with pytest.raises(V3CompoundRuntimeError) as missing_progress:
        runtime._aggregate_plan(resolved, empty_progress, source)
    assert missing_progress.value.code == "resolved_action_progress_mismatch"


def test_v3_runtime_result_rejects_missing_action_outcome_and_invalid_mechanics_json():
    missing = V3CompoundRuntimeResult(
        checkpoint=SimpleNamespace(nodes=()),
        progress=SimpleNamespace(entries=(
            SimpleNamespace(
                event_id="event_open",
                action_id="action_open",
                source_order=0,
                evidence_excerpt="Abro la puerta",
                mechanics_json=None,
                mechanics_decision_json=None,
            ),
        )),
        plan=SimpleNamespace(),
    )
    with pytest.raises(V3CompoundRuntimeError) as no_outcome:
        _ = missing.action_outcomes
    assert no_outcome.value.code == "action_outcome_missing"

    invalid_mechanics = V3CompoundRuntimeResult(
        checkpoint=SimpleNamespace(nodes=(
            SimpleNamespace(
                candidate=SimpleNamespace(source_event_id="event_open"),
                outcome=ActionOutcome.SUCCESS,
            ),
        )),
        progress=SimpleNamespace(entries=(
            SimpleNamespace(
                event_id="event_open",
                action_id="action_open",
                source_order=0,
                evidence_excerpt="Abro la puerta",
                mechanics_json="{invalid",
                mechanics_decision_json=None,
            ),
        )),
        plan=SimpleNamespace(),
    )
    with pytest.raises(V3CompoundRuntimeError) as malformed:
        _ = invalid_mechanics.action_outcomes
    assert malformed.value.code == "action_mechanics_evidence_invalid"


def test_v3_runtime_supports_graph_rejects_wrong_type_empty_nodes_and_unknown_state(monkeypatch):
    (
        _source,
        _world,
        _context_value,
        _preview_service_value,
        _interpreter_provider,
        preview,
        _resolver,
        _record,
        _planning_calls,
        _persistence_calls,
        _fail_final_once,
        _persist_checkpoint,
    ) = _runtime_fixture(monkeypatch)

    assert not V3CompoundActionRuntime.supports_graph(
        object(),
        manual_mode=False,
    )
    empty = replace(
        preview,
        checkpoint=replace(preview.checkpoint, nodes=()),
    )
    assert not V3CompoundActionRuntime.supports_graph(
        empty,
        manual_mode=False,
    )
    unknown = replace(
        preview,
        selection=replace(
            preview.selection,
            status=ActionSelectionStatus.BLOCKED_BY_DEPENDENCY,
        ),
    )
    assert not V3CompoundActionRuntime.supports_graph(
        unknown,
        manual_mode=False,
    )


def test_v3_runtime_fails_closed_before_persistence_for_invalid_inputs(monkeypatch):
    (
        _source,
        _world,
        context,
        preview_service,
        _interpreter_provider,
        preview,
        resolver,
        record,
        _planning_calls,
        _persistence_calls,
        _fail_final_once,
        persist_checkpoint,
    ) = _runtime_fixture(monkeypatch)
    runtime = V3CompoundActionRuntime(resolver, preview_service)

    with pytest.raises(TypeError, match="preview"):
        runtime.run(
            record,
            object(),
            context=context,
            player_input="Intento abrirla",
            recent_turns=[],
            manual_mode=False,
            persist_checkpoint=persist_checkpoint,
        )
    with pytest.raises(TypeError, match="persist_checkpoint"):
        runtime.run(
            record,
            preview,
            context=context,
            player_input="Intento abrirla",
            recent_turns=[],
            manual_mode=False,
            persist_checkpoint=None,
        )
    with pytest.raises(V3CompoundRuntimeError) as manual:
        runtime.run(
            record,
            preview,
            context=context,
            player_input="Intento abrirla",
            recent_turns=[],
            manual_mode=True,
            persist_checkpoint=persist_checkpoint,
        )
    assert manual.value.code == "manual_roll_continuation_not_enabled"
