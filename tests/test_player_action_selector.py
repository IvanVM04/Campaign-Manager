import hashlib
import json
from dataclasses import replace

import pytest

from models.player_action_checkpoint import (
    ActionCheckpointValidationError,
    ActionExecutionState,
    ActionOutcome,
    FactValidationReceipt,
    FactValidationState,
    PlayerActionCheckpoint,
)
from models.player_turn_interpretation_v3 import (
    GameplayActionEligibility,
    GameplayActionReason,
    GameplayProcessingState,
    GameplayResolvedReference,
    GameplayResolvedReferenceKind,
    GameplayUnlockCondition,
    GameplayWorkflow,
    TurnInterpretationV3,
    WorldFactCandidate,
)
from models.semantic_frames import (
    SemanticMention,
    SemanticObjectKind,
)
from services.turns.player_action_selector import (
    ActionReferenceResolution,
    ActionSelectionStatus,
    ActionSelectorError,
    build_action_checkpoint,
    fact_candidate_json,
    fact_candidate_sha256,
    record_fact_validation_receipts,
    mark_action_completed,
    mark_action_execution_failed,
    mark_action_started,
    resume_after_clarification,
    select_next_action,
)


def _span(source, value):
    start = source.index(value)
    return {
        "start": start,
        "end": start + len(value),
        "text": value,
        "source": "current_utterance",
    }


def _mention(value, kind="character"):
    return {"text": value, "kind_hint": kind}


def _event(
    source,
    event_id,
    predicate,
    evidence,
    *,
    family="movement",
    actor="Yo",
    target="el muro",
    phase="attempted",
    epistemic="asserted",
    polarity="positive",
    source_act="act_player",
):
    arguments = [
        {"role": "agent", "mention": _mention(actor)},
    ]
    if target is not None:
        arguments.append(
            {
                "role": "theme",
                "mention": _mention(target, "location"),
            }
        )
    return {
        "local_id": event_id,
        "source_act_id": source_act,
        "predicate_surface": predicate,
        "family": family,
        "arguments": arguments,
        "polarity": polarity,
        "epistemic_status": epistemic,
        "action_phase": phase,
        "temporal_expression": None,
        "attributed_source": None,
        "evidence_spans": [_span(source, evidence)],
    }


def _interpretation(
    source,
    events,
    *,
    links=(),
    quote=None,
    speaker_role="player",
    force="assertion",
):
    act = {
        "local_id": "act_player" if speaker_role == "player" else "act_npc",
        "force": force,
        "speaker_role": speaker_role,
        "speaker_mention": None,
        "addressee_mention": None,
        "quote_spans": [_span(source, quote)] if quote else [],
        "evidence_spans": [_span(source, source)],
    }
    for event in events:
        if speaker_role != "player":
            event["source_act_id"] = "act_npc"
    return TurnInterpretationV3.from_payload(
        {
            "schema_version": 3,
            "utterance_acts": [act],
            "events": events,
            "discourse_links": list(links),
            "world_facts": [],
            "clarification_candidates": [],
        },
        source_text=source,
    )


def _resolution(source, event_id, *, active_id=7, actor="Yo", target=None):
    actor_ref = GameplayResolvedReference(
        mention=SemanticMention(actor),
        category=GameplayResolvedReferenceKind.ENTITY,
        referent_id=active_id,
        name="Hero",
    )
    targets = ()
    if target is not None:
        targets = (
            GameplayResolvedReference(
                mention=SemanticMention(
                    target, kind_hint=SemanticObjectKind.LOCATION
                ),
                category=GameplayResolvedReferenceKind.ENTITY,
                referent_id=100 + len(event_id),
                name=target,
            ),
        )
    return ActionReferenceResolution(
        actor_reference=actor_ref,
        visibility_verified=True,
        resolved_targets=targets,
    )


def _basic_graph():
    source = (
        "Yo intento escalar el muro. "
        "Si llego a la cornisa, yo entro en la torre. "
        "Luego yo examino el cofre."
    )
    events = [
        _event(
            source, "event_climb", "escalar",
            "Yo intento escalar el muro", target="el muro",
        ),
        _event(
            source, "event_enter", "entro",
            "yo entro en la torre", target="la torre",
            phase="planned", epistemic="hypothetical",
        ),
        _event(
            source, "event_examine", "examino",
            "yo examino el cofre", family="perception",
            target="el cofre",
        ),
    ]
    link = {
        "local_id": "link_condition",
        "source_ref": "event:event_enter",
        "target_ref": "event:event_climb",
        "link_type": "condition_on_success",
        "anchor_candidate": None,
        "evidence_spans": [_span(source, "Si llego a la cornisa")],
    }
    analysis = _interpretation(source, events, links=[link])
    resolutions = {
        "event_climb": _resolution(
            source, "event_climb", target="el muro"
        ),
        "event_enter": _resolution(
            source, "event_enter", target="la torre"
        ),
        "event_examine": _resolution(
            source, "event_examine", target="el cofre"
        ),
    }
    result = build_action_checkpoint(
        analysis,
        resolution_id=41,
        context_revision=9,
        source_text=source,
        active_character_id=7,
        reference_resolutions=resolutions,
    )
    return source, analysis, result.checkpoint


def test_action_graph_round_trips_with_source_and_interpretation_fingerprints():
    _, _, checkpoint = _basic_graph()

    restored = PlayerActionCheckpoint.from_json(checkpoint.to_json())

    assert restored == checkpoint
    assert restored.resolution_id == 41
    assert restored.context_revision == 9
    assert restored.source_sha256 == hashlib.sha256(
        b"Yo intento escalar el muro. Si llego a la cornisa, yo entro en la torre. "
        b"Luego yo examino el cofre."
    ).hexdigest()


def test_checkpoint_decoder_rejects_unknown_fields_and_malformed_digest():
    _, _, checkpoint = _basic_graph()
    payload = json.loads(checkpoint.to_json())
    payload["model_selected_action"] = "event_enter"
    with pytest.raises(ActionCheckpointValidationError):
        PlayerActionCheckpoint.from_payload(payload)

    payload = json.loads(checkpoint.to_json())
    payload["source_sha256"] = "not-a-sha256"
    with pytest.raises(ActionCheckpointValidationError):
        PlayerActionCheckpoint.from_payload(payload)


def test_only_first_action_is_selected_and_condition_waits_for_success():
    _, _, checkpoint = _basic_graph()

    selected = select_next_action(checkpoint)

    assert selected.status is ActionSelectionStatus.READY
    assert selected.candidate is not None
    assert selected.candidate.source_event_id == "event_climb"
    assert selected.candidate.workflow is GameplayWorkflow.MECHANICS
    assert next(
        item for item in selected.checkpoint.nodes
        if item.candidate.source_event_id == "event_enter"
    ).candidate.eligibility is GameplayActionEligibility.BLOCKED_BY_DEPENDENCY


def test_success_unlocks_condition_but_does_not_execute_later_independent_action():
    _, _, checkpoint = _basic_graph()
    checkpoint, _, _ = mark_action_started(checkpoint, "event_climb")
    checkpoint = mark_action_completed(
        checkpoint, "event_climb", ActionOutcome.SUCCESS
    )

    selected = select_next_action(checkpoint)

    assert selected.status is ActionSelectionStatus.READY
    assert selected.candidate is not None
    assert selected.candidate.source_event_id == "event_enter"
    assert selected.candidate.eligibility is GameplayActionEligibility.ELIGIBLE
    assert next(
        item for item in selected.checkpoint.nodes
        if item.candidate.source_event_id == "event_examine"
    ).state is ActionExecutionState.PENDING


def test_failure_never_unlocks_conditional_successor_and_independent_action_continues():
    _, _, checkpoint = _basic_graph()
    checkpoint, _, _ = mark_action_started(checkpoint, "event_climb")
    checkpoint = mark_action_completed(
        checkpoint, "event_climb", ActionOutcome.FAILURE
    )

    selected = select_next_action(checkpoint)
    dependent = next(
        item for item in selected.checkpoint.nodes
        if item.candidate.source_event_id == "event_enter"
    )

    assert selected.status is ActionSelectionStatus.READY
    assert selected.candidate is not None
    assert selected.candidate.source_event_id == "event_examine"
    assert dependent.state is ActionExecutionState.SKIPPED
    assert dependent.candidate.processing_state is GameplayProcessingState.BLOCKED


def test_technical_execution_failure_retries_with_the_same_idempotency_key():
    _, _, checkpoint = _basic_graph()
    checkpoint, first_key, resumed = mark_action_started(
        checkpoint, "event_climb"
    )
    assert not resumed
    checkpoint = mark_action_execution_failed(checkpoint, "event_climb")

    selected = select_next_action(checkpoint)
    checkpoint, retry_key, resumed = mark_action_started(
        selected.checkpoint, "event_climb"
    )

    assert resumed
    assert retry_key == first_key
    node = checkpoint.nodes[0]
    assert node.attempt_count == 2
    assert node.state is ActionExecutionState.IN_PROGRESS


@pytest.mark.parametrize(
    ("speaker_role", "quote", "polarity", "expected_reason"),
    [
        ("npc", "Yo intento abrir la puerta", "positive", GameplayActionReason.OUTSIDE_PLAYER_SCOPE),
        ("player", "Yo intento abrir la puerta", "negative", GameplayActionReason.NEGATED),
    ],
)
def test_npc_and_negated_events_are_never_actionable(
    speaker_role, quote, polarity, expected_reason
):
    source = "Yo intento abrir la puerta."
    event = _event(
        source,
        "event_open",
        "abrir",
        "Yo intento abrir la puerta",
        target="la puerta",
        polarity=polarity,
    )
    analysis = _interpretation(
        source,
        [event],
        speaker_role=speaker_role,
        quote=quote if speaker_role == "npc" else None,
    )
    built = build_action_checkpoint(
        analysis,
        resolution_id=44,
        context_revision=2,
        source_text=source,
        active_character_id=7,
        reference_resolutions={
            "event_open": _resolution(source, "event_open", target="la puerta")
        },
    )

    node = built.checkpoint.nodes[0]
    assert node.state is ActionExecutionState.SKIPPED
    assert node.candidate.reason is expected_reason


def test_event_inside_a_player_quote_is_not_activated_as_a_command():
    source = "Mara dice: «Yo abro la puerta»."
    act = {
        "local_id": "act_player",
        "force": "report",
        "speaker_role": "player",
        "speaker_mention": None,
        "addressee_mention": None,
        "quote_spans": [_span(source, "Yo abro la puerta")],
        "evidence_spans": [_span(source, source)],
    }
    event = _event(
        source,
        "event_open",
        "abro",
        "Yo abro la puerta",
        target="la puerta",
    )
    analysis = TurnInterpretationV3.from_payload(
        {
            "schema_version": 3,
            "utterance_acts": [act],
            "events": [event],
            "discourse_links": [],
            "world_facts": [],
            "clarification_candidates": [],
        },
        source_text=source,
    )
    built = build_action_checkpoint(
        analysis,
        resolution_id=45,
        context_revision=2,
        source_text=source,
        active_character_id=7,
        reference_resolutions={
            "event_open": _resolution(source, "event_open", target="la puerta")
        },
    )

    assert built.checkpoint.nodes[0].state is ActionExecutionState.SKIPPED


def test_planned_action_without_success_dependency_is_not_selected():
    source = "Yo entro en la torre."
    event = _event(
        source,
        "event_enter",
        "Entro",
        source,
        target="la torre",
        phase="planned",
        epistemic="hypothetical",
    )
    analysis = _interpretation(source, [event])
    built = build_action_checkpoint(
        analysis,
        resolution_id=46,
        context_revision=2,
        source_text=source,
        active_character_id=7,
        reference_resolutions={
            "event_enter": _resolution(source, "event_enter", target="la torre")
        },
    )

    assert built.checkpoint.nodes[0].state is ActionExecutionState.SKIPPED
    assert built.checkpoint.nodes[0].candidate.reason is GameplayActionReason.CONDITIONAL
    assert select_next_action(built.checkpoint).status is ActionSelectionStatus.EXHAUSTED


def test_unresolved_actor_pauses_and_clarification_preserves_other_nodes():
    source = "Yo intento abrir la puerta. Luego yo examino el escritorio."
    events = [
        _event(
            source, "event_open", "abrir", "Yo intento abrir la puerta",
            target="la puerta",
        ),
        _event(
            source, "event_examine", "examino", "yo examino el escritorio",
            family="perception", target="el escritorio",
        ),
    ]
    analysis = _interpretation(source, events)
    graph = build_action_checkpoint(
        analysis,
        resolution_id=47,
        context_revision=3,
        source_text=source,
        active_character_id=7,
        reference_resolutions={
            "event_examine": _resolution(
                source, "event_examine", target="el escritorio"
            )
        },
    ).checkpoint
    first = graph.nodes[0]
    second = graph.nodes[1]
    assert first.state is ActionExecutionState.AWAITING_INPUT

    selection = select_next_action(graph)
    assert selection.status is ActionSelectionStatus.NEEDS_CLARIFICATION
    assert selection.candidate is not None
    assert selection.candidate.source_event_id == "event_open"

    updated = replace(
        first.candidate,
        eligibility=GameplayActionEligibility.ELIGIBLE,
        reason=GameplayActionReason.ELIGIBLE,
        workflow=GameplayWorkflow.MECHANICS,
        unlock_condition=GameplayUnlockCondition.NONE,
        processing_state=GameplayProcessingState.PENDING,
        resolved_references=(
            GameplayResolvedReference(
                mention=SemanticMention("Yo"),
                category=GameplayResolvedReferenceKind.ENTITY,
                referent_id=7,
                name="Hero",
            ),
            GameplayResolvedReference(
                mention=SemanticMention(
                    "la puerta", kind_hint=SemanticObjectKind.LOCATION
                ),
                category=GameplayResolvedReferenceKind.ENTITY,
                referent_id=99,
                name="la puerta",
            ),
        ),
    )
    resumed = resume_after_clarification(graph, "event_open", updated)

    assert resumed.checkpoint.nodes[0].state is ActionExecutionState.PENDING
    assert resumed.checkpoint.nodes[1] == second
    assert resumed.affected_descendant_event_ids == ()


def test_clarification_reports_only_transitive_dependency_branch():
    source = (
        "Yo intento escalar el muro. "
        "Si llego a la cornisa, yo entro en la torre. "
        "Luego yo examino el cofre."
    )
    events = [
        _event(source, "event_climb", "escalar", "Yo intento escalar el muro"),
        _event(
            source, "event_enter", "entro", "yo entro en la torre",
            target="la torre", phase="planned", epistemic="hypothetical",
        ),
        _event(
            source, "event_examine", "examino", "yo examino el cofre",
            family="perception", target="el cofre",
        ),
    ]
    link = {
        "local_id": "link_condition",
        "source_ref": "event:event_enter",
        "target_ref": "event:event_climb",
        "link_type": "condition_on_success",
        "anchor_candidate": None,
        "evidence_spans": [_span(source, "Si llego a la cornisa")],
    }
    analysis = _interpretation(source, events, links=[link])
    graph = build_action_checkpoint(
        analysis,
        resolution_id=48,
        context_revision=3,
        source_text=source,
        active_character_id=7,
    ).checkpoint
    first = graph.nodes[0]
    updated = replace(
        first.candidate,
        eligibility=GameplayActionEligibility.ELIGIBLE,
        reason=GameplayActionReason.ELIGIBLE,
        workflow=GameplayWorkflow.MECHANICS,
        processing_state=GameplayProcessingState.PENDING,
        resolved_references=(
            GameplayResolvedReference(
                mention=SemanticMention("Yo"),
                category=GameplayResolvedReferenceKind.ENTITY,
                referent_id=7,
                name="Hero",
            ),
        ),
    )
    resumed = resume_after_clarification(graph, "event_climb", updated)

    assert resumed.affected_descendant_event_ids == ("event_enter",)
    assert resumed.checkpoint.nodes[1] == graph.nodes[1]
    assert resumed.checkpoint.nodes[2] == graph.nodes[2]


def test_conditional_link_with_forward_dependency_fails_closed():
    source = "Si yo entro en la torre, yo escalo el muro."
    events = [
        _event(
            source, "event_enter", "entro", "yo entro en la torre",
            target="la torre", phase="planned", epistemic="hypothetical",
        ),
        _event(
            source, "event_climb", "escalo", "yo escalo el muro",
            target="el muro", phase="attempted",
        ),
    ]
    link = {
        "local_id": "link_condition",
        "source_ref": "event:event_enter",
        "target_ref": "event:event_climb",
        "link_type": "condition_on_success",
        "anchor_candidate": None,
        "evidence_spans": [_span(source, "Si yo entro en la torre")],
    }
    analysis = _interpretation(source, events, links=[link])

    with pytest.raises(ActionSelectorError, match="must precede"):
        build_action_checkpoint(
            analysis,
            resolution_id=49,
            context_revision=2,
            source_text=source,
            active_character_id=7,
        )


def test_failed_prerequisite_skips_even_a_dependent_action_awaiting_clarification():
    _, _, checkpoint = _basic_graph()
    nodes = []
    for node in checkpoint.nodes:
        if node.candidate.source_event_id == "event_enter":
            candidate = replace(
                node.candidate,
                eligibility=GameplayActionEligibility.REQUIRES_CLARIFICATION,
                reason=GameplayActionReason.CLARIFICATION_REQUIRED,
                workflow=GameplayWorkflow.CLARIFICATION,
                unlock_condition=GameplayUnlockCondition.NONE,
                processing_state=GameplayProcessingState.AWAITING_INPUT,
            )
            node = replace(
                node,
                candidate=candidate,
                state=ActionExecutionState.AWAITING_INPUT,
                clarification_slots=("target",),
            )
        nodes.append(node)
    checkpoint = replace(checkpoint, nodes=tuple(nodes))
    checkpoint, _, _ = mark_action_started(checkpoint, "event_climb")
    checkpoint = mark_action_completed(
        checkpoint, "event_climb", ActionOutcome.FAILURE
    )

    selected = select_next_action(checkpoint)

    assert selected.status is ActionSelectionStatus.READY
    assert selected.candidate is not None
    assert selected.candidate.source_event_id == "event_examine"


def test_fact_validation_receipt_is_bound_to_exact_candidate_and_checkpointed():
    source = "Mara es hermana de Aldric."
    payload = {
        "schema_version": 3,
        "utterance_acts": [
            {
                "local_id": "act_assertion",
                "force": "assertion",
                "speaker_role": "player",
                "speaker_mention": None,
                "addressee_mention": None,
                "quote_spans": [],
                "evidence_spans": [_span(source, source)],
            }
        ],
        "events": [],
        "discourse_links": [],
        "world_facts": [
            {
                "local_id": "fact_sibling",
                "source_act_id": "act_assertion",
                "fact_kind": "relation",
                "subject": _mention("Mara"),
                "predicate_surface": "hermana",
                "object": _mention("Aldric"),
                "value_surface": None,
                "relation_family": "kinship",
                "normalized_relation_type": "kinship.sibling",
                "direction": "symmetric",
                "polarity": "positive",
                "epistemic_status": "asserted",
                "temporal_scope": "permanent",
                "attributed_source": None,
                "evidence_spans": [_span(source, source)],
            }
        ],
        "clarification_candidates": [],
    }
    interpretation = TurnInterpretationV3.from_payload(
        payload, source_text=source
    )
    fact = interpretation.world_facts[0]
    receipt = FactValidationReceipt(
        fact_local_id=fact.local_id,
        source_act_id=fact.source_act_id,
        candidate_sha256=fact_candidate_sha256(fact),
        candidate_json=fact_candidate_json(fact),
        state=FactValidationState.VALIDATED,
    )

    checkpoint = build_action_checkpoint(
        interpretation,
        resolution_id=50,
        context_revision=4,
        source_text=source,
        active_character_id=7,
    ).checkpoint
    checkpoint = record_fact_validation_receipts(
        checkpoint, interpretation, (receipt,)
    )
    restored = PlayerActionCheckpoint.from_json(checkpoint.to_json())

    assert restored.fact_validation_receipts == (receipt,)
    restored_fact = WorldFactCandidate.from_payload(
        json.loads(restored.fact_validation_receipts[0].candidate_json),
        source_text=source,
    )
    assert restored_fact == fact
    assert record_fact_validation_receipts(
        restored, interpretation, (receipt,)
    ) == restored
    stale_receipt = replace(receipt, candidate_sha256="0" * 64)
    with pytest.raises(ActionSelectorError, match="exact candidate"):
        build_action_checkpoint(
            interpretation,
            resolution_id=50,
            context_revision=4,
            source_text=source,
            active_character_id=7,
            fact_validation_receipts=(stale_receipt,),
        )


def test_selector_rejects_canonical_references_without_visibility_attestation():
    source = "Yo intento abrir la puerta."
    event = _event(
        source, "event_open", "abrir", source, target="la puerta"
    )
    analysis = _interpretation(source, [event])
    resolution = _resolution(source, "event_open", target="la puerta")
    resolution = replace(resolution, visibility_verified=False)

    with pytest.raises(ActionSelectorError, match="visibility verification"):
        build_action_checkpoint(
            analysis,
            resolution_id=51,
            context_revision=2,
            source_text=source,
            active_character_id=7,
            reference_resolutions={"event_open": resolution},
        )



def test_resolved_action_completion_is_idempotent_and_outcome_immutable():
    _, _, checkpoint = _basic_graph()
    checkpoint, _, _ = mark_action_started(checkpoint, "event_climb")
    checkpoint = mark_action_completed(
        checkpoint, "event_climb", ActionOutcome.SUCCESS
    )

    assert mark_action_completed(
        checkpoint, "event_climb", ActionOutcome.SUCCESS
    ) == checkpoint
    with pytest.raises(ActionSelectorError, match="immutable"):
        mark_action_completed(
            checkpoint, "event_climb", ActionOutcome.FAILURE
        )


def test_technical_failure_marker_is_idempotent():
    _, _, checkpoint = _basic_graph()
    checkpoint, _, _ = mark_action_started(checkpoint, "event_climb")
    failed = mark_action_execution_failed(checkpoint, "event_climb")

    assert mark_action_execution_failed(
        failed, "event_climb"
    ) == failed


def test_long_v3_event_ids_produce_valid_stable_action_ids():
    source = "Yo intento abrir la puerta."
    event_id = "event_abcdefghijklmnopqrstuvwxyz"
    event = _event(
        source, event_id, "abrir", source, target="la puerta"
    )
    analysis = _interpretation(source, [event])
    graph = build_action_checkpoint(
        analysis,
        resolution_id=52,
        context_revision=5,
        source_text=source,
        active_character_id=7,
        reference_resolutions={
            event_id: _resolution(
                source, event_id, target="la puerta"
            )
        },
    ).checkpoint

    assert len(graph.nodes[0].candidate.local_id) <= 32
    assert graph.nodes[0].candidate.local_id.startswith("action_")


def test_self_target_reference_is_not_duplicated_in_candidate():
    source = "Yo me observo."
    event = _event(
        source, "event_observe", "observo", source,
        family="perception", actor="Yo", target="me"
    )
    analysis = _interpretation(source, [event])
    actor_ref = GameplayResolvedReference(
        mention=SemanticMention("Yo"),
        category=GameplayResolvedReferenceKind.ENTITY,
        referent_id=7,
        name="Hero",
    )
    target_ref = GameplayResolvedReference(
        mention=SemanticMention("me"),
        category=GameplayResolvedReferenceKind.ENTITY,
        referent_id=7,
        name="Hero",
    )
    resolution = ActionReferenceResolution(
        actor_reference=actor_ref,
        visibility_verified=True,
        resolved_targets=(target_ref,),
    )
    graph = build_action_checkpoint(
        analysis,
        resolution_id=53,
        context_revision=5,
        source_text=source,
        active_character_id=7,
        reference_resolutions={"event_observe": resolution},
    ).checkpoint

    assert graph.nodes[0].candidate.resolved_references == (actor_ref,)
