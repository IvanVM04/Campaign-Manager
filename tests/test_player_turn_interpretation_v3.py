import json
from dataclasses import FrozenInstanceError

import pytest

from models.player_turn_interpretation_v3 import (
    ActionPhase,
    DiscourseLinkType,
    EpistemicStatus,
    EvidenceSpan,
    FactTemporalScope,
    GameplayActionCandidate,
    GameplayActionEligibility,
    GameplayActionReason,
    GameplayProcessingState,
    GameplayResolvedReference,
    GameplayResolvedReferenceKind,
    GameplayUnlockCondition,
    GameplayWorkflow,
    RelationDirection,
    SpeakerRole,
    TurnInterpretationV3,
    TurnInterpretationV3ValidationError,
    UtteranceForce,
)
from models.semantic_frames import (
    SemanticMention,
    SemanticObjectKind,
    SemanticPolarity,
)


def _span(source, text):
    start = source.index(text)
    return {
        "start": start,
        "end": start + len(text),
        "text": text,
        "source": "current_utterance",
    }


def _mention(text, kind="character"):
    return {"text": text, "kind_hint": kind}


def _payload(source=None):
    source = source or (
        "Aldric me advierte: «No cruces el puente». "
        "Mara es hermana de Aldric."
    )
    warning = "Aldric me advierte: «No cruces el puente»."
    quote = "No cruces el puente"
    relation = "Mara es hermana de Aldric."
    return {
        "schema_version": 3,
        "utterance_acts": [
            {
                "local_id": "act_warning",
                "force": "warning",
                "speaker_role": "npc",
                "speaker_mention": _mention("Aldric"),
                "addressee_mention": _mention("me"),
                "quote_spans": [_span(source, quote)],
                "evidence_spans": [_span(source, warning)],
            },
            {
                "local_id": "act_assertion",
                "force": "assertion",
                "speaker_role": "player",
                "speaker_mention": None,
                "addressee_mention": None,
                "quote_spans": [],
                "evidence_spans": [_span(source, relation)],
            },
        ],
        "events": [
            {
                "local_id": "event_cross",
                "source_act_id": "act_warning",
                "predicate_surface": "cruces",
                "family": "movement",
                "arguments": [
                    {
                        "role": "theme",
                        "mention": _mention("el puente", "location"),
                    }
                ],
                "polarity": "negative",
                "epistemic_status": "not_established",
                "action_phase": "planned",
                "temporal_expression": None,
                "attributed_source": _mention("Aldric"),
                "evidence_spans": [_span(source, warning)],
            }
        ],
        "discourse_links": [
            {
                "local_id": "link_quote",
                "source_ref": "act:act_warning",
                "target_ref": "event:event_cross",
                "link_type": "quotes",
                "anchor_candidate": None,
                "evidence_spans": [_span(source, quote)],
            }
        ],
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
                "evidence_spans": [_span(source, relation)],
            }
        ],
        "clarification_candidates": [],
    }


def test_v3_round_trip_keeps_acts_events_links_and_facts_orthogonal():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    analysis = TurnInterpretationV3.from_payload(_payload(source), source_text=source)

    assert analysis.schema_version == 3
    assert analysis.utterance_acts[0].force is UtteranceForce.WARNING
    assert analysis.utterance_acts[0].speaker_role is SpeakerRole.NPC
    assert analysis.utterance_acts[0].speaker_mention.text == "Aldric"
    assert analysis.events[0].source_act_id == "act_warning"
    assert analysis.events[0].epistemic_status is EpistemicStatus.NOT_ESTABLISHED
    assert analysis.events[0].action_phase is ActionPhase.PLANNED
    assert analysis.events[0].polarity is SemanticPolarity.NEGATIVE
    assert analysis.discourse_links[0].link_type is DiscourseLinkType.QUOTES
    assert analysis.world_facts[0].direction is RelationDirection.SYMMETRIC
    assert analysis.world_facts[0].normalized_relation_type == "kinship.sibling"
    assert analysis.world_facts[0].temporal_scope is FactTemporalScope.PERMANENT

    restored = TurnInterpretationV3.from_json(
        analysis.to_json(),
        source_text=source,
    )
    assert restored == analysis
    assert json.loads(analysis.to_json()) == analysis.to_dict()


def test_evidence_offsets_are_half_open_unicode_character_ranges():
    source = "Mara observa la runa: «Ω»."
    span = EvidenceSpan.from_payload(_span(source, "Ω"), source_text=source)

    assert source[span.start:span.end] == "Ω"
    assert span.end - span.start == 1


def test_decoder_rejects_span_offsets_that_do_not_match_current_player_text():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    payload = _payload(source)
    payload["utterance_acts"][0]["evidence_spans"][0]["start"] += 1

    with pytest.raises(TurnInterpretationV3ValidationError) as error:
        TurnInterpretationV3.from_payload(payload, source_text=source)

    assert error.value.code == "invalid_payload"
    assert error.value.field_path == "payload"


def test_decoder_rejects_history_only_mentions_and_unknown_schema_fields():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    payload = _payload(source)
    payload["utterance_acts"] = [{
        "local_id": "act_assertion",
        "force": "assertion",
        "speaker_role": "player",
        "speaker_mention": _mention("Aldric"),
        "addressee_mention": None,
        "quote_spans": [],
        "evidence_spans": [_span(source, source)],
    }]
    payload["events"] = []
    payload["discourse_links"] = []
    payload["world_facts"][0]["source_act_id"] = "act_assertion"
    payload["world_facts"][0]["subject"] = _mention("El Rey del Norte")

    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(payload, source_text=source)

    valid = _payload(source)
    valid["untrusted_entity_id"] = 42
    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(valid, source_text=source)


def test_decoder_rejects_canonical_ids_inside_semantic_mentions():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    payload = _payload(source)
    payload["world_facts"][0]["subject"]["entity_id"] = 77

    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(payload, source_text=source)


def test_local_references_must_resolve_and_reject_duplicate_local_ids():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    invalid_link = _payload(source)
    invalid_link["discourse_links"][0]["target_ref"] = "event:not_present"
    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(invalid_link, source_text=source)

    duplicate = _payload(source)
    duplicate["utterance_acts"][1]["local_id"] = "act_warning"
    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(duplicate, source_text=source)


def test_decoder_rejects_unsorted_and_overlapping_evidence_spans():
    source = "Mara saluda y después habla con Aldric."
    base = {
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_sequence",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [
                _span(source, "habla con Aldric"),
                _span(source, "Mara saluda"),
            ],
        }],
        "events": [],
        "discourse_links": [],
        "world_facts": [],
        "clarification_candidates": [],
    }
    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(base, source_text=source)

    base["utterance_acts"][0]["evidence_spans"] = [
        _span(source, "Mara saluda y"),
        _span(source, "saluda"),
    ]
    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(base, source_text=source)


def test_top_level_utterance_acts_must_preserve_surface_order():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    payload = _payload(source)
    payload["utterance_acts"].reverse()

    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(payload, source_text=source)


def test_callback_link_uses_a_surface_anchor_and_never_a_model_supplied_turn_id():
    source = "Retomando lo de la pared, intento escalarla."
    callback = {
        "schema_version": 3,
        "utterance_acts": [
            {
                "local_id": "act_player",
                "force": "assertion",
                "speaker_role": "player",
                "speaker_mention": None,
                "addressee_mention": None,
                "quote_spans": [],
                "evidence_spans": [_span(source, source)],
            },
        ],
        "events": [
            {
                "local_id": "event_climb",
                "source_act_id": "act_player",
                "predicate_surface": "escalar",
                "family": "movement",
                "arguments": [
                    {
                        "role": "theme",
                        "mention": _mention("la pared", "location"),
                    }
                ],
                "polarity": "positive",
                "epistemic_status": "asserted",
                "action_phase": "attempted",
                "temporal_expression": None,
                "attributed_source": None,
                "evidence_spans": [_span(source, "la pared"), _span(source, "intento escalarla")],
            }
        ],
        "discourse_links": [
            {
                "local_id": "link_callback",
                "source_ref": "event:event_climb",
                "target_ref": None,
                "link_type": "callback",
                "anchor_candidate": "la pared",
                "evidence_spans": [_span(source, "Retomando lo de la pared")],
            }
        ],
        "world_facts": [],
        "clarification_candidates": [],
    }
    analysis = TurnInterpretationV3.from_payload(callback, source_text=source)
    link = analysis.discourse_links[0]
    assert link.target_ref is None
    assert link.anchor_candidate == "la pared"
    assert "turn_id" not in analysis.to_dict()

    callback["discourse_links"][0]["target_ref"] = "turn:42"
    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(callback, source_text=source)


def test_callback_requires_anchor_and_non_callback_links_require_local_target():
    source = "Retomando lo de la pared."
    base = {
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_callback",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [_span(source, source)],
        }],
        "events": [],
        "discourse_links": [{
            "local_id": "link_callback",
            "source_ref": "act:act_callback",
            "target_ref": None,
            "link_type": "callback",
            "anchor_candidate": None,
            "evidence_spans": [_span(source, source)],
        }],
        "world_facts": [],
        "clarification_candidates": [],
    }
    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(base, source_text=source)

    base["discourse_links"][0]["link_type"] = "continuation"
    base["discourse_links"][0]["anchor_candidate"] = None
    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(base, source_text=source)


def _conditional_payload(source: str) -> dict:
    return {
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_turn",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [_span(source, source)],
        }],
        "events": [
            {
                "local_id": "event_open",
                "source_act_id": "act_turn",
                "predicate_surface": "abro",
                "family": "interaction",
                "arguments": [{
                    "role": "theme",
                    "mention": _mention("la puerta", "world_entity"),
                }],
                "polarity": "positive",
                "epistemic_status": "hypothetical",
                "action_phase": "planned",
                "temporal_expression": None,
                "attributed_source": None,
                "evidence_spans": [_span(source, "abro la puerta")],
            },
            {
                "local_id": "event_enter",
                "source_act_id": "act_turn",
                "predicate_surface": "entro",
                "family": "movement",
                "arguments": [{
                    "role": "destination",
                    "mention": _mention("la sala", "location"),
                }],
                "polarity": "positive",
                "epistemic_status": "hypothetical",
                "action_phase": "planned",
                "temporal_expression": None,
                "attributed_source": None,
                "evidence_spans": [_span(source, "entro en la sala")],
            },
        ],
        "discourse_links": [{
            "local_id": "link_condition",
            "source_ref": "event:event_enter",
            "target_ref": "event:event_open",
            "link_type": "condition_on_success",
            "anchor_candidate": None,
            "evidence_spans": [_span(source, "Si abro la puerta")],
        }],
        "world_facts": [],
        "clarification_candidates": [],
    }


def test_event_evidence_must_be_contained_in_its_declared_source_act():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    payload = _payload(source)
    payload["discourse_links"] = []
    payload["utterance_acts"][0]["quote_spans"] = []
    payload["utterance_acts"][0]["evidence_spans"] = [
        _span(source, "Aldric me advierte")
    ]
    payload["events"][0]["attributed_source"] = None
    payload["events"][0]["evidence_spans"] = [
        _span(source, "cruces el puente")
    ]

    with pytest.raises(TurnInterpretationV3ValidationError) as error:
        TurnInterpretationV3.from_payload(payload, source_text=source)

    assert error.value.code == "event_evidence_outside_source_act"
    assert error.value.field_path == "events/0/evidence_spans/0"
    assert source not in str(error.value)
    assert "cruces el puente" not in str(error.value)


def test_fact_evidence_must_be_contained_in_its_declared_source_act():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    payload = _payload(source)
    payload["utterance_acts"][1]["evidence_spans"] = [
        _span(source, "Mara")
    ]
    payload["world_facts"][0]["evidence_spans"] = [
        _span(source, "Mara"),
        _span(source, "hermana"),
        _span(source, "Aldric."),
    ]

    with pytest.raises(TurnInterpretationV3ValidationError) as error:
        TurnInterpretationV3.from_payload(payload, source_text=source)

    assert error.value.code == "fact_evidence_outside_source_act"
    assert error.value.field_path == "world_facts/0/evidence_spans/1"


def test_quote_link_must_connect_an_act_to_an_event_from_that_same_act():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    payload = _payload(source)
    other_event = dict(payload["events"][0])
    other_event.update({
        "local_id": "event_relation",
        "source_act_id": "act_assertion",
        "predicate_surface": "hermana",
        "family": "social",
        "arguments": [
            {"role": "agent", "mention": _mention("Mara")},
            {"role": "theme", "mention": _mention("Aldric")},
        ],
        "action_phase": "state",
        "attributed_source": None,
        "evidence_spans": [_span(source, "Mara es hermana de Aldric.")],
    })
    payload["events"].append(other_event)
    payload["discourse_links"][0]["target_ref"] = "event:event_relation"

    with pytest.raises(TurnInterpretationV3ValidationError) as error:
        TurnInterpretationV3.from_payload(payload, source_text=source)

    assert error.value.code == "quote_link_source_act_mismatch"


def test_quote_link_requires_act_to_event_endpoint_kinds():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    payload = _payload(source)
    payload["discourse_links"][0]["source_ref"] = "fact:fact_sibling"

    with pytest.raises(TurnInterpretationV3ValidationError) as error:
        TurnInterpretationV3.from_payload(payload, source_text=source)

    assert error.value.code == "quote_link_invalid_endpoints"


def test_quote_link_evidence_must_be_inside_the_source_acts_quote_span():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    payload = _payload(source)
    payload["discourse_links"][0]["evidence_spans"] = [
        _span(source, "Aldric me advierte")
    ]

    with pytest.raises(TurnInterpretationV3ValidationError) as error:
        TurnInterpretationV3.from_payload(payload, source_text=source)

    assert error.value.code == "quote_link_evidence_outside_quote"


def test_conditional_dependency_requires_event_endpoints_and_dependent_to_prerequisite_direction():
    source = "Si abro la puerta, entro en la sala."
    payload = _conditional_payload(source)
    valid = TurnInterpretationV3.from_payload(payload, source_text=source)
    assert valid.discourse_links[0].source_ref == "event:event_enter"
    assert valid.discourse_links[0].target_ref == "event:event_open"

    wrong_endpoints = _payload()
    wrong_endpoints["discourse_links"][0]["source_ref"] = "act:act_warning"
    wrong_endpoints["discourse_links"][0]["link_type"] = "condition_on_success"
    with pytest.raises(TurnInterpretationV3ValidationError) as endpoint_error:
        TurnInterpretationV3.from_payload(
            wrong_endpoints,
            source_text="Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric.",
        )
    assert endpoint_error.value.code == "condition_dependency_invalid_endpoints"

    wrong_direction = _conditional_payload(source)
    wrong_direction["discourse_links"][0]["source_ref"] = "event:event_open"
    wrong_direction["discourse_links"][0]["target_ref"] = "event:event_enter"
    with pytest.raises(TurnInterpretationV3ValidationError) as order_error:
        TurnInterpretationV3.from_payload(wrong_direction, source_text=source)
    assert order_error.value.code == "condition_dependency_forward_reference"


def test_conditional_dependent_must_be_a_planned_event_and_edge_must_not_repeat():
    source = "Si abro la puerta, entro en la sala."
    non_planned = _conditional_payload(source)
    non_planned["events"][1]["action_phase"] = "attempted"

    with pytest.raises(TurnInterpretationV3ValidationError) as phase_error:
        TurnInterpretationV3.from_payload(non_planned, source_text=source)
    assert phase_error.value.code == "condition_dependency_dependent_not_planned"

    duplicate = _conditional_payload(source)
    duplicate["discourse_links"].append({
        **duplicate["discourse_links"][0],
        "local_id": "link_condition_duplicate",
    })
    with pytest.raises(TurnInterpretationV3ValidationError) as duplicate_error:
        TurnInterpretationV3.from_payload(duplicate, source_text=source)
    assert duplicate_error.value.code == "duplicate_discourse_edge"


def test_before_after_link_requires_forward_event_sequence():
    source = "Abro la puerta y después entro en la sala."
    payload = _conditional_payload(source)
    payload["discourse_links"][0]["link_type"] = "before_after"
    valid = TurnInterpretationV3.from_payload(payload, source_text=source)
    assert valid.discourse_links[0].source_ref == "event:event_enter"

    payload["discourse_links"][0]["source_ref"] = "event:event_open"
    payload["discourse_links"][0]["target_ref"] = "event:event_enter"
    with pytest.raises(TurnInterpretationV3ValidationError) as error:
        TurnInterpretationV3.from_payload(payload, source_text=source)

    assert error.value.code == "sequence_link_invalid_order"


def test_clarification_evidence_must_be_grounded_in_an_affected_record():
    source = "Entrego la llave a Mara. Después observo la puerta."
    payload = {
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_transfer",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [_span(source, "Entrego la llave a Mara.")],
        }],
        "events": [],
        "discourse_links": [],
        "world_facts": [],
        "clarification_candidates": [{
            "local_id": "clarify_recipient",
            "affected_local_ids": ["act_transfer"],
            "ambiguity_kind": "role",
            "missing_slot": "recipient",
            "question_intent": "Aclarar el destinatario",
            "evidence_spans": [_span(source, "la puerta")],
        }],
    }

    with pytest.raises(TurnInterpretationV3ValidationError) as error:
        TurnInterpretationV3.from_payload(payload, source_text=source)

    assert error.value.code == "clarification_evidence_outside_affected_records"


def test_other_fact_candidates_cannot_mix_in_relation_only_fields():
    source = (
        "Aldric me advierte: «No cruces el puente». "
        "Mara es hermana de Aldric."
    )
    payload = _payload(source)
    payload["world_facts"][0]["fact_kind"] = "other"

    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(payload, source_text=source)


def test_relation_fact_requires_two_endpoints_and_explicit_direction():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    payload = _payload(source)
    payload["world_facts"][0]["direction"] = None

    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(payload, source_text=source)


def test_attribute_fact_is_a_candidate_not_a_persistence_decision():
    source = "Aldric muestra una cicatriz nueva."
    fact = {
        "local_id": "fact_scar",
        "source_act_id": "act_show",
        "fact_kind": "entity_attribute",
        "subject": _mention("Aldric"),
        "predicate_surface": "cicatriz",
        "object": None,
        "value_surface": "cicatriz nueva",
        "relation_family": None,
        "normalized_relation_type": None,
        "direction": None,
        "polarity": "positive",
        "epistemic_status": "observed",
        "temporal_scope": "permanent",
        "attributed_source": None,
        "evidence_spans": [_span(source, source)],
    }
    payload = {
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_show",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [_span(source, source)],
        }],
        "events": [],
        "discourse_links": [],
        "world_facts": [fact],
        "clarification_candidates": [],
    }

    analysis = TurnInterpretationV3.from_payload(payload, source_text=source)

    assert analysis.world_facts[0].fact_kind.value == "entity_attribute"
    assert analysis.world_facts[0].temporal_scope is FactTemporalScope.PERMANENT
    assert not hasattr(analysis.world_facts[0], "persistence_authorized")


def test_clarification_candidates_reference_turn_local_records_only():
    source = "Entrego la llave a Mara."
    act_span = _span(source, source)
    payload = {
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_transfer",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [act_span],
        }],
        "events": [],
        "discourse_links": [],
        "world_facts": [],
        "clarification_candidates": [{
            "local_id": "clarify_recipient",
            "affected_local_ids": ["act_transfer"],
            "ambiguity_kind": "role",
            "missing_slot": "recipient",
            "question_intent": "Aclarar a quién se entrega la llave",
            "evidence_spans": [act_span],
        }],
    }

    parsed = TurnInterpretationV3.from_payload(payload, source_text=source)
    assert parsed.clarification_candidates[0].affected_local_ids == ("act_transfer",)

    payload["clarification_candidates"][0]["affected_local_ids"] = ["turn_17"]
    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(payload, source_text=source)


def test_v3_payload_cannot_choose_gameplay_actions_or_persistence_permissions():
    source = "Abro la puerta."
    payload = {
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_open",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [_span(source, source)],
        }],
        "events": [],
        "discourse_links": [],
        "world_facts": [],
        "clarification_candidates": [],
        "gameplay_actions": [{
            "action_type": "open_door",
            "eligible": True,
            "canonical_entity_id": 12,
        }],
    }

    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(payload, source_text=source)


def test_gameplay_action_candidate_is_a_backend_only_typed_record():
    actor = SemanticMention("mi personaje", SemanticObjectKind.CHARACTER)
    target = SemanticMention("la puerta", SemanticObjectKind.WORLD_ENTITY)
    reference = GameplayResolvedReference(
        mention=target,
        category=GameplayResolvedReferenceKind.ENTITY,
        referent_id=12,
        name="Puerta norte",
    )
    blocked = GameplayActionCandidate(
        local_id="action_enter",
        source_event_id="event_enter",
        actor=actor,
        action_type="movement.enter",
        eligibility=GameplayActionEligibility.BLOCKED_BY_DEPENDENCY,
        reason=GameplayActionReason.DEPENDENCY_PENDING,
        workflow=GameplayWorkflow.MECHANICS,
        unlock_condition=GameplayUnlockCondition.DEPENDENCY_SUCCESS,
        processing_state=GameplayProcessingState.BLOCKED,
        target_mentions=(target,),
        dependency_event_ids=("event_unlock",),
        resolved_references=(reference,),
    )

    assert blocked.resolved_references[0].referent_id == 12
    assert blocked.eligibility is GameplayActionEligibility.BLOCKED_BY_DEPENDENCY
    assert not hasattr(GameplayActionCandidate, "from_payload")

    with pytest.raises(ValueError, match="unlock condition"):
        GameplayActionCandidate(
            local_id="action_enter",
            source_event_id="event_enter",
            actor=actor,
            action_type="movement.enter",
            eligibility=GameplayActionEligibility.BLOCKED_BY_DEPENDENCY,
            reason=GameplayActionReason.DEPENDENCY_PENDING,
            workflow=GameplayWorkflow.MECHANICS,
            unlock_condition=GameplayUnlockCondition.NONE,
            processing_state=GameplayProcessingState.BLOCKED,
            dependency_event_ids=("event_unlock",),
        )


def test_v3_contract_rejects_oversized_collections_and_unsupported_enum_values():
    source = "Aldric me advierte: «No cruces el puente». Mara es hermana de Aldric."
    payload = _payload(source)
    payload["utterance_acts"] = payload["utterance_acts"] * 5

    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(payload, source_text=source)

    invalid_enum = _payload(source)
    invalid_enum["utterance_acts"][0]["force"] = "imperative_future"
    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(invalid_enum, source_text=source)


def test_v3_decoder_fails_closed_for_invalid_json_and_source_text():
    with pytest.raises(TurnInterpretationV3ValidationError) as json_error:
        TurnInterpretationV3.from_json("{", source_text="Abro la puerta.")
    assert json_error.value.code == "invalid_json"

    with pytest.raises(TurnInterpretationV3ValidationError) as source_error:
        TurnInterpretationV3.from_payload({}, source_text=" ")
    assert source_error.value.code == "invalid_source_text"


def test_contract_records_are_immutable_and_ids_are_local_namespaced_only():
    source = "Abro la puerta."
    parsed = TurnInterpretationV3.from_payload({
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_open",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [_span(source, source)],
        }],
        "events": [],
        "discourse_links": [],
        "world_facts": [],
        "clarification_candidates": [],
    }, source_text=source)

    with pytest.raises((FrozenInstanceError, AttributeError)):
        parsed.schema_version = 2

    bad_id = {
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "entity_42",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [_span(source, source)],
        }],
        "events": [],
        "discourse_links": [],
        "world_facts": [],
        "clarification_candidates": [],
    }
    with pytest.raises(TurnInterpretationV3ValidationError):
        TurnInterpretationV3.from_payload(bad_id, source_text=source)
