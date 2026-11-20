"""Backend-only selection and resumable execution of v3 action candidates.

This module does not call an LLM, resolve canonical references, adjudicate
mechanics or mutate the world. Callers must provide already-resolved references
from trusted context services and authoritative outcomes from the rules engine.
"""
from __future__ import annotations

import enum
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace

from models.player_action_checkpoint import (
    ActionCheckpointNode,
    ActionExecutionState,
    ActionOutcome,
    FactValidationReceipt,
    FactValidationState,
    PlayerActionCheckpoint,
    processing_state_for,
)
from models.player_turn_interpretation_v3 import (
    ActionPhase,
    DiscourseLinkType,
    EpistemicStatus,
    EventFrame,
    GameplayActionCandidate,
    GameplayActionEligibility,
    GameplayActionReason,
    GameplayProcessingState,
    GameplayResolvedReference,
    GameplayResolvedReferenceKind,
    GameplayUnlockCondition,
    GameplayWorkflow,
    SpeakerRole,
    TurnInterpretationV3,
    UtteranceAct,
    UtteranceForce,
    WorldFactCandidate,
)
from models.semantic_frames import (
    SemanticActionFamily,
    SemanticArgumentRole,
    SemanticMention,
    SemanticPolarity,
)

_TARGET_ROLES = frozenset(
    {
        SemanticArgumentRole.PATIENT,
        SemanticArgumentRole.THEME,
        SemanticArgumentRole.RECIPIENT,
        SemanticArgumentRole.DESTINATION,
        SemanticArgumentRole.LOCATION,
    }
)
_DIALOGUE_FORCES = frozenset(
    {
        UtteranceForce.ASSERTION,
        UtteranceForce.QUESTION,
        UtteranceForce.IN_CHARACTER_DIALOGUE,
        UtteranceForce.WARNING,
        UtteranceForce.REQUEST,
        UtteranceForce.REFUSAL,
        UtteranceForce.CORRECTION,
    }
)
_MECHANICS_FAMILIES = frozenset(
    {
        SemanticActionFamily.MOVEMENT,
        SemanticActionFamily.PERCEPTION,
        SemanticActionFamily.INTERACTION,
        SemanticActionFamily.TRANSFER,
        SemanticActionFamily.ITEM_USE,
        SemanticActionFamily.COMBAT,
    }
)


class ActionSelectorError(ValueError):
    """Fail-closed graph or trusted-reference inconsistency."""


class ActionSelectionStatus(str, enum.Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    BLOCKED_BY_DEPENDENCY = "blocked_by_dependency"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True, slots=True)
class ActionReferenceResolution:
    """Trusted resolution result for one event's literal mentions.

    Canonical IDs must come from the existing visibility-aware resolver. The
    selector never derives an ID from a name or from model output.
    """

    actor_reference: GameplayResolvedReference | None = None
    actor_ambiguous: bool = False
    visibility_verified: bool = False
    resolved_targets: tuple[GameplayResolvedReference, ...] = ()
    unresolved_targets: tuple[SemanticMention, ...] = ()
    ambiguous_targets: tuple[SemanticMention, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.actor_ambiguous, bool):
            raise TypeError("actor_ambiguous must be a boolean")
        if not isinstance(self.visibility_verified, bool):
            raise TypeError("visibility_verified must be a boolean")
        if self.actor_ambiguous and self.actor_reference is not None:
            raise ValueError("ambiguous actor resolution cannot include a canonical actor")
        if self.actor_reference is not None and not isinstance(
            self.actor_reference, GameplayResolvedReference
        ):
            raise TypeError("actor_reference must be a trusted resolved reference")
        for name, values in (
            ("resolved_targets", self.resolved_targets),
            ("unresolved_targets", self.unresolved_targets),
            ("ambiguous_targets", self.ambiguous_targets),
        ):
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be a tuple")
        if any(
            not isinstance(item, GameplayResolvedReference)
            for item in self.resolved_targets
        ):
            raise TypeError("resolved_targets must contain resolved references")
        if any(
            not isinstance(item, SemanticMention)
            for item in (*self.unresolved_targets, *self.ambiguous_targets)
        ):
            raise TypeError("unresolved/ambiguous targets must be literal mentions")


@dataclass(frozen=True, slots=True)
class ActionGraphBuildResult:
    checkpoint: PlayerActionCheckpoint
    excluded_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionSelection:
    checkpoint: PlayerActionCheckpoint
    status: ActionSelectionStatus
    candidate: GameplayActionCandidate | None = None
    execution_key: str | None = None
    resume_existing_attempt: bool = False
    clarification_slots: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClarificationResumeResult:
    checkpoint: PlayerActionCheckpoint
    updated_event_id: str
    affected_descendant_event_ids: tuple[str, ...]


def _fold(value: str) -> str:
    return " ".join(value.casefold().split())


def _workflow_for(event: EventFrame) -> GameplayWorkflow:
    if event.family in {
        SemanticActionFamily.COMMUNICATION,
        SemanticActionFamily.SOCIAL,
    }:
        return GameplayWorkflow.DIALOGUE
    if event.family in _MECHANICS_FAMILIES:
        return GameplayWorkflow.MECHANICS
    return GameplayWorkflow.NONE


def _agent(event: EventFrame) -> SemanticMention | None:
    values = tuple(
        item.mention
        for item in event.arguments
        if item.role is SemanticArgumentRole.AGENT
    )
    return values[0] if len(values) == 1 else None


def _target_mentions(
    event: EventFrame,
    act: UtteranceAct,
    actor: SemanticMention,
) -> tuple[SemanticMention, ...]:
    seen: set[str] = set()
    result = []
    for argument in event.arguments:
        if argument.role not in _TARGET_ROLES:
            continue
        key = _fold(argument.mention.text)
        if key not in seen:
            seen.add(key)
            result.append(argument.mention)
    if (
        event.family in {
            SemanticActionFamily.COMMUNICATION,
            SemanticActionFamily.SOCIAL,
        }
        and act.addressee_mention is not None
    ):
        key = _fold(act.addressee_mention.text)
        if key != _fold(actor.text) and key not in seen:
            result.append(act.addressee_mention)
    return tuple(result)


def _covered_by_quote(event: EventFrame, act: UtteranceAct) -> bool:
    # A broad sentence-level event span that intersects quoted content is
    # ambiguous; fail closed rather than promote a quoted instruction.
    return any(
        evidence.start < quote.end and quote.start < evidence.end
        for evidence in event.evidence_spans
        for quote in act.quote_spans
    )


def _event_ref(reference: str | None) -> str | None:
    if reference is None or not reference.startswith("event:"):
        return None
    return reference.removeprefix("event:")


def _condition_dependencies(
    interpretation: TurnInterpretationV3,
) -> dict[str, tuple[str, ...]]:
    event_ids = {item.local_id for item in interpretation.events}
    dependencies: dict[str, list[str]] = {}
    for link in interpretation.discourse_links:
        if link.link_type is not DiscourseLinkType.CONDITION_ON_SUCCESS:
            continue
        dependent = _event_ref(link.source_ref)
        prerequisite = _event_ref(link.target_ref)
        if dependent is None or prerequisite is None:
            raise ActionSelectorError(
                "condition_on_success links must connect two event records"
            )
        if dependent not in event_ids or prerequisite not in event_ids:
            raise ActionSelectorError(
                "condition_on_success link references an unknown event"
            )
        dependencies.setdefault(dependent, []).append(prerequisite)

    normalized: dict[str, tuple[str, ...]] = {}
    for dependent, prerequisites in dependencies.items():
        if len(set(prerequisites)) != len(prerequisites):
            raise ActionSelectorError("duplicate action dependencies are not allowed")
        normalized[dependent] = tuple(prerequisites)
    return normalized


def _reference_partition(
    expected: tuple[SemanticMention, ...],
    resolution: ActionReferenceResolution,
) -> tuple[
    tuple[GameplayResolvedReference, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    expected_by_key = {_fold(item.text): item for item in expected}
    if len(expected_by_key) != len(expected):
        raise ActionSelectorError("event has duplicate target mentions")
    resolved_by_key = {
        _fold(item.mention.text): item for item in resolution.resolved_targets
    }
    unresolved_items = tuple(_fold(item.text) for item in resolution.unresolved_targets)
    ambiguous_items = tuple(_fold(item.text) for item in resolution.ambiguous_targets)
    unresolved = set(unresolved_items)
    ambiguous = set(ambiguous_items)
    if len(set(unresolved_items)) != len(unresolved_items):
        raise ActionSelectorError("target resolver returned duplicate unresolved mentions")
    if len(set(ambiguous_items)) != len(ambiguous_items):
        raise ActionSelectorError("target resolver returned duplicate ambiguous mentions")
    if len(resolved_by_key) != len(resolution.resolved_targets):
        raise ActionSelectorError("target resolver returned duplicate references")
    if unresolved & ambiguous or unresolved & set(resolved_by_key) or ambiguous & set(
        resolved_by_key
    ):
        raise ActionSelectorError("target resolver returned overlapping outcomes")
    supplied = set(resolved_by_key) | unresolved | ambiguous
    if supplied - set(expected_by_key):
        raise ActionSelectorError("target resolver returned an unrelated mention")
    missing = set(expected_by_key) - supplied
    unresolved.update(missing)
    resolved = tuple(
        resolved_by_key[_fold(mention.text)]
        for mention in expected
        if _fold(mention.text) in resolved_by_key
    )
    return resolved, tuple(sorted(unresolved)), tuple(sorted(ambiguous))


def _unique_resolved_references(
    actor: GameplayResolvedReference,
    targets: tuple[GameplayResolvedReference, ...],
) -> tuple[GameplayResolvedReference, ...]:
    """Preserve mention order while deduplicating identical canonical targets."""
    result = []
    seen: set[tuple[GameplayResolvedReferenceKind, int | str]] = set()
    for reference in (actor, *targets):
        key = (reference.category, reference.referent_id)
        if key not in seen:
            seen.add(key)
            result.append(reference)
    return tuple(result)


def _candidate_base(
    event: EventFrame,
    actor: SemanticMention,
    targets: tuple[SemanticMention, ...],
    resolved_references: tuple[GameplayResolvedReference, ...],
    dependencies: tuple[str, ...],
    *,
    eligibility: GameplayActionEligibility,
    reason: GameplayActionReason,
    workflow: GameplayWorkflow,
    unlock_condition: GameplayUnlockCondition = GameplayUnlockCondition.NONE,
) -> GameplayActionCandidate:
    return GameplayActionCandidate(
        local_id="action_" + hashlib.sha256(
            event.local_id.encode("utf-8")
        ).hexdigest()[:24],
        source_event_id=event.local_id,
        actor=actor,
        action_type=event.family.value,
        eligibility=eligibility,
        reason=reason,
        workflow=workflow,
        unlock_condition=unlock_condition,
        processing_state=GameplayProcessingState.PENDING,
        target_mentions=targets,
        dependency_event_ids=dependencies,
        resolved_references=resolved_references,
    )


def _candidate_for_event(
    event: EventFrame,
    *,
    act: UtteranceAct,
    active_character_id: int,
    resolution: ActionReferenceResolution,
    dependencies: tuple[str, ...],
    conditional: bool,
) -> GameplayActionCandidate:
    actor = _agent(event)
    if actor is None:
        raise ActionSelectorError("action event must have exactly one agent")
    targets = _target_mentions(event, act, actor)
    workflow = _workflow_for(event)

    if act.speaker_role is not SpeakerRole.PLAYER or _covered_by_quote(event, act):
        return _candidate_base(
            event, actor, targets, (), dependencies,
            eligibility=GameplayActionEligibility.INELIGIBLE,
            reason=GameplayActionReason.OUTSIDE_PLAYER_SCOPE,
            workflow=GameplayWorkflow.NONE,
        )
    if workflow is GameplayWorkflow.NONE:
        return _candidate_base(
            event, actor, targets, (), dependencies,
            eligibility=GameplayActionEligibility.INELIGIBLE,
            reason=GameplayActionReason.UNSUPPORTED_ACTION,
            workflow=GameplayWorkflow.NONE,
        )
    if event.polarity is SemanticPolarity.NEGATIVE:
        return _candidate_base(
            event, actor, targets, (), dependencies,
            eligibility=GameplayActionEligibility.INELIGIBLE,
            reason=GameplayActionReason.NEGATED,
            workflow=GameplayWorkflow.NONE,
        )

    if conditional:
        if event.action_phase is not ActionPhase.PLANNED:
            raise ActionSelectorError(
                "condition_on_success dependent events must be planned"
            )
        if event.epistemic_status not in {
            EpistemicStatus.HYPOTHETICAL,
            EpistemicStatus.ASSERTED,
        }:
            return _candidate_base(
                event, actor, targets, (), dependencies,
                eligibility=GameplayActionEligibility.INELIGIBLE,
                reason=GameplayActionReason.NOT_AN_ATTEMPT,
                workflow=GameplayWorkflow.NONE,
            )
    elif (
        event.action_phase is not ActionPhase.ATTEMPTED
        or event.epistemic_status is not EpistemicStatus.ASSERTED
    ):
        return _candidate_base(
            event, actor, targets, (), dependencies,
            eligibility=GameplayActionEligibility.INELIGIBLE,
            reason=(
                GameplayActionReason.CONDITIONAL
                if event.action_phase is ActionPhase.PLANNED
                else GameplayActionReason.NOT_AN_ATTEMPT
            ),
            workflow=GameplayWorkflow.NONE,
        )

    allowed_mechanics_forces = {
        UtteranceForce.ASSERTION,
        UtteranceForce.IN_CHARACTER_DIALOGUE,
    }
    if conditional:
        allowed_mechanics_forces.add(UtteranceForce.HYPOTHESIS)
    if (
        workflow is GameplayWorkflow.MECHANICS
        and act.force not in allowed_mechanics_forces
    ):
        return _candidate_base(
            event, actor, targets, (), dependencies,
            eligibility=GameplayActionEligibility.INELIGIBLE,
            reason=GameplayActionReason.OUTSIDE_PLAYER_SCOPE,
            workflow=GameplayWorkflow.NONE,
        )
    if workflow is GameplayWorkflow.DIALOGUE and act.force not in _DIALOGUE_FORCES:
        return _candidate_base(
            event, actor, targets, (), dependencies,
            eligibility=GameplayActionEligibility.INELIGIBLE,
            reason=GameplayActionReason.OUTSIDE_PLAYER_SCOPE,
            workflow=GameplayWorkflow.NONE,
        )

    if resolution.actor_ambiguous:
        return _candidate_base(
            event, actor, targets, (), dependencies,
            eligibility=GameplayActionEligibility.REQUIRES_CLARIFICATION,
            reason=GameplayActionReason.AMBIGUOUS_REFERENCE,
            workflow=GameplayWorkflow.CLARIFICATION,
        )
    if not resolution.visibility_verified and (
        resolution.actor_reference is not None or resolution.resolved_targets
    ):
        raise ActionSelectorError(
            "canonical references require an explicit visibility verification"
        )
    actor_reference = resolution.actor_reference
    if actor_reference is None:
        return _candidate_base(
            event, actor, targets, (), dependencies,
            eligibility=GameplayActionEligibility.REQUIRES_CLARIFICATION,
            reason=GameplayActionReason.UNRESOLVED_REFERENCE,
            workflow=GameplayWorkflow.CLARIFICATION,
        )
    if _fold(actor_reference.mention.text) != _fold(actor.text):
        raise ActionSelectorError("resolved actor does not match its event mention")
    if actor_reference.category is not GameplayResolvedReferenceKind.ENTITY:
        raise ActionSelectorError("player actor must resolve to an entity")
    if actor_reference.referent_id != active_character_id:
        return _candidate_base(
            event, actor, targets, (actor_reference,), dependencies,
            eligibility=GameplayActionEligibility.INELIGIBLE,
            reason=GameplayActionReason.NON_PLAYER_ACTOR,
            workflow=GameplayWorkflow.NONE,
        )

    resolved_targets, unresolved, ambiguous = _reference_partition(
        targets, resolution
    )
    if ambiguous:
        return _candidate_base(
            event, actor, targets, _unique_resolved_references(actor_reference, resolved_targets), dependencies,
            eligibility=GameplayActionEligibility.REQUIRES_CLARIFICATION,
            reason=GameplayActionReason.AMBIGUOUS_REFERENCE,
            workflow=GameplayWorkflow.CLARIFICATION,
        )
    if unresolved:
        return _candidate_base(
            event, actor, targets, _unique_resolved_references(actor_reference, resolved_targets), dependencies,
            eligibility=GameplayActionEligibility.REQUIRES_CLARIFICATION,
            reason=GameplayActionReason.UNRESOLVED_REFERENCE,
            workflow=GameplayWorkflow.CLARIFICATION,
        )

    return _candidate_base(
        event, actor, targets, _unique_resolved_references(actor_reference, resolved_targets), dependencies,
        eligibility=(
            GameplayActionEligibility.BLOCKED_BY_DEPENDENCY
            if conditional
            else GameplayActionEligibility.ELIGIBLE
        ),
        reason=(
            GameplayActionReason.DEPENDENCY_PENDING
            if conditional
            else GameplayActionReason.ELIGIBLE
        ),
        workflow=workflow,
        unlock_condition=(
            GameplayUnlockCondition.DEPENDENCY_SUCCESS
            if conditional
            else GameplayUnlockCondition.NONE
        ),
    )


def fact_candidate_json(candidate: WorldFactCandidate) -> str:
    """Return a canonical, bounded snapshot of one exact v3 fact candidate."""
    if not isinstance(candidate, WorldFactCandidate):
        raise TypeError("candidate must be a WorldFactCandidate")
    payload = json.dumps(
        candidate.to_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(payload.encode("utf-8")) > 16_384:
        raise ActionSelectorError("fact candidate exceeds its checkpoint byte budget")
    return payload


def fact_candidate_sha256(candidate: WorldFactCandidate) -> str:
    """Fingerprint one exact v3 fact candidate for a backend validation receipt."""
    return hashlib.sha256(
        fact_candidate_json(candidate).encode("utf-8")
    ).hexdigest()


def record_fact_validation_receipts(
    checkpoint: PlayerActionCheckpoint,
    interpretation: TurnInterpretationV3,
    receipts: tuple[FactValidationReceipt, ...],
) -> PlayerActionCheckpoint:
    """Append/advance backend fact-validation receipts without resetting actions."""
    if not isinstance(checkpoint, PlayerActionCheckpoint):
        raise TypeError("checkpoint must be a PlayerActionCheckpoint")
    if not isinstance(interpretation, TurnInterpretationV3):
        raise TypeError("interpretation must be a TurnInterpretationV3")
    if not isinstance(receipts, tuple) or any(
        not isinstance(item, FactValidationReceipt) for item in receipts
    ):
        raise TypeError("receipts must be a tuple of FactValidationReceipt")
    interpretation_digest = hashlib.sha256(
        interpretation.to_json().encode("utf-8")
    ).hexdigest()
    if checkpoint.interpretation_sha256 != interpretation_digest:
        raise ActionSelectorError(
            "fact validation receipts belong to a different interpretation"
        )
    facts = {item.local_id: item for item in interpretation.world_facts}
    merged = {
        item.fact_local_id: item
        for item in checkpoint.fact_validation_receipts
    }
    for receipt in receipts:
        fact = facts.get(receipt.fact_local_id)
        if fact is None or fact.source_act_id != receipt.source_act_id:
            raise ActionSelectorError(
                "fact validation receipt does not match this interpretation"
            )
        if (
            receipt.candidate_sha256 != fact_candidate_sha256(fact)
            or receipt.candidate_json != fact_candidate_json(fact)
        ):
            raise ActionSelectorError(
                "fact validation receipt is not bound to the exact candidate"
            )
        previous = merged.get(receipt.fact_local_id)
        if previous is not None:
            if previous.candidate_sha256 != receipt.candidate_sha256:
                raise ActionSelectorError(
                    "fact validation receipt cannot change candidate identity"
                )
            if previous.state is not FactValidationState.PENDING and (
                previous.state is not receipt.state
            ):
                raise ActionSelectorError(
                    "a final fact validation decision cannot be reversed"
                )
        merged[receipt.fact_local_id] = receipt
    ordered = tuple(
        merged[fact.local_id]
        for fact in interpretation.world_facts
        if fact.local_id in merged
    )
    return replace(checkpoint, fact_validation_receipts=ordered)


def build_action_checkpoint(
    interpretation: TurnInterpretationV3,
    *,
    resolution_id: int,
    context_revision: int,
    source_text: str,
    active_character_id: int,
    reference_resolutions: Mapping[str, ActionReferenceResolution] | None = None,
    fact_validation_receipts: tuple[FactValidationReceipt, ...] = (),
) -> ActionGraphBuildResult:
    """Derive a bounded graph from v3 semantics and trusted resolver results."""
    if not isinstance(interpretation, TurnInterpretationV3):
        raise TypeError("interpretation must be a TurnInterpretationV3")
    if not isinstance(source_text, str) or not source_text.strip():
        raise ValueError("source_text must not be empty")
    if isinstance(active_character_id, bool) or not isinstance(
        active_character_id, int
    ) or active_character_id < 1:
        raise ValueError("active_character_id must be a positive integer")
    resolutions = {} if reference_resolutions is None else dict(reference_resolutions)
    if any(
        not isinstance(value, ActionReferenceResolution)
        for value in resolutions.values()
    ):
        raise TypeError(
            "reference_resolutions must contain ActionReferenceResolution"
        )
    if not isinstance(fact_validation_receipts, tuple) or any(
        not isinstance(item, FactValidationReceipt)
        for item in fact_validation_receipts
    ):
        raise TypeError(
            "fact_validation_receipts must be a tuple of FactValidationReceipt"
        )
    all_records = (
        *interpretation.utterance_acts,
        *interpretation.events,
        *interpretation.discourse_links,
        *interpretation.world_facts,
        *interpretation.clarification_candidates,
    )
    for item in all_records:
        spans = list(item.evidence_spans)
        spans.extend(getattr(item, "quote_spans", ()))
        for span in spans:
            try:
                span.validate_source(source_text)
            except ValueError:
                raise ActionSelectorError(
                    "interpretation evidence does not match the checkpoint source"
                ) from None
    events = tuple(
        sorted(interpretation.events, key=lambda item: item.evidence_spans[0].start)
    )
    acts = {item.local_id: item for item in interpretation.utterance_acts}
    dependencies = _condition_dependencies(interpretation)
    ordered_ids = {item.local_id: index for index, item in enumerate(events)}
    for dependent, prerequisite_ids in dependencies.items():
        for prerequisite in prerequisite_ids:
            if ordered_ids[prerequisite] >= ordered_ids[dependent]:
                raise ActionSelectorError(
                    "conditional dependency must precede its dependent event"
                )

    candidates: list[GameplayActionCandidate] = []
    excluded: list[str] = []
    for event in events:
        actor = _agent(event)
        if actor is None:
            excluded.append(event.local_id)
            continue
        act = acts.get(event.source_act_id)
        if act is None:
            raise ActionSelectorError("event source act is missing")
        dependency_ids = dependencies.get(event.local_id, ())
        candidates.append(
            _candidate_for_event(
                event,
                act=act,
                active_character_id=active_character_id,
                resolution=resolutions.get(event.local_id, ActionReferenceResolution()),
                dependencies=dependency_ids,
                conditional=bool(dependency_ids),
            )
        )

    unknown_resolutions = set(resolutions) - {
        item.local_id for item in interpretation.events
    }
    if unknown_resolutions:
        raise ActionSelectorError(
            "reference resolver returned an event outside this interpretation"
        )

    candidate_ids = {item.source_event_id for item in candidates}
    for dependent, prerequisite_ids in dependencies.items():
        if dependent not in candidate_ids or any(
            item not in candidate_ids for item in prerequisite_ids
        ):
            raise ActionSelectorError(
                "conditional dependency cannot target an excluded action event"
            )

    nodes = []
    for index, candidate in enumerate(candidates):
        state = (
            ActionExecutionState.SKIPPED
            if candidate.eligibility is GameplayActionEligibility.INELIGIBLE
            else (
                ActionExecutionState.AWAITING_INPUT
                if candidate.eligibility
                is GameplayActionEligibility.REQUIRES_CLARIFICATION
                else ActionExecutionState.PENDING
            )
        )
        execution_key = hashlib.sha256(
            (
                f"{resolution_id}:"
                f"{hashlib.sha256(source_text.encode('utf-8')).hexdigest()}:"
                f"{candidate.source_event_id}"
            ).encode()
        ).hexdigest()
        nodes.append(
            ActionCheckpointNode(
                candidate=replace(
                    candidate,
                    processing_state=processing_state_for(state),
                ),
                source_order=index,
                state=state,
                execution_key=execution_key,
                clarification_slots=(
                    ("actor", "target")
                    if state is ActionExecutionState.AWAITING_INPUT
                    else ()
                ),
            )
        )

    fact_by_id = {
        item.local_id: item for item in interpretation.world_facts
    }
    for receipt in fact_validation_receipts:
        fact = fact_by_id.get(receipt.fact_local_id)
        if fact is None or fact.source_act_id != receipt.source_act_id:
            raise ActionSelectorError(
                "fact validation receipt does not match this interpretation"
            )
        if (
            receipt.candidate_sha256 != fact_candidate_sha256(fact)
            or receipt.candidate_json != fact_candidate_json(fact)
        ):
            raise ActionSelectorError(
                "fact validation receipt is not bound to the exact candidate"
            )

    checkpoint = PlayerActionCheckpoint(
        resolution_id=resolution_id,
        context_revision=context_revision,
        source_sha256=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        interpretation_sha256=hashlib.sha256(
            interpretation.to_json().encode("utf-8")
        ).hexdigest(),
        nodes=tuple(nodes),
        fact_validation_receipts=fact_validation_receipts,
    )
    return ActionGraphBuildResult(
        checkpoint=checkpoint,
        excluded_event_ids=tuple(excluded),
    )


def _dependency_nodes(
    checkpoint: PlayerActionCheckpoint,
) -> dict[str, ActionCheckpointNode]:
    return {
        node.candidate.source_event_id: node for node in checkpoint.nodes
    }


def _set_node(
    checkpoint: PlayerActionCheckpoint,
    updated: ActionCheckpointNode,
) -> PlayerActionCheckpoint:
    nodes = tuple(
        updated if item.candidate.source_event_id == updated.candidate.source_event_id
        else item
        for item in checkpoint.nodes
    )
    return replace(checkpoint, nodes=nodes)


def _mark_skipped(
    node: ActionCheckpointNode,
) -> ActionCheckpointNode:
    candidate = replace(
        node.candidate,
        eligibility=GameplayActionEligibility.INELIGIBLE,
        reason=GameplayActionReason.CONDITIONAL,
        workflow=GameplayWorkflow.NONE,
        unlock_condition=GameplayUnlockCondition.NONE,
        processing_state=GameplayProcessingState.BLOCKED,
    )
    return replace(
        node,
        candidate=candidate,
        state=ActionExecutionState.SKIPPED,
        clarification_slots=(),
        outcome=None,
    )


def select_next_action(
    checkpoint: PlayerActionCheckpoint,
) -> ActionSelection:
    """Return at most one action; dependent nodes only run after success."""
    if not isinstance(checkpoint, PlayerActionCheckpoint):
        raise TypeError("checkpoint must be a PlayerActionCheckpoint")
    current = checkpoint
    for node in current.nodes:
        if node.state in {
            ActionExecutionState.RESOLVED,
            ActionExecutionState.SKIPPED,
        }:
            continue
        dependency_nodes = _dependency_nodes(current)
        dependencies = tuple(
            dependency_nodes[item]
            for item in node.candidate.dependency_event_ids
        )
        if dependencies:
            failed = any(
                dependency.state is ActionExecutionState.SKIPPED
                or (
                    dependency.state is ActionExecutionState.RESOLVED
                    and dependency.outcome is ActionOutcome.FAILURE
                )
                for dependency in dependencies
            )
            if failed:
                current = _set_node(current, _mark_skipped(node))
                continue
            successful = all(
                dependency.state is ActionExecutionState.RESOLVED
                and dependency.outcome is ActionOutcome.SUCCESS
                for dependency in dependencies
            )
            if not successful:
                return ActionSelection(
                    checkpoint=current,
                    status=ActionSelectionStatus.BLOCKED_BY_DEPENDENCY,
                    candidate=node.candidate,
                    execution_key=node.execution_key,
                )

        if node.state is ActionExecutionState.AWAITING_INPUT:
            return ActionSelection(
                checkpoint=current,
                status=ActionSelectionStatus.NEEDS_CLARIFICATION,
                candidate=node.candidate,
                execution_key=node.execution_key,
                clarification_slots=node.clarification_slots,
            )
        if node.state is ActionExecutionState.IN_PROGRESS:
            return ActionSelection(
                checkpoint=current,
                status=ActionSelectionStatus.READY,
                candidate=node.candidate,
                execution_key=node.execution_key,
                resume_existing_attempt=True,
            )

        candidate = node.candidate
        if candidate.eligibility is GameplayActionEligibility.BLOCKED_BY_DEPENDENCY:
            candidate = replace(
                candidate,
                eligibility=GameplayActionEligibility.ELIGIBLE,
                reason=GameplayActionReason.ELIGIBLE,
                unlock_condition=GameplayUnlockCondition.NONE,
            )
        return ActionSelection(
            checkpoint=current,
            status=ActionSelectionStatus.READY,
            candidate=candidate,
            execution_key=node.execution_key,
            resume_existing_attempt=(
                node.state is ActionExecutionState.EXECUTION_FAILED
            ),
        )
    if current != checkpoint:
        return ActionSelection(
            checkpoint=current,
            status=ActionSelectionStatus.EXHAUSTED,
        )
    return ActionSelection(
        checkpoint=current,
        status=ActionSelectionStatus.EXHAUSTED,
    )


def mark_action_started(
    checkpoint: PlayerActionCheckpoint,
    event_id: str,
) -> tuple[PlayerActionCheckpoint, str, bool]:
    """Begin/recover a node and return its stable idempotency key."""
    selection = select_next_action(checkpoint)
    if (
        selection.status is not ActionSelectionStatus.READY
        or selection.candidate is None
        or selection.candidate.source_event_id != event_id
        or selection.execution_key is None
    ):
        raise ActionSelectorError("action is not the next eligible action")
    node = next(
        item for item in selection.checkpoint.nodes
        if item.candidate.source_event_id == event_id
    )
    resumed = node.state in {
        ActionExecutionState.IN_PROGRESS,
        ActionExecutionState.EXECUTION_FAILED,
    }
    if node.state is ActionExecutionState.IN_PROGRESS:
        return selection.checkpoint, node.execution_key, True
    candidate = replace(
        selection.candidate,
        processing_state=GameplayProcessingState.ADJUDICATING,
    )
    started = replace(
        node,
        candidate=candidate,
        state=ActionExecutionState.IN_PROGRESS,
        attempt_count=node.attempt_count + 1,
        outcome=None,
        clarification_slots=(),
    )
    return _set_node(selection.checkpoint, started), node.execution_key, resumed


def mark_action_completed(
    checkpoint: PlayerActionCheckpoint,
    event_id: str,
    outcome: ActionOutcome,
) -> PlayerActionCheckpoint:
    """Record a backend/rules-engine outcome, never a model-reported result."""
    if not isinstance(outcome, ActionOutcome):
        raise TypeError("outcome must be an authoritative ActionOutcome")
    node = next(
        (
            item for item in checkpoint.nodes
            if item.candidate.source_event_id == event_id
        ),
        None,
    )
    if node is None:
        raise ActionSelectorError("action event is not in this checkpoint")
    if node.state is ActionExecutionState.RESOLVED:
        if node.outcome is outcome:
            return checkpoint
        raise ActionSelectorError("a resolved action outcome is immutable")
    if node.state is not ActionExecutionState.IN_PROGRESS:
        raise ActionSelectorError("only an in-progress action can be resolved")
    candidate = replace(
        node.candidate,
        eligibility=GameplayActionEligibility.ELIGIBLE,
        reason=GameplayActionReason.ELIGIBLE,
        workflow=node.candidate.workflow,
        unlock_condition=GameplayUnlockCondition.NONE,
        processing_state=GameplayProcessingState.RESOLVED,
    )
    return _set_node(
        checkpoint,
        replace(
            node,
            candidate=candidate,
            state=ActionExecutionState.RESOLVED,
            outcome=outcome,
            clarification_slots=(),
        ),
    )


def mark_action_execution_failed(
    checkpoint: PlayerActionCheckpoint,
    event_id: str,
) -> PlayerActionCheckpoint:
    """Record an infrastructure failure; retry must reuse the same execution key."""
    node = next(
        (
            item for item in checkpoint.nodes
            if item.candidate.source_event_id == event_id
        ),
        None,
    )
    if node is None:
        raise ActionSelectorError("action event is not in this checkpoint")
    if node.state is ActionExecutionState.EXECUTION_FAILED:
        return checkpoint
    if node.state is not ActionExecutionState.IN_PROGRESS:
        raise ActionSelectorError("only an in-progress action can fail execution")
    candidate = replace(
        node.candidate,
        processing_state=GameplayProcessingState.FAILED,
    )
    return _set_node(
        checkpoint,
        replace(
            node,
            candidate=candidate,
            state=ActionExecutionState.EXECUTION_FAILED,
            outcome=None,
        ),
    )


def mark_action_awaiting_input(
    checkpoint: PlayerActionCheckpoint,
    event_id: str,
    clarification_slots: tuple[str, ...],
) -> PlayerActionCheckpoint:
    """Pause one action while preserving the rest of the graph."""
    node = next(
        (
            item for item in checkpoint.nodes
            if item.candidate.source_event_id == event_id
        ),
        None,
    )
    if node is None:
        raise ActionSelectorError("action event is not in this checkpoint")
    if node.state is ActionExecutionState.AWAITING_INPUT:
        if node.clarification_slots == clarification_slots:
            return checkpoint
        raise ActionSelectorError("awaiting-input clarification slots are immutable")
    if node.state not in {
        ActionExecutionState.PENDING,
        ActionExecutionState.IN_PROGRESS,
    }:
        raise ActionSelectorError("action cannot be moved to awaiting input")
    candidate = replace(
        node.candidate,
        eligibility=GameplayActionEligibility.REQUIRES_CLARIFICATION,
        reason=GameplayActionReason.CLARIFICATION_REQUIRED,
        workflow=GameplayWorkflow.CLARIFICATION,
        unlock_condition=GameplayUnlockCondition.NONE,
        processing_state=GameplayProcessingState.AWAITING_INPUT,
    )
    return _set_node(
        checkpoint,
        replace(
            node,
            candidate=candidate,
            state=ActionExecutionState.AWAITING_INPUT,
            outcome=None,
            clarification_slots=clarification_slots,
        ),
    )


def _descendants(
    checkpoint: PlayerActionCheckpoint,
    event_id: str,
) -> tuple[str, ...]:
    children: dict[str, set[str]] = {}
    for node in checkpoint.nodes:
        for dependency in node.candidate.dependency_event_ids:
            children.setdefault(dependency, set()).add(
                node.candidate.source_event_id
            )
    found: set[str] = set()
    pending = list(children.get(event_id, ()))
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        pending.extend(children.get(current, ()))
    return tuple(
        node.candidate.source_event_id
        for node in checkpoint.nodes
        if node.candidate.source_event_id in found
    )


def resume_after_clarification(
    checkpoint: PlayerActionCheckpoint,
    event_id: str,
    updated_candidate: GameplayActionCandidate,
    *,
    clarification_slots: tuple[str, ...] = (),
) -> ClarificationResumeResult:
    """Update only the clarified action and report its transitive dependants."""
    node = next(
        (
            item for item in checkpoint.nodes
            if item.candidate.source_event_id == event_id
        ),
        None,
    )
    if node is None or node.state is not ActionExecutionState.AWAITING_INPUT:
        raise ActionSelectorError("action is not awaiting clarification")
    if not isinstance(updated_candidate, GameplayActionCandidate):
        raise TypeError("updated_candidate must be backend-derived")
    if (
        updated_candidate.source_event_id != event_id
        or updated_candidate.actor != node.candidate.actor
        or updated_candidate.action_type != node.candidate.action_type
        or updated_candidate.dependency_event_ids
        != node.candidate.dependency_event_ids
    ):
        raise ActionSelectorError(
            "clarification may not replace action identity or dependencies"
        )
    if updated_candidate.eligibility is GameplayActionEligibility.REQUIRES_CLARIFICATION:
        state = ActionExecutionState.AWAITING_INPUT
        updated_candidate = replace(
            updated_candidate,
            reason=(
                updated_candidate.reason
                if updated_candidate.reason is not GameplayActionReason.ELIGIBLE
                else GameplayActionReason.CLARIFICATION_REQUIRED
            ),
            workflow=GameplayWorkflow.CLARIFICATION,
            processing_state=GameplayProcessingState.AWAITING_INPUT,
        )
    elif updated_candidate.eligibility in {
        GameplayActionEligibility.ELIGIBLE,
        GameplayActionEligibility.BLOCKED_BY_DEPENDENCY,
    }:
        if (
            updated_candidate.eligibility
            is GameplayActionEligibility.BLOCKED_BY_DEPENDENCY
            and (
                not updated_candidate.dependency_event_ids
                or updated_candidate.unlock_condition
                is not GameplayUnlockCondition.DEPENDENCY_SUCCESS
            )
        ):
            raise ActionSelectorError(
                "dependency-blocked clarification must retain its success gate"
            )
        state = ActionExecutionState.PENDING
        updated_candidate = replace(
            updated_candidate,
            processing_state=GameplayProcessingState.PENDING,
        )
    else:
        raise ActionSelectorError(
            "clarification must resolve to eligible, dependency-blocked or still-ambiguous action"
        )
    updated = replace(
        node,
        candidate=updated_candidate,
        state=state,
        clarification_slots=(
            clarification_slots if state is ActionExecutionState.AWAITING_INPUT else ()
        ),
        outcome=None,
    )
    next_checkpoint = _set_node(checkpoint, updated)
    return ClarificationResumeResult(
        checkpoint=next_checkpoint,
        updated_event_id=event_id,
        affected_descendant_event_ids=_descendants(checkpoint, event_id),
    )
