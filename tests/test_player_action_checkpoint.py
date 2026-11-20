import hashlib
import json
from dataclasses import replace

import pytest

from models.player_action_checkpoint import (
    ActionCheckpointNode,
    ActionCheckpointValidationError,
    ActionExecutionState,
    ActionOutcome,
    FactValidationReceipt,
    FactValidationState,
    PlayerActionCheckpoint,
)
from models.player_turn_interpretation_v3 import (
    GameplayActionCandidate,
    GameplayActionEligibility,
    GameplayActionReason,
    GameplayProcessingState,
    GameplayUnlockCondition,
    GameplayWorkflow,
)
from models.semantic_frames import SemanticMention


def _candidate(
    *,
    local_id="action_open",
    event_id="event_open",
    eligibility=GameplayActionEligibility.ELIGIBLE,
    reason=GameplayActionReason.ELIGIBLE,
    workflow=GameplayWorkflow.MECHANICS,
    unlock=GameplayUnlockCondition.NONE,
    processing=GameplayProcessingState.PENDING,
    dependencies=(),
    targets=("la puerta",),
):
    return GameplayActionCandidate(
        local_id=local_id,
        source_event_id=event_id,
        actor=SemanticMention("Yo"),
        action_type="interaction",
        eligibility=eligibility,
        reason=reason,
        workflow=workflow,
        unlock_condition=unlock,
        processing_state=processing,
        target_mentions=tuple(SemanticMention(item) for item in targets),
        dependency_event_ids=dependencies,
    )


def _node(
    candidate=None,
    *,
    order=0,
    state=ActionExecutionState.PENDING,
    key="a" * 64,
    attempts=0,
    outcome=None,
    slots=(),
    **overrides,
):
    values = {
        "candidate": candidate or _candidate(),
        "source_order": order,
        "state": state,
        "execution_key": key,
        "attempt_count": attempts,
        "outcome": outcome,
        "clarification_slots": slots,
    }
    values.update(overrides)
    return ActionCheckpointNode(**values)


def _checkpoint(*nodes, receipts=()):
    return PlayerActionCheckpoint(
        resolution_id=7,
        context_revision=3,
        source_sha256="b" * 64,
        interpretation_sha256="c" * 64,
        nodes=tuple(nodes),
        fact_validation_receipts=tuple(receipts),
    )


def _receipt(*, state=FactValidationState.PENDING, candidate=None):
    candidate = candidate or {
        "local_id": "fact_sibling",
        "source_act_id": "act_assertion",
        "fact_kind": "relation",
        "subject": {"text": "Mara", "kind_hint": "character"},
        "predicate_surface": "hermana",
        "object": {"text": "Aldric", "kind_hint": "character"},
        "value_surface": None,
        "relation_family": "kinship",
        "normalized_relation_type": "kinship.sibling",
        "direction": "symmetric",
        "polarity": "positive",
        "epistemic_status": "asserted",
        "temporal_scope": "permanent",
        "attributed_source": None,
        "evidence_spans": [{
            "start": 0,
            "end": 7,
            "text": "Mara es",
            "source": "current_utterance",
        }],
    }
    serialized = json.dumps(
        candidate,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return FactValidationReceipt(
        fact_local_id="fact_sibling",
        source_act_id="act_assertion",
        candidate_sha256=hashlib.sha256(serialized.encode()).hexdigest(),
        candidate_json=serialized,
        state=state,
    )


def test_fact_validation_receipt_round_trips_and_preserves_canonical_snapshot():
    receipt = _receipt()
    restored = FactValidationReceipt(
        fact_local_id=receipt.fact_local_id,
        source_act_id=receipt.source_act_id,
        candidate_sha256=receipt.candidate_sha256,
        candidate_json=receipt.candidate_json,
        state=receipt.state,
    )
    assert restored == receipt
    assert restored.to_dict()["candidate_json"] == receipt.candidate_json


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"fact_local_id": "bad"}, ValueError),
        ({"source_act_id": "bad"}, ValueError),
        ({"candidate_sha256": "bad"}, ValueError),
        ({"candidate_json": 1}, TypeError),
        ({"candidate_json": "{"}, ValueError),
        ({"candidate_json": "[]"}, TypeError),
        ({"state": "pending"}, TypeError),
    ],
)
def test_fact_validation_receipt_rejects_invalid_fields(overrides, error):
    receipt = _receipt()
    values = {
        "fact_local_id": receipt.fact_local_id,
        "source_act_id": receipt.source_act_id,
        "candidate_sha256": receipt.candidate_sha256,
        "candidate_json": receipt.candidate_json,
        "state": receipt.state,
    }
    values.update(overrides)
    with pytest.raises(error):
        FactValidationReceipt(**values)


def test_fact_validation_receipt_rejects_wrong_shape_identity_canonicalization_and_digest():
    receipt = _receipt()
    with pytest.raises(ValueError, match="contract"):
        _receipt(candidate={"unexpected": True})

    wrong_identity = json.loads(receipt.candidate_json)
    wrong_identity["local_id"] = "fact_other"
    with pytest.raises(ValueError, match="identity"):
        _receipt(candidate=wrong_identity)

    with pytest.raises(ValueError, match="canonical JSON"):
        FactValidationReceipt(
            fact_local_id=receipt.fact_local_id,
            source_act_id=receipt.source_act_id,
            candidate_sha256=receipt.candidate_sha256,
            candidate_json=json.dumps(json.loads(receipt.candidate_json)),
            state=receipt.state,
        )

    with pytest.raises(ValueError, match="does not match"):
        FactValidationReceipt(
            fact_local_id=receipt.fact_local_id,
            source_act_id=receipt.source_act_id,
            candidate_sha256="0" * 64,
            candidate_json=receipt.candidate_json,
            state=receipt.state,
        )


def test_fact_validation_receipt_enforces_serialized_size():
    with pytest.raises(ValueError, match="byte budget"):
        FactValidationReceipt(
            fact_local_id="fact_sibling",
            source_act_id="act_assertion",
            candidate_sha256="0" * 64,
            candidate_json="x" * 16_385,
            state=FactValidationState.PENDING,
        )


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"source_order": True}, TypeError, "source_order"),
        ({"source_order": -1}, ValueError, "source_order"),
        ({"execution_key": "bad"}, ValueError, "execution_key"),
        ({"attempt_count": True}, TypeError, "attempt_count"),
        ({"attempt_count": -1}, ValueError, "attempt_count"),
        ({"outcome": "success"}, TypeError, "outcome"),
        ({"clarification_slots": ["target"]}, TypeError, "tuple"),
        ({"clarification_slots": ("target", "target")}, ValueError, "unique"),
        ({"clarification_slots": ("other",)}, ValueError, "unsupported"),
        ({"clarification_slots": ("actor", "target", "action", "sequence", "reference", "extra")}, ValueError, "five"),
    ],
)
def test_action_checkpoint_node_rejects_invalid_fields(kwargs, error, message):
    with pytest.raises(error, match=message):
        _node(**kwargs)


def test_action_checkpoint_node_requires_state_outcome_attempt_and_slots():
    with pytest.raises(ValueError, match="authoritative outcome"):
        _node(
            candidate=_candidate(processing=GameplayProcessingState.RESOLVED),
            state=ActionExecutionState.RESOLVED,
        )

    with pytest.raises(ValueError, match="only resolved"):
        _node(outcome=ActionOutcome.SUCCESS)

    with pytest.raises(ValueError, match="attempt count"):
        _node(
            candidate=_candidate(
                processing=GameplayProcessingState.ADJUDICATING
            ),
            state=ActionExecutionState.IN_PROGRESS,
        )

    with pytest.raises(ValueError, match="missing slots"):
        _node(
            candidate=_candidate(
                eligibility=GameplayActionEligibility.REQUIRES_CLARIFICATION,
                reason=GameplayActionReason.CLARIFICATION_REQUIRED,
                workflow=GameplayWorkflow.CLARIFICATION,
                processing=GameplayProcessingState.AWAITING_INPUT,
            ),
            state=ActionExecutionState.AWAITING_INPUT,
        )


def test_checkpoint_rejects_bad_identity_schema_and_duplicate_node_keys():
    with pytest.raises(ValueError, match="resolution_id"):
        replace(_checkpoint(), resolution_id=True)
    with pytest.raises(ValueError, match="context_revision"):
        replace(_checkpoint(), context_revision=0)
    with pytest.raises(ValueError, match="schema_version"):
        replace(_checkpoint(), schema_version=4)
    with pytest.raises(ValueError, match="unique"):
        _checkpoint(_node(), _node(order=1, key="d" * 64))
    with pytest.raises(ValueError, match="execution keys"):
        _checkpoint(
            _node(),
            _node(
                _candidate(local_id="action_second", event_id="event_second"),
                order=1,
            ),
        )


def test_checkpoint_rejects_missing_and_forward_dependencies():
    dependent = _candidate(
        local_id="action_enter",
        event_id="event_enter",
        eligibility=GameplayActionEligibility.BLOCKED_BY_DEPENDENCY,
        reason=GameplayActionReason.DEPENDENCY_PENDING,
        unlock=GameplayUnlockCondition.DEPENDENCY_SUCCESS,
        dependencies=("event_open",),
    )
    with pytest.raises(ValueError, match="must reference"):
        _checkpoint(_node(dependent))

    later_prerequisite = _node(
        _candidate(),
        order=1,
        key="b" * 64,
    )
    earlier_dependent = _node(
        dependent,
        order=0,
        key="c" * 64,
    )
    with pytest.raises(ValueError, match="precede"):
        _checkpoint(earlier_dependent, later_prerequisite)


def test_checkpoint_codec_rejects_unknown_malformed_and_oversized_payloads():
    checkpoint = _checkpoint(_node())
    payload = checkpoint.to_dict()
    payload["unexpected"] = True
    with pytest.raises(ActionCheckpointValidationError):
        PlayerActionCheckpoint.from_payload(payload)

    with pytest.raises(ActionCheckpointValidationError):
        PlayerActionCheckpoint.from_payload({
            **checkpoint.to_dict(),
            "nodes": "not-an-array",
        })

    with pytest.raises(ActionCheckpointValidationError):
        PlayerActionCheckpoint.from_json("{")

    with pytest.raises(ActionCheckpointValidationError):
        PlayerActionCheckpoint.from_json(None)

    with pytest.raises(ActionCheckpointValidationError):
        PlayerActionCheckpoint.from_json(" " * 131_073)


def test_checkpoint_progress_accepts_forward_execution():
    pending = _node()
    previous = _checkpoint(pending)
    started = _node(
        replace(
            pending.candidate,
            processing_state=GameplayProcessingState.ADJUDICATING,
        ),
        state=ActionExecutionState.IN_PROGRESS,
        attempts=1,
    )
    _checkpoint(started).validate_progress_from(previous)


def test_checkpoint_progress_rejects_dropped_reset_and_rebound_nodes():
    pending = _node()
    previous = _checkpoint(pending)
    with pytest.raises(ValueError, match="drop action nodes"):
        _checkpoint().validate_progress_from(previous)

    started = _node(
        replace(
            pending.candidate,
            processing_state=GameplayProcessingState.ADJUDICATING,
        ),
        state=ActionExecutionState.IN_PROGRESS,
        attempts=1,
    )
    with pytest.raises(ValueError, match="move backwards"):
        previous.validate_progress_from(_checkpoint(started))

    rebound = _node(
        replace(pending.candidate, actor=SemanticMention("Mara"))
    )
    with pytest.raises(ValueError, match="identity cannot change"):
        _checkpoint(rebound).validate_progress_from(previous)


def test_checkpoint_progress_rejects_non_monotonic_attempts_and_terminal_edits():
    pending = _node()
    previous = _checkpoint(pending)
    extra_attempt = _node(
        replace(
            pending.candidate,
            processing_state=GameplayProcessingState.ADJUDICATING,
        ),
        state=ActionExecutionState.IN_PROGRESS,
        attempts=2,
    )
    with pytest.raises(ValueError, match="attempt count"):
        _checkpoint(extra_attempt).validate_progress_from(previous)

    resolved = _node(
        replace(
            pending.candidate,
            processing_state=GameplayProcessingState.RESOLVED,
        ),
        state=ActionExecutionState.RESOLVED,
        attempts=1,
        outcome=ActionOutcome.SUCCESS,
    )
    terminal = _checkpoint(resolved)
    edited = replace(resolved, outcome=ActionOutcome.FAILURE)
    with pytest.raises(ValueError, match="terminal checkpoint action"):
        _checkpoint(edited).validate_progress_from(terminal)


def test_checkpoint_progress_preserves_final_fact_validation_receipts():
    receipt = _receipt()
    previous = _checkpoint(receipts=(receipt,))
    with pytest.raises(ValueError, match="drop fact validation receipts"):
        _checkpoint().validate_progress_from(previous)

    rejected = replace(receipt, state=FactValidationState.REJECTED)
    _checkpoint(receipts=(rejected,)).validate_progress_from(previous)

    with pytest.raises(ValueError, match="final fact validation receipt"):
        previous.validate_progress_from(_checkpoint(receipts=(rejected,)))


def test_checkpoint_codec_round_trips_canonical_json_with_fact_receipts():
    checkpoint = _checkpoint(_node(), receipts=(_receipt(),))

    serialized = checkpoint.to_json()
    restored = PlayerActionCheckpoint.from_json(serialized)

    assert restored == checkpoint
    assert restored.to_json() == serialized


def test_checkpoint_codec_rejects_malformed_nested_candidate_and_receipt():
    checkpoint = _checkpoint(_node())
    payload = checkpoint.to_dict()
    payload["nodes"][0]["candidate"]["target_mentions"] = "not-an-array"

    with pytest.raises(ActionCheckpointValidationError):
        PlayerActionCheckpoint.from_payload(payload)

    payload = checkpoint.to_dict()
    payload["fact_validation_receipts"] = "not-an-array"

    with pytest.raises(ActionCheckpointValidationError):
        PlayerActionCheckpoint.from_payload(payload)
