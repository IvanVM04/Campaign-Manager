"""Deterministic eligibility policy for facts derived from v3.

A WorldFactCandidate is untrusted evidence, not a write instruction. This
module requires backend-resolved, visibility-attested endpoints and returns
bounded domain operations without calling an LLM or committing world state.
"""
from __future__ import annotations

import enum
import hashlib
import json
import unicodedata
from dataclasses import dataclass

from models.entity import Entity
from models.player_action_checkpoint import FactValidationReceipt, FactValidationState
from models.player_turn_interpretation_v3 import (
    EpistemicStatus,
    FactTemporalScope,
    RelationDirection,
    SpeakerRole,
    TurnInterpretationV3,
    UtteranceForce,
    WorldFactCandidate,
    WorldFactKind,
)
from models.relation import Relation
from models.semantic_frames import SemanticActionFamily, SemanticPolarity
from models.world_state import WorldState
from operations.turn_operations import TurnOperation
from operations.world_operations import (
    CreateRelationOperation,
    UpdateEntityOperation,
    UpdateRelationOperation,
)

_ALLOWED_RELATION_FAMILIES = frozenset({
    "kinship", "membership", "employment", "allegiance", "friendship",
    "hostility", "part_of", "knowledge", "obligation", "protection",
    "service", "spatial", "containment", "ownership", "possession",
})


class FactDecisionStatus(str, enum.Enum):
    ACCEPTED = "accepted"
    ALREADY_PRESENT = "already_present"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"


class FactDecisionReason(str, enum.Enum):
    ELIGIBLE = "eligible"
    ALREADY_PRESENT = "already_present"
    CANDIDATE_NOT_IN_INTERPRETATION = "candidate_not_in_interpretation"
    SOURCE_ACT_NOT_PLAYER_ASSERTION = "source_act_not_player_assertion"
    QUOTED_EVIDENCE = "quoted_evidence"
    ATTRIBUTED_OR_REPORTED = "attributed_or_reported"
    NON_PERSISTENT_EPISTEMIC_STATUS = "non_persistent_epistemic_status"
    NON_POSITIVE_POLARITY = "non_positive_polarity"
    NON_PERMANENT_TEMPORAL_SCOPE = "non_permanent_temporal_scope"
    SUBJECT_UNRESOLVED = "subject_unresolved"
    OBJECT_UNRESOLVED = "object_unresolved"
    VISIBILITY_UNVERIFIED = "visibility_unverified"
    INVALID_REFERENCE = "invalid_reference"
    REFERENCE_MISMATCH = "reference_mismatch"
    UNSUPPORTED_RELATION_FAMILY = "unsupported_relation_family"
    MISSING_NORMALIZED_RELATION = "missing_normalized_relation"
    TRANSFER_DOES_NOT_PROVE_RELATION = "transfer_does_not_prove_relation"
    RELATION_ID_COLLISION = "relation_id_collision"


@dataclass(frozen=True, slots=True)
class FactDecision:
    candidate: WorldFactCandidate
    status: FactDecisionStatus
    reason: FactDecisionReason
    operations: tuple[TurnOperation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, WorldFactCandidate):
            raise TypeError("candidate must be a WorldFactCandidate")
        if not isinstance(self.status, FactDecisionStatus):
            raise TypeError("status must be a FactDecisionStatus")
        if not isinstance(self.reason, FactDecisionReason):
            raise TypeError("reason must be a FactDecisionReason")
        if not isinstance(self.operations, tuple):
            raise TypeError("operations must be a tuple")
        if self.status is FactDecisionStatus.ACCEPTED and not self.operations:
            raise ValueError("accepted fact decisions require a world operation")
        if self.status is not FactDecisionStatus.ACCEPTED and self.operations:
            raise ValueError("non-accepted fact decisions cannot contain operations")

    def to_receipt(self) -> FactValidationReceipt:
        """Bind the backend policy result to the exact candidate snapshot."""
        payload = _candidate_json(self.candidate)
        state = (
            FactValidationState.VALIDATED
            if self.status in {
                FactDecisionStatus.ACCEPTED, FactDecisionStatus.ALREADY_PRESENT
            }
            else FactValidationState.REJECTED
            if self.status is FactDecisionStatus.REJECTED
            else FactValidationState.PENDING
        )
        return FactValidationReceipt(
            fact_local_id=self.candidate.local_id,
            source_act_id=self.candidate.source_act_id,
            candidate_sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            candidate_json=payload,
            state=state,
        )


def evaluate_world_fact(
    candidate: WorldFactCandidate,
    interpretation: TurnInterpretationV3,
    world: WorldState,
    *,
    subject_entity_id: int | None,
    subject_visibility_verified: bool,
    object_entity_id: int | None = None,
    object_visibility_verified: bool = False,
) -> FactDecision:
    """Evaluate one candidate and produce at most one deterministic operation.

    Only positive, permanent facts explicitly asserted/observed by the player
    are eligible. Quoted, attributed, reported, uncertain, hypothetical,
    negative and temporary claims abstain. IDs must come from trusted,
    visibility-aware resolution and match the literal mentions; names are
    never converted to IDs here.
    """
    if not isinstance(candidate, WorldFactCandidate):
        raise TypeError("candidate must be a WorldFactCandidate")
    if not isinstance(interpretation, TurnInterpretationV3):
        raise TypeError("interpretation must be a TurnInterpretationV3")
    if not isinstance(world, WorldState):
        raise TypeError("world must be a WorldState")
    if not isinstance(subject_visibility_verified, bool) or not isinstance(
        object_visibility_verified, bool
    ):
        raise TypeError("visibility attestations must be booleans")
    if candidate not in interpretation.world_facts:
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.CANDIDATE_NOT_IN_INTERPRETATION,
        )

    act = next(
        (item for item in interpretation.utterance_acts
         if item.local_id == candidate.source_act_id),
        None,
    )
    if (
        act is None
        or act.speaker_role is not SpeakerRole.PLAYER
        or act.force is not UtteranceForce.ASSERTION
    ):
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.SOURCE_ACT_NOT_PLAYER_ASSERTION,
        )
    if any(
        evidence.start < quote.end and quote.start < evidence.end
        for evidence in candidate.evidence_spans
        for quote in act.quote_spans
    ):
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.QUOTED_EVIDENCE,
        )
    if candidate.attributed_source is not None:
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.ATTRIBUTED_OR_REPORTED,
        )
    if candidate.epistemic_status not in {
        EpistemicStatus.ASSERTED, EpistemicStatus.OBSERVED
    }:
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.NON_PERSISTENT_EPISTEMIC_STATUS,
        )
    if candidate.polarity is not SemanticPolarity.POSITIVE:
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.NON_POSITIVE_POLARITY,
        )
    if candidate.temporal_scope is not FactTemporalScope.PERMANENT:
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.NON_PERMANENT_TEMPORAL_SCOPE,
        )

    if subject_entity_id is None:
        return _decision(
            candidate, FactDecisionStatus.NEEDS_CLARIFICATION,
            FactDecisionReason.SUBJECT_UNRESOLVED,
        )
    subject = _trusted_entity(
        world, subject_entity_id, candidate.subject.text,
        subject_visibility_verified,
    )
    if subject is None:
        reason = (
            FactDecisionReason.VISIBILITY_UNVERIFIED
            if not subject_visibility_verified
            else FactDecisionReason.INVALID_REFERENCE
        )
        if (
            isinstance(subject_entity_id, int)
            and not isinstance(subject_entity_id, bool)
            and subject_entity_id in world.entities
        ):
            reason = FactDecisionReason.REFERENCE_MISMATCH
        return _decision(candidate, FactDecisionStatus.REJECTED, reason)

    if candidate.fact_kind is WorldFactKind.ENTITY_ATTRIBUTE:
        if candidate.object is not None or candidate.value_surface is None:
            return _decision(
                candidate, FactDecisionStatus.REJECTED,
                FactDecisionReason.INVALID_REFERENCE,
            )
        note = (
            f"{candidate.predicate_surface.strip()}: "
            f"{candidate.value_surface.strip()}"
        )
        if note.casefold() in subject.notes.casefold():
            return _decision(
                candidate, FactDecisionStatus.ALREADY_PRESENT,
                FactDecisionReason.ALREADY_PRESENT,
            )
        operation = UpdateEntityOperation(
            entity_id=subject_entity_id,
            notes=f"{subject.notes.rstrip()}\n{note}".strip(),
        )
        return _decision(
            candidate, FactDecisionStatus.ACCEPTED,
            FactDecisionReason.ELIGIBLE, (operation,),
        )

    if (
        candidate.fact_kind is not WorldFactKind.RELATION
        or candidate.object is None
        or candidate.direction is None
    ):
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.INVALID_REFERENCE,
        )
    if object_entity_id is None:
        return _decision(
            candidate, FactDecisionStatus.NEEDS_CLARIFICATION,
            FactDecisionReason.OBJECT_UNRESOLVED,
        )
    target = _trusted_entity(
        world, object_entity_id, candidate.object.text,
        object_visibility_verified,
    )
    if target is None:
        reason = (
            FactDecisionReason.VISIBILITY_UNVERIFIED
            if not object_visibility_verified
            else FactDecisionReason.INVALID_REFERENCE
        )
        if (
            isinstance(object_entity_id, int)
            and not isinstance(object_entity_id, bool)
            and object_entity_id in world.entities
        ):
            reason = FactDecisionReason.REFERENCE_MISMATCH
        return _decision(candidate, FactDecisionStatus.REJECTED, reason)
    if subject_entity_id == object_entity_id:
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.INVALID_REFERENCE,
        )
    if (
        candidate.relation_family is None
        or candidate.relation_family.value not in _ALLOWED_RELATION_FAMILIES
    ):
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.UNSUPPORTED_RELATION_FAMILY,
        )
    if not candidate.normalized_relation_type:
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.MISSING_NORMALIZED_RELATION,
        )
    if (
        candidate.relation_family.value in {"ownership", "possession"}
        and any(
            event.source_act_id == candidate.source_act_id
            and event.family is SemanticActionFamily.TRANSFER
            for event in interpretation.events
        )
    ):
        return _decision(
            candidate, FactDecisionStatus.REJECTED,
            FactDecisionReason.TRANSFER_DOES_NOT_PROVE_RELATION,
        )

    left_id, right_id = subject_entity_id, object_entity_id
    if candidate.direction is RelationDirection.OBJECT_TO_SUBJECT:
        left_id, right_id = right_id, left_id
    elif candidate.direction is RelationDirection.SYMMETRIC:
        left_id, right_id = sorted((left_id, right_id))

    relation_type = candidate.normalized_relation_type
    relation_id = _relation_id(left_id, relation_type, right_id)
    metadata = {
        "source": "player_world_fact_policy_v1",
        "fact_local_id": candidate.local_id,
        "source_act_id": candidate.source_act_id,
        "candidate_sha256": _candidate_digest(candidate),
        "predicate_surface": candidate.predicate_surface,
        "relation_family": candidate.relation_family.value,
        "direction": candidate.direction.value,
        "epistemic_status": candidate.epistemic_status.value,
        "temporal_scope": candidate.temporal_scope.value,
        "evidence_spans": [span.to_dict() for span in candidate.evidence_spans],
    }
    existing = world.relations.get(relation_id)
    if existing is not None:
        if (
            existing.subject_id != left_id
            or existing.target_id != right_id
            or existing.relation_type != relation_type
        ):
            return _decision(
                candidate, FactDecisionStatus.REJECTED,
                FactDecisionReason.RELATION_ID_COLLISION,
            )
        if existing.active:
            return _decision(
                candidate, FactDecisionStatus.ALREADY_PRESENT,
                FactDecisionReason.ALREADY_PRESENT,
            )
        return _decision(
            candidate, FactDecisionStatus.ACCEPTED,
            FactDecisionReason.ELIGIBLE,
            (UpdateRelationOperation(
                relation_id=relation_id, metadata=metadata, active=True
            ),),
        )

    if any(
        isinstance(relation, Relation)
        and relation.active
        and relation.subject_id == left_id
        and relation.target_id == right_id
        and relation.relation_type == relation_type
        for relation in world.relations.values()
    ):
        return _decision(
            candidate, FactDecisionStatus.ALREADY_PRESENT,
            FactDecisionReason.ALREADY_PRESENT,
        )

    operation = CreateRelationOperation(
        relation_id=relation_id,
        subject_id=left_id,
        relation_type=relation_type,
        target_id=right_id,
        metadata=metadata,
    )
    return _decision(
        candidate, FactDecisionStatus.ACCEPTED,
        FactDecisionReason.ELIGIBLE, (operation,),
    )


def _trusted_entity(
    world: WorldState,
    entity_id: int,
    mention: str,
    visibility_verified: bool,
) -> Entity | None:
    if (
        not visibility_verified
        or isinstance(entity_id, bool)
        or not isinstance(entity_id, int)
    ):
        return None
    entity = world.entities.get(entity_id)
    if not isinstance(entity, Entity) or not entity.active:
        return None
    names = {entity.name, *entity.aliases}
    return entity if _fold(mention) in {_fold(name) for name in names} else None


def _fold(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", value).casefold().split()
    )


def _decision(
    candidate: WorldFactCandidate,
    status: FactDecisionStatus,
    reason: FactDecisionReason,
    operations: tuple[TurnOperation, ...] = (),
) -> FactDecision:
    return FactDecision(candidate, status, reason, operations)


def _candidate_json(candidate: WorldFactCandidate) -> str:
    return json.dumps(
        candidate.to_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _candidate_digest(candidate: WorldFactCandidate) -> str:
    return hashlib.sha256(
        _candidate_json(candidate).encode("utf-8")
    ).hexdigest()


def _relation_id(subject_id: int, relation_type: str, target_id: int) -> str:
    identity = f"{subject_id}:{relation_type}:{target_id}".encode()
    return "fact_" + hashlib.sha256(identity).hexdigest()[:32]
