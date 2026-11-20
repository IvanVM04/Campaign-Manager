from dataclasses import replace

import pytest

from models.entity import Entity
from models.player_turn_interpretation_v3 import (
    ActionPhase,
    EpistemicStatus,
    EventFrame,
    EvidenceSpan,
    FactTemporalScope,
    RelationDirection,
    SpeakerRole,
    TurnInterpretationV3,
    UtteranceAct,
    UtteranceForce,
    WorldFactCandidate,
    WorldFactKind,
)
from models.relation import Relation
from models.resolved_conversation_reference import ResolvedConversationReference
from models.semantic_frames import (
    SemanticActionFamily,
    SemanticMention,
    SemanticPolarity,
    SemanticRelationFamily,
)
from models.world_state import WorldState
from operations.world_operations import (
    CreateRelationOperation,
    UpdateEntityOperation,
    UpdateRelationOperation,
)
from services.turns.world_fact_policy import (
    FactDecisionReason,
    FactDecisionStatus,
    FactEndpointResolution,
    evaluate_world_fact,
    evaluate_world_facts,
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


def _resolved_reference(world, mention, entity_id):
    if entity_id is None:
        return None
    entity = world.entities[entity_id]
    return ResolvedConversationReference(
        mention=mention,
        entity_id=entity_id,
        entity_name=entity.name,
        match_kind="test",
    )


def _evaluate(fact, interpretation, world=None, **kwargs):
    world = world or _world()
    subject_id = kwargs.pop("subject_entity_id", 1)
    object_id = kwargs.pop("object_entity_id", 2)
    subject_mention = kwargs.pop("subject_reference_mention", fact.subject.text)
    object_mention = kwargs.pop(
        "object_reference_mention",
        fact.object.text if fact.object is not None else "",
    )
    return evaluate_world_fact(
        fact,
        interpretation,
        world,
        subject_reference=_resolved_reference(world, subject_mention, subject_id),
        object_reference=(
            _resolved_reference(world, object_mention, object_id)
            if fact.object is not None
            else None
        ),
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
    source = "Entrego Mara a Aldric."
    fact = _fact(
        source, predicate="Entrego", family=SemanticRelationFamily.OWNERSHIP,
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


def test_explicit_ownership_clause_separate_from_transfer_can_be_persisted():
    source = "Entrego Llave a Mara; Llave pertenece a Mara."
    fact = _fact(
        source, predicate="pertenece", subject="Llave", object_="Mara",
        family=SemanticRelationFamily.OWNERSHIP, normalized="ownership.owner",
        direction=RelationDirection.SUBJECT_TO_OBJECT,
    )
    fact = replace(
        fact,
        evidence_spans=(
            _span(source, "Llave"),
            _span(source, "Mara"),
            _span(source, "pertenece"),
        ),
    )
    event = EventFrame(
        local_id="event_transfer", source_act_id="act_assertion",
        predicate_surface="Entrego", family=SemanticActionFamily.TRANSFER,
        arguments=(), polarity=SemanticPolarity.POSITIVE,
        epistemic_status=EpistemicStatus.ASSERTED,
        action_phase=ActionPhase.ATTEMPTED,
        evidence_spans=(_span(source, "Entrego Llave a Mara"),),
    )
    world = _world()
    world.entities[3] = Entity(id=3, name="Llave", entity_type="item")

    result = _evaluate(
        fact,
        _interpretation(source, fact, events=(event,)),
        world,
        subject_entity_id=3,
        object_entity_id=1,
    )

    assert result.status is FactDecisionStatus.ACCEPTED
    assert isinstance(result.operations[0], CreateRelationOperation)
    assert result.operations[0].subject_id == 3
    assert result.operations[0].target_id == 1


def test_unresolved_or_mismatched_endpoints_do_not_create_relations():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    interpretation = _interpretation(source, fact)
    unresolved = _evaluate(fact, interpretation, subject_entity_id=None)
    assert unresolved.status is FactDecisionStatus.NEEDS_CLARIFICATION
    assert unresolved.reason is FactDecisionReason.SUBJECT_UNRESOLVED
    assert unresolved.to_receipt().state.value == "pending"
    mismatched = _evaluate(
        fact, interpretation, subject_reference_mention="Aldric"
    )
    assert mismatched.status is FactDecisionStatus.REJECTED
    assert mismatched.reason is FactDecisionReason.REFERENCE_MISMATCH
    unresolved_object = _evaluate(fact, interpretation, object_entity_id=None)
    assert unresolved_object.status is FactDecisionStatus.NEEDS_CLARIFICATION
    assert unresolved_object.reason is FactDecisionReason.OBJECT_UNRESOLVED


def test_reference_mention_must_match_the_exact_candidate_endpoint():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    result = _evaluate(
        fact, _interpretation(source, fact),
        subject_reference_mention="Aldric",
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



def test_attributed_fact_is_not_persisted_without_source_authority():
    source = "Según un viajero, Mara es hermana de Aldric."
    fact = _fact(source, attributed="un viajero")
    result = _evaluate(fact, _interpretation(source, fact))
    assert result.status is FactDecisionStatus.REJECTED
    assert result.reason is FactDecisionReason.ATTRIBUTED_OR_REPORTED
    assert result.operations == ()



def test_fact_evidence_must_be_contained_in_its_source_act():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    act = UtteranceAct(
        local_id="act_assertion",
        force=UtteranceForce.ASSERTION,
        speaker_role=SpeakerRole.PLAYER,
        evidence_spans=(_span(source, "Mara"),),
    )
    interpretation = TurnInterpretationV3(
        utterance_acts=(act,),
        events=(),
        discourse_links=(),
        world_facts=(fact,),
    )

    result = _evaluate(fact, interpretation)

    assert result.status is FactDecisionStatus.REJECTED
    assert result.reason is FactDecisionReason.FACT_EVIDENCE_OUTSIDE_SOURCE_ACT
    assert result.operations == ()



def test_fact_candidates_are_evaluated_independently_in_source_order():
    source = "Mara es hermana de Aldric."
    accepted = _fact(source)
    rejected = replace(
        accepted,
        local_id="fact_rumour",
        epistemic_status=EpistemicStatus.RUMOR,
    )
    interpretation = TurnInterpretationV3(
        utterance_acts=_interpretation(source, accepted).utterance_acts,
        events=(),
        discourse_links=(),
        world_facts=(accepted, rejected),
    )
    world = _world()
    resolutions = {
        accepted.local_id: FactEndpointResolution(
            subject_reference=_resolved_reference(world, "Mara", 1),
            object_reference=_resolved_reference(world, "Aldric", 2),
        ),
    }

    decisions = evaluate_world_facts(interpretation, world, resolutions)

    assert [item.candidate.local_id for item in decisions] == [
        "fact_relation",
        "fact_rumour",
    ]
    assert decisions[0].status is FactDecisionStatus.ACCEPTED
    assert decisions[0].operations
    assert decisions[1].status is FactDecisionStatus.REJECTED
    assert decisions[1].operations == ()



def test_policy_reports_attribute_already_present_without_duplicate_write():
    source = "Aldric tiene una cicatriz nueva."
    fact = _fact(
        source, fact_kind=WorldFactKind.ENTITY_ATTRIBUTE, predicate="cicatriz",
        subject="Aldric", object_=None, value="nueva", family=None,
        normalized=None, direction=None, epistemic=EpistemicStatus.OBSERVED,
    )
    world = _world()
    world.entities[2].notes = "Conoce la posada.\ncicatriz: nueva"
    result = _evaluate(
        fact, _interpretation(source, fact), world, subject_entity_id=2
    )
    assert result.status is FactDecisionStatus.ALREADY_PRESENT
    assert result.operations == ()


def test_inactive_or_renamed_subject_reference_is_rejected():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    world = _world()
    world.entities[1].active = False
    result = _evaluate(fact, _interpretation(source, fact), world)
    assert result.status is FactDecisionStatus.REJECTED
    assert result.reason is FactDecisionReason.REFERENCE_MISMATCH


def test_same_entity_cannot_form_a_relation_with_itself():
    source = "Mara es hermana de Mara."
    fact = _fact(source, object_="Mara")
    result = _evaluate(
        fact, _interpretation(source, fact),
        subject_entity_id=1, object_entity_id=1,
    )
    assert result.status is FactDecisionStatus.REJECTED
    assert result.reason is FactDecisionReason.INVALID_REFERENCE


def test_relation_id_collision_is_rejected():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    interpretation = _interpretation(source, fact)
    operation = _evaluate(fact, interpretation).operations[0]
    world = _world()
    world.relations[operation.relation_id] = Relation(
        id=operation.relation_id, subject_id=999,
        relation_type=operation.relation_type, target_id=operation.target_id,
        active=True,
    )
    result = _evaluate(fact, interpretation, world)
    assert result.status is FactDecisionStatus.REJECTED
    assert result.reason is FactDecisionReason.RELATION_ID_COLLISION


def test_matching_active_relation_under_legacy_id_is_idempotent():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    world = _world()
    world.relations["legacy-relation"] = Relation(
        id="legacy-relation", subject_id=1,
        relation_type="kinship.sibling", target_id=2, active=True,
    )
    result = _evaluate(fact, _interpretation(source, fact), world)
    assert result.status is FactDecisionStatus.ALREADY_PRESENT
    assert result.operations == ()


def test_fact_endpoint_resolution_rejects_untrusted_values():
    with pytest.raises(TypeError):
        FactEndpointResolution(subject_reference=object())


def test_fact_decision_rejects_invalid_status_and_operations():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    with pytest.raises(TypeError):
        FactDecision(fact, "accepted", FactDecisionReason.ELIGIBLE)
    with pytest.raises(ValueError):
        FactDecision(fact, FactDecisionStatus.ACCEPTED, FactDecisionReason.ELIGIBLE)
    operation = _evaluate(fact, _interpretation(source, fact)).operations[0]
    with pytest.raises(ValueError):
        FactDecision(
            fact, FactDecisionStatus.REJECTED,
            FactDecisionReason.INVALID_REFERENCE, (operation,),
        )


def test_evaluate_world_facts_validates_resolution_mapping():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    interpretation = _interpretation(source, fact)
    world = _world()
    with pytest.raises(TypeError):
        evaluate_world_facts(interpretation, world, [])
    with pytest.raises(TypeError):
        evaluate_world_facts(interpretation, world, {"fact_relation": object()})
    with pytest.raises(TypeError):
        evaluate_world_facts(interpretation, world, {1: FactEndpointResolution()})


def test_policy_rejects_invalid_runtime_inputs():
    source = "Mara es hermana de Aldric."
    fact = _fact(source)
    interpretation = _interpretation(source, fact)
    world = _world()
    with pytest.raises(TypeError):
        evaluate_world_fact(object(), interpretation, world, subject_reference=None)
    with pytest.raises(TypeError):
        evaluate_world_fact(fact, object(), world, subject_reference=None)
    with pytest.raises(TypeError):
        evaluate_world_fact(fact, interpretation, object(), subject_reference=None)
