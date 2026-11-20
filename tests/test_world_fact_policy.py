from dataclasses import replace

import pytest

from models.entity import Entity
from models.player_turn_interpretation_v3 import (
    ActionPhase, EpistemicStatus, EventFrame, FactTemporalScope,
    RelationDirection, SpeakerRole, TurnInterpretationV3, UtteranceAct,
    UtteranceForce, WorldFactCandidate, WorldFactKind, EvidenceSpan,
)
from models.relation import Relation
from models.semantic_frames import (
    SemanticActionFamily, SemanticMention, SemanticPolarity,
    SemanticRelationFamily,
)
from models.world_state import WorldState
from operations.world_operations import (
    CreateRelationOperation, UpdateEntityOperation, UpdateRelationOperation,
)
from services.turns.world_fact_policy import (
    FactDecisionReason, FactDecisionStatus, evaluate_world_fact,
)


def _span(source, text):
    start = source.index(text)
    return EvidenceSpan(start, start + len(text), text)


def _fact(
    source, *, fact_kind=WorldFactKind.RELATION, predicate="hermana",
    subject="Mara", object_="Aldric", value=None,
    family=SemanticRelationFamily.KINSHIP, normalized="kinship.sibling",
    direction=RelationDirection.SYMMETRIC,
    polarity=SemanticPolarity.POSITIVE, epistemic=EpistemicStatus.ASSERTED,
    temporal=FactTemporalScope.PERMANENT, attributed=None,
):
    return WorldFactCandidate(
        local_id="fact_relation" if fact_kind is WorldFactKind.RELATION else "fact_attribute",
        source_act_id="act_assertion", fact_kind=fact_kind,
        subject=SemanticMention(subject), predicate_surface=predicate,
        object=None if object_ is None else SemanticMention(object_),
        value_surface=value, relation_family=family,
        normalized_relation_type=normalized, direction=direction,
        polarity=polarity, epistemic_status=epistemic,
        temporal_scope=temporal,
        attributed_source=None if attributed is None else SemanticMention(attributed),
        evidence_spans=(_span(source, source),),
    )


def _interpretation(source, fact, *, force=UtteranceForce.ASSERTION,
                    speaker=SpeakerRole.PLAYER, quotes=(), events=()):
    act = UtteranceAct(
        local_id="act_assertion", force=force, speaker_role=speaker,
        evidence_spans=(_span(source, source),), quote_spans=tuple(quotes),
    )
    return TurnInterpretationV3(
        utterance_acts=(act,), events=tuple(events), discourse_links=(),
        world_facts=(fact,),
    )


def _world():
    return WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })


def _evaluate(fact, interpretation, world=None, **kwargs):
    return evaluate_world_fact(
        fact, interpretation, world or _world(),
        subject_entity_id=kwargs.pop("subject_entity_id", 1),
        subject_visibility_verified=kwargs.pop("subject_visibility_verified", True),
        object_entity_id=kwargs.pop("object_entity_id", 2),
        object_visibility_verified=kwargs.pop("object_visibility_verified", True),
        **kwargs,
    )


def test_explicit_permanent_kinship_creates_one_deterministic_relation():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    interpretation = _interpretation(source, fact)
    first = _evaluate(fact, interpretation)
    second = _evaluate(fact, interpretation)
    assert first.status is FactDecisionStatus.ACCEPTED
    assert first.reason is FactDecisionReason.ELIGIBLE
    assert len(first.operations) == 1
    assert isinstance(first.operations[0], CreateRelationOperation)
    assert (first.operations[0].subject_id, first.operations[0].target_id) == (1, 2)
    assert first.operations[0].relation_type == "kinship.sibling"
    assert first.operations[0].relation_id == second.operations[0].relation_id


def test_relation_direction_is_preserved():
    source = "Aldric protege a Mara."
    fact = _fact(
        source, predicate="protege", subject="Aldric", object_="Mara",
        family=SemanticRelationFamily.PROTECTION, normalized="protection.guardian",
        direction=RelationDirection.OBJECT_TO_SUBJECT,
    )
    result = _evaluate(
        fact, _interpretation(source, fact), subject_entity_id=2, object_entity_id=1
    )
    assert result.operations[0].subject_id == 1
    assert result.operations[0].target_id == 2


def test_observed_npc_attribute_is_appended_without_overwriting_existing_notes():
    source = "Aldric tiene una cicatriz nueva."
    fact = _fact(
        source, fact_kind=WorldFactKind.ENTITY_ATTRIBUTE, predicate="cicatriz",
        subject="Aldric", object_=None, value="nueva", family=None,
        normalized=None, direction=None, epistemic=EpistemicStatus.OBSERVED,
    )
    world = _world()
    world.entities[2].notes = "Conoce la posada."
    result = _evaluate(
        fact, _interpretation(source, fact), world, subject_entity_id=2
    )
    assert result.status is FactDecisionStatus.ACCEPTED
    operation = result.operations[0]
    assert isinstance(operation, UpdateEntityOperation)
    assert operation.entity_id == 2
    assert operation.notes == "Conoce la posada.\ncicatriz: nueva"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"epistemic_status": EpistemicStatus.REPORTED}, FactDecisionReason.NON_PERSISTENT_EPISTEMIC_STATUS),
        ({"epistemic_status": EpistemicStatus.RUMOR}, FactDecisionReason.NON_PERSISTENT_EPISTEMIC_STATUS),
        ({"epistemic_status": EpistemicStatus.HYPOTHETICAL}, FactDecisionReason.NON_PERSISTENT_EPISTEMIC_STATUS),
        ({"epistemic_status": EpistemicStatus.UNCERTAIN}, FactDecisionReason.NON_PERSISTENT_EPISTEMIC_STATUS),
        ({"polarity": SemanticPolarity.NEGATIVE}, FactDecisionReason.NON_POSITIVE_POLARITY),
        ({"polarity": SemanticPolarity.UNCERTAIN}, FactDecisionReason.NON_POSITIVE_POLARITY),
        ({"temporal_scope": FactTemporalScope.TEMPORARY}, FactDecisionReason.NON_PERMANENT_TEMPORAL_SCOPE),
        ({"temporal_scope": FactTemporalScope.UNKNOWN}, FactDecisionReason.NON_PERMANENT_TEMPORAL_SCOPE),
        ({"attributed_source": SemanticMention("un viajero")}, FactDecisionReason.ATTRIBUTED_OR_REPORTED),
    ],
)
def test_unstable_or_untrusted_fact_claims_never_produce_writes(changes, reason):
    source = "Mara es hermana de Aldric."
    fact = replace(_fact(source), **changes)
    result = _evaluate(fact, _interpretation(source, fact))
    assert result.status is FactDecisionStatus.REJECTED
    assert result.reason is reason
    assert result.operations == ()
    assert result.to_receipt().state.value == "rejected"


@pytest.mark.parametrize(
    ("force", "speaker"),
    [
        (UtteranceForce.REPORT, SpeakerRole.PLAYER),
        (UtteranceForce.ASSERTION, SpeakerRole.NPC),
        (UtteranceForce.HYPOTHESIS, SpeakerRole.PLAYER),
    ],
)
def test_non_player_assertion_cannot_authorize_fact_write(force, speaker):
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    result = _evaluate(
        fact, _interpretation(source, fact, force=force, speaker=speaker)
    )
    assert result.status is FactDecisionStatus.REJECTED
    assert result.reason is FactDecisionReason.SOURCE_ACT_NOT_PLAYER_ASSERTION


def test_quoted_evidence_cannot_be_persisted_as_player_fact():
    source = 'Mara dice: "Mara es hermana de Aldric".'
    fact = _fact(source)
    quote = _span(source, "Mara es hermana de Aldric")
    result = _evaluate(
        fact, _interpretation(source, fact, quotes=(quote,))
    )
    assert result.status is FactDecisionStatus.REJECTED
    assert result.reason is FactDecisionReason.QUOTED_EVIDENCE


def test_transfer_arguments_do_not_imply_ownership_or_possession():
    source = "Entrego Mara a Aldric; propiedad confirmada."
    fact = _fact(
        source, predicate="propiedad", family=SemanticRelationFamily.OWNERSHIP,
        normalized="ownership.owner", direction=RelationDirection.SUBJECT_TO_OBJECT,
    )
    event = EventFrame(
        local_id="event_transfer", source_act_id="act_assertion",
        predicate_surface="Entrego", family=SemanticActionFamily.TRANSFER,
        arguments=(), polarity=SemanticPolarity.POSITIVE,
        epistemic_status=EpistemicStatus.ASSERTED,
        action_phase=ActionPhase.ATTEMPTED, evidence_spans=(_span(source, source),),
    )
    result = _evaluate(fact, _interpretation(source, fact, events=(event,)))
    assert result.status is FactDecisionStatus.REJECTED
    assert result.reason is FactDecisionReason.TRANSFER_DOES_NOT_PROVE_RELATION
    assert result.operations == ()


def test_unresolved_or_invisible_endpoints_do_not_create_relations():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    interpretation = _interpretation(source, fact)
    unresolved = _evaluate(fact, interpretation, subject_entity_id=None)
    assert unresolved.status is FactDecisionStatus.NEEDS_CLARIFICATION
    assert unresolved.reason is FactDecisionReason.SUBJECT_UNRESOLVED
    assert unresolved.to_receipt().state.value == "pending"
    invisible = _evaluate(fact, interpretation, subject_visibility_verified=False)
    assert invisible.status is FactDecisionStatus.REJECTED
    assert invisible.reason is FactDecisionReason.VISIBILITY_UNVERIFIED
    unresolved_object = _evaluate(fact, interpretation, object_entity_id=None)
    assert unresolved_object.status is FactDecisionStatus.NEEDS_CLARIFICATION
    assert unresolved_object.reason is FactDecisionReason.OBJECT_UNRESOLVED


def test_reference_id_must_match_the_literal_mention():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    result = _evaluate(
        fact, _interpretation(source, fact), subject_entity_id=2
    )
    assert result.status is FactDecisionStatus.REJECTED
    assert result.reason is FactDecisionReason.REFERENCE_MISMATCH


def test_duplicate_relation_is_idempotently_reported_without_second_write():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    interpretation = _interpretation(source, fact)
    operation = _evaluate(fact, interpretation).operations[0]
    world = _world()
    world.relations[operation.relation_id] = Relation(
        id=operation.relation_id, subject_id=operation.subject_id,
        relation_type=operation.relation_type, target_id=operation.target_id,
        metadata=operation.metadata, active=True,
    )
    result = _evaluate(fact, interpretation, world)
    assert result.status is FactDecisionStatus.ALREADY_PRESENT
    assert result.operations == ()
    assert result.to_receipt().state.value == "validated"


def test_inactive_deterministic_relation_is_reactivated_not_duplicated():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    interpretation = _interpretation(source, fact)
    operation = _evaluate(fact, interpretation).operations[0]
    world = _world()
    world.relations[operation.relation_id] = Relation(
        id=operation.relation_id, subject_id=operation.subject_id,
        relation_type=operation.relation_type, target_id=operation.target_id,
        active=False,
    )
    result = _evaluate(fact, interpretation, world)
    assert result.status is FactDecisionStatus.ACCEPTED
    assert isinstance(result.operations[0], UpdateRelationOperation)
    assert result.operations[0].active is True


def test_fact_not_part_of_exact_interpretation_is_rejected():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    other = _fact(source, normalized="kinship.parent")
    result = _evaluate(fact, _interpretation(source, other))
    assert result.status is FactDecisionStatus.REJECTED
    assert result.reason is FactDecisionReason.CANDIDATE_NOT_IN_INTERPRETATION


def test_unknown_relation_family_or_missing_normalization_is_rejected():
    source = "Mara conoce a Aldric."
    unknown = _fact(
        source, predicate="conoce", family=SemanticRelationFamily.UNKNOWN,
        normalized="knowledge.knows",
    )
    result = _evaluate(unknown, _interpretation(source, unknown))
    assert result.reason is FactDecisionReason.UNSUPPORTED_RELATION_FAMILY
    missing = _fact(
        source, predicate="conoce", family=SemanticRelationFamily.KNOWLEDGE,
        normalized=None,
    )
    result = _evaluate(missing, _interpretation(source, missing))
    assert result.reason is FactDecisionReason.MISSING_NORMALIZED_RELATION
