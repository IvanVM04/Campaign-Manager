"""Durable execution bridge for v3 compound player-action graphs.

The bridge deliberately owns no persistence transaction. Its caller supplies a
lease-fenced checkpoint/progress persister and later hands the aggregate plan to
the existing atomic prepared-commit service.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, replace

from models.mechanics import MechanicsDecision
from models.player_action_checkpoint import (
    ActionExecutionState,
    ActionOutcome,
    PlayerActionCheckpoint,
)
from models.player_turn_interpretation_v3 import GameplayActionCandidate
from models.world_context_projection import WorldContextProjection
from services.turns.player_action_selector import select_next_action
from services.turns.turn_resolution_codec import TurnResolutionCodec
from services.turns.turn_resolution_service import (
    TurnResolutionPlan,
    TurnResolutionService,
)
from services.turns.v3_action_planning_adapter import (
    V3ActionPlanningAdapter,
)
from services.turns.v3_action_preview_service import (
    V3ActionPreviewResult,
    V3ActionPreviewService,
)
from services.turns.v3_action_progress_codec import (
    V3ActionProgressSnapshot,
)
from services.turns.v3_compound_action_orchestrator import (
    CompoundActionExecution,
    CompoundActionRunStatus,
    V3CompoundActionOrchestrator,
)


class V3CompoundRuntimeError(RuntimeError):
    """Fail-closed error from the durable V3 runtime integration."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"v3 compound runtime failed ({code})")


@dataclass(frozen=True, slots=True)
class V3CompoundRuntimeResult:
    """A completed graph or a durable pause awaiting one action clarification."""

    checkpoint: PlayerActionCheckpoint
    progress: V3ActionProgressSnapshot
    plan: TurnResolutionPlan | None
    status: CompoundActionRunStatus = CompoundActionRunStatus.COMPLETED
    candidate: GameplayActionCandidate | None = None
    event_id: str | None = None
    clarification_slots: tuple[str, ...] = ()
    manual_roll_decision: MechanicsDecision | None = None
    manual_roll_execution_key: str | None = None

    @property
    def action_outcomes(self) -> tuple[dict[str, object], ...]:
        """Return bounded backend outcomes for narration after the aggregate commit."""
        nodes = {
            node.candidate.source_event_id: node
            for node in self.checkpoint.nodes
        }
        outcomes: list[dict[str, object]] = []
        for entry in self.progress.entries:
            node = nodes.get(entry.event_id)
            if node is None or node.outcome is None:
                raise V3CompoundRuntimeError("action_outcome_missing")
            try:
                mechanics_result = (
                    json.loads(entry.mechanics_json)
                    if entry.mechanics_json is not None
                    else None
                )
                mechanics_decision = (
                    json.loads(entry.mechanics_decision_json)
                    if entry.mechanics_decision_json is not None
                    else None
                )
            except (TypeError, ValueError):
                raise V3CompoundRuntimeError(
                    "action_mechanics_evidence_invalid"
                ) from None
            outcomes.append({
                "event_id": entry.event_id,
                "action_id": entry.action_id,
                "source_order": entry.source_order,
                "evidence_excerpt": entry.evidence_excerpt,
                "outcome": node.outcome.value,
                "mechanics_result": mechanics_result,
                "mechanics_decision": mechanics_decision,
            })
        return tuple(outcomes)


class V3CompoundActionRuntime:
    """Run ready V3 action nodes and aggregate their staged plans.

    Every checkpoint transition and staged proposal is persisted by the
    caller using the active resolution lease and repository CAS. Action
    proposals are never applied while traversing the graph.
    """

    def __init__(
        self,
        resolver: TurnResolutionService,
        preview_service: V3ActionPreviewService,
        *,
        planning_adapter: V3ActionPlanningAdapter | None = None,
        orchestrator: V3CompoundActionOrchestrator | None = None,
    ) -> None:
        if not isinstance(resolver, TurnResolutionService):
            raise TypeError("resolver must be a TurnResolutionService")
        if not isinstance(preview_service, V3ActionPreviewService):
            raise TypeError("preview_service must be a V3ActionPreviewService")
        self.resolver = resolver
        self.preview_service = preview_service
        self.planning_adapter = planning_adapter or V3ActionPlanningAdapter()
        self.orchestrator = orchestrator or V3CompoundActionOrchestrator()

    @staticmethod
    def _progress_snapshot(
        record,
        checkpoint: PlayerActionCheckpoint,
    ) -> V3ActionProgressSnapshot:
        payload = getattr(record, "proposal_json", None)
        if payload is None:
            return V3ActionProgressSnapshot.empty(
                resolution_id=checkpoint.resolution_id,
                context_revision=checkpoint.context_revision,
                source_sha256=checkpoint.source_sha256,
            )
        try:
            snapshot = V3ActionProgressSnapshot.from_json(payload)
        except (TypeError, ValueError) as exc:
            raise V3CompoundRuntimeError("staged_progress_invalid") from exc
        if (
            snapshot.resolution_id != checkpoint.resolution_id
            or snapshot.context_revision != checkpoint.context_revision
            or snapshot.source_sha256 != checkpoint.source_sha256
        ):
            raise V3CompoundRuntimeError("staged_progress_identity_mismatch")
        return snapshot

    def _virtual_preview(
        self,
        preview: V3ActionPreviewResult,
        progress: V3ActionProgressSnapshot,
        player_input: str,
        current_event_id: str,
    ) -> V3ActionPreviewResult:
        """Project every completed staged predecessor without touching live state."""
        projection = preview.visible_projection
        if not isinstance(projection, WorldContextProjection):
            raise V3CompoundRuntimeError("visible_projection_unavailable")
        staged_operations = []
        for entry in progress.entries:
            if entry.event_id == current_event_id:
                continue
            plan = TurnResolutionCodec.plan_from_v3_action_progress_entry(
                entry,
                original_input=player_input,
                operation_parser=self.resolver.extractor.operation_parser,
            )
            if plan.character_operations:
                raise V3CompoundRuntimeError(
                    "virtual_character_projection_not_supported"
                )
            staged_operations.extend(plan.ordered_operations)
        if not staged_operations:
            return preview

        # WorldService.apply_operations mutates only its own in-memory copy and
        # never opens a repository transaction or saves the campaign.
        sandbox = copy.copy(self.resolver.world_service)
        sandbox.world = copy.deepcopy(projection.world)
        applied = sandbox.apply_operations(tuple(staged_operations))
        if not applied.success:
            raise V3CompoundRuntimeError("virtual_projection_rejected")
        return replace(
            preview,
            visible_projection=replace(projection, world=applied.world),
        )

    def _aggregate_plan(
        self,
        checkpoint: PlayerActionCheckpoint,
        progress: V3ActionProgressSnapshot,
        player_input: str,
    ) -> TurnResolutionPlan:
        resolved_ids = {
            node.candidate.source_event_id
            for node in checkpoint.nodes
            if node.state is ActionExecutionState.RESOLVED
        }
        staged_ids = {entry.event_id for entry in progress.entries}
        if resolved_ids != staged_ids:
            raise V3CompoundRuntimeError("resolved_action_progress_mismatch")

        plans = [
            TurnResolutionCodec.plan_from_v3_action_progress_entry(
                entry,
                original_input=player_input,
                operation_parser=self.resolver.extractor.operation_parser,
            )
            for entry in progress.entries
        ]
        if not plans:
            raise V3CompoundRuntimeError("completed_graph_has_no_action_plans")

        ordered_operations = tuple(
            operation
            for plan in plans
            for operation in plan.ordered_operations
        )
        world_operations = tuple(
            operation
            for plan in plans
            for operation in plan.world_operations
        )
        character_operations = tuple(
            operation
            for plan in plans
            for operation in plan.character_operations
        )
        mechanics_result = next(
            (
                plan.mechanics_result
                for plan in reversed(plans)
                if plan.mechanics_result is not None
            ),
            None,
        )
        mechanics_decision = next(
            (
                plan.mechanics_decision
                for plan in reversed(plans)
                if plan.mechanics_decision is not None
            ),
            None,
        )
        analyses = [
            plan.intent_analysis
            for plan in plans
            if plan.intent_analysis is not None
        ]
        intent_analysis = None
        if analyses:
            steps = tuple(
                replace(step, index=index)
                for index, step in enumerate(
                    step
                    for analysis in analyses
                    for step in analysis.steps
                )
            )
            first = analyses[0]
            intent_analysis = replace(
                first,
                steps=steps,
                active_step_index=(
                    0 if first.active_step_index is not None and steps else None
                ),
            )

        return TurnResolutionPlan(
            player_input=player_input,
            narrative="",
            world_operations=world_operations,
            character_operations=character_operations,
            ordered_operations=ordered_operations,
            mechanics_result=mechanics_result,
            mechanics_decision=mechanics_decision,
            intent_analysis=intent_analysis,
            intent_evidence_text=player_input,
        )

    @staticmethod
    def supports_graph(
        preview: V3ActionPreviewResult,
        *,
        manual_mode: bool,
    ) -> bool:
        """Return whether this graph can start or pause for one supported input."""
        if not isinstance(manual_mode, bool) or not isinstance(
            preview, V3ActionPreviewResult
        ):
            return False
        status = preview.selection.status.value
        if status not in {"ready", "exhausted", "needs_clarification"}:
            return False
        if not preview.checkpoint.nodes:
            return False
        awaiting_nodes = tuple(
            node for node in preview.checkpoint.nodes
            if node.state is ActionExecutionState.AWAITING_INPUT
        )
        if any(node.clarification_slots != ("target",) for node in awaiting_nodes):
            return False
        if status == "needs_clarification":
            return (
                preview.selection.candidate is not None
                and preview.selection.clarification_slots == ("target",)
            )
        if status == "exhausted":
            return any(
                node.state is ActionExecutionState.RESOLVED
                for node in preview.checkpoint.nodes
            )
        return True

    def run(
        self,
        record,
        preview: V3ActionPreviewResult,
        *,
        context,
        player_input: str,
        recent_turns,
        manual_mode: bool,
        persist_checkpoint,
        clarification_event_id: str | None = None,
        clarification_answer: str | None = None,
        manual_roll_event_id: str | None = None,
        manual_rolls: tuple[int, ...] | None = None,
    ) -> V3CompoundRuntimeResult:
        """Execute ready graph nodes, pausing durably for target clarifications.

        Manual rolls are validated against the staged decision and resolve the
        same IN_PROGRESS node; the original interpretation and mechanics decision
        are restored from progress rather than requested from a provider.
        """
        if not isinstance(preview, V3ActionPreviewResult):
            raise TypeError("preview must be a V3ActionPreviewResult")
        if not callable(persist_checkpoint):
            raise TypeError("persist_checkpoint must be callable")
        if not isinstance(manual_mode, bool):
            raise TypeError("manual_mode must be a boolean")
        if preview.selection.status.value not in {
            "ready", "exhausted", "needs_clarification"
        }:
            raise V3CompoundRuntimeError("initial_graph_not_ready")
        if (
            (clarification_event_id is None) != (clarification_answer is None)
        ):
            raise V3CompoundRuntimeError("clarification_response_incomplete")
        if (manual_roll_event_id is None) != (manual_rolls is None):
            raise V3CompoundRuntimeError("manual_roll_response_incomplete")
        if manual_roll_event_id is not None and not any(
            node.candidate.source_event_id == manual_roll_event_id
            and node.state is ActionExecutionState.IN_PROGRESS
            for node in preview.checkpoint.nodes
        ):
            raise V3CompoundRuntimeError("manual_roll_action_not_pending")
        if clarification_event_id is not None and not any(
            node.candidate.source_event_id == clarification_event_id
            and node.state is ActionExecutionState.AWAITING_INPUT
            and node.clarification_slots == ("target",)
            for node in preview.checkpoint.nodes
        ):
            raise V3CompoundRuntimeError("clarification_action_not_pending")
        if any(
            node.state is ActionExecutionState.AWAITING_INPUT
            and node.clarification_slots != ("target",)
            for node in preview.checkpoint.nodes
        ):
            raise V3CompoundRuntimeError("unsupported_clarification_slots")

        current_preview = preview
        progress = self._progress_snapshot(record, preview.checkpoint)

        def persist(current_checkpoint, updates=None) -> None:
            nonlocal current_preview, progress
            persist_checkpoint(current_checkpoint, updates)
            current_preview = replace(
                current_preview,
                checkpoint=current_checkpoint,
                selection=select_next_action(current_checkpoint),
            )
            if updates and "proposal_json" in updates:
                progress = V3ActionProgressSnapshot.from_json(
                    updates["proposal_json"]
                )

        def execute(candidate, execution_key, resumed, persist_staged_progress):
            nonlocal progress, current_preview
            existing = progress.entry_for_event(candidate.source_event_id)
            if resumed and existing is not None:
                action = self.planning_adapter.restore_staged_action(
                    current_preview,
                    context,
                    player_input,
                    progress_json=progress.to_json(),
                    event_id=candidate.source_event_id,
                    execution_key=execution_key,
                    operation_parser=self.resolver.extractor.operation_parser,
                )
            else:
                action_preview = self._virtual_preview(
                    current_preview,
                    progress,
                    player_input,
                    candidate.source_event_id,
                )
                action = self.planning_adapter.prepare_next_action(
                    self.resolver,
                    action_preview,
                    context,
                    player_input,
                    recent_turns=recent_turns,
                    manual_mode=manual_mode,
                )
            plan = action.plan
            if plan.awaiting_manual_roll:
                if (
                    manual_roll_event_id is not None
                    and manual_roll_event_id == candidate.source_event_id
                    and manual_rolls is not None
                ):
                    manual_preview = self._virtual_preview(
                        current_preview,
                        progress,
                        player_input,
                        candidate.source_event_id,
                    )
                    current_preview = manual_preview
                    action = self.planning_adapter.resolve_manual_roll(
                        self.resolver,
                        action,
                        manual_preview,
                        context,
                        player_input,
                        manual_rolls,
                        recent_turns=recent_turns,
                    )
                    plan = action.plan
                else:
                    updates = (
                        progress.to_repository_progress_updates()
                        if resumed and existing is not None
                        else action.progress_updates(
                            execution_key=execution_key,
                            previous_progress_json=progress.to_json(),
                        )
                    )
                    if not (resumed and existing is not None):
                        persist_staged_progress(updates)
                        progress = V3ActionProgressSnapshot.from_json(
                            updates["proposal_json"]
                        )
                    return CompoundActionExecution(
                        manual_roll_decision=plan.mechanics_decision,
                    )
            elif (
                manual_roll_event_id is not None
                and manual_roll_event_id == candidate.source_event_id
            ):
                raise V3CompoundRuntimeError("action_no_longer_awaits_manual_roll")
            if plan.clarification_question is not None:
                raise V3CompoundRuntimeError("clarification_continuation_not_enabled")
            if plan.mechanics_result is not None:
                outcome = (
                    ActionOutcome.SUCCESS
                    if plan.mechanics_result.check.success
                    else ActionOutcome.FAILURE
                )
            elif (
                plan.mechanics_decision is not None
                and plan.mechanics_decision.decision.value == "none"
            ):
                # No roll required is a resolved, no-check action. A check
                # result, when present, always takes precedence above.
                outcome = ActionOutcome.SUCCESS
            else:
                raise V3CompoundRuntimeError("action_outcome_not_authoritative")

            updates = (
                action.manual_roll_progress_updates(
                    execution_key=execution_key,
                    previous_progress_json=progress.to_json(),
                )
                if resumed and existing is not None and manual_rolls is not None
                else (
                    progress.to_repository_progress_updates()
                    if resumed and existing is not None
                    else action.progress_updates(
                        execution_key=execution_key,
                        previous_progress_json=progress.to_json(),
                    )
                )
            )
            # Persist the provider-produced plan before the orchestrator records
            # RESOLVED. A crash after this point restores it without another
            # mechanics or extraction provider call.
            persist_staged_progress(updates)
            progress = V3ActionProgressSnapshot.from_json(updates["proposal_json"])
            return CompoundActionExecution(
                outcome=outcome,
                progress_updates=updates,
            )

        if clarification_event_id is not None and clarification_answer is not None:
            current_preview, updated_candidate, clarification_slots = (
                self.preview_service.resolve_target_clarification(
                    current_preview,
                    clarification_event_id,
                    clarification_answer,
                    context=context,
                    player_input=player_input,
                )
            )
            _clarification, run_result = self.orchestrator.resume_after_clarification(
                current_preview.checkpoint,
                clarification_event_id,
                updated_candidate,
                clarification_slots=clarification_slots,
                execute=execute,
                persist_checkpoint=persist,
            )
        else:
            run_result = self.orchestrator.run(
                current_preview.checkpoint,
                execute=execute,
                persist_checkpoint=persist,
            )

        final_checkpoint = run_result.checkpoint
        final_progress = progress
        if run_result.status is CompoundActionRunStatus.NEEDS_CLARIFICATION:
            return V3CompoundRuntimeResult(
                checkpoint=final_checkpoint,
                progress=final_progress,
                plan=None,
                status=run_result.status,
                candidate=run_result.candidate,
                event_id=run_result.event_id,
                clarification_slots=run_result.clarification_slots,
            )
        if run_result.status is CompoundActionRunStatus.NEEDS_MANUAL_ROLL:
            return V3CompoundRuntimeResult(
                checkpoint=final_checkpoint,
                progress=final_progress,
                plan=None,
                status=run_result.status,
                candidate=run_result.candidate,
                event_id=run_result.event_id,
                manual_roll_decision=run_result.manual_roll_decision,
                manual_roll_execution_key=run_result.execution_key,
            )
        if run_result.status is not CompoundActionRunStatus.COMPLETED:
            code = (
                "action_execution_failed"
                if run_result.status is CompoundActionRunStatus.EXECUTION_FAILED
                else f"graph_{run_result.status.value}"
            )
            raise V3CompoundRuntimeError(code)

        aggregate = self._aggregate_plan(
            final_checkpoint,
            final_progress,
            player_input,
        )
        return V3CompoundRuntimeResult(
            checkpoint=final_checkpoint,
            progress=final_progress,
            plan=aggregate,
            status=run_result.status,
        )
