import json

import pytest

from models.player_intent_analysis import PlayerIntentAnalysis
from models.semantic_frames import SemanticArgumentRole, SemanticModality, SemanticObjectKind
from services.turns import TurnResolutionCodec
from services.turns.turn_resolution_service import TurnResolutionPlan


def payload():
    return {
        "schema_version": 2, "category": "action",
        "steps": [{
            "index": 0, "source_excerpt": "Entrego la llave de hierro a Mara",
            "actor": "player", "action": "entregar la llave a Mara",
            "modality": "attempted", "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": ["la llave de hierro", "Mara"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "Entrego", "family": "transfer",
                "arguments": [
                    {"role": "theme", "mention": {"text": "la llave de hierro", "kind_hint": "item_instance"}},
                    {"role": "recipient", "mention": {"text": "Mara", "kind_hint": "character"}},
                ],
            },
        }],
        "active_step_index": 0, "requires_clarification": False,
        "clarification_question": None, "relation_claims": [],
    }


def test_action_frame_preserves_transfer_roles_and_item_instance_hint():
    source = "Entrego la llave de hierro a Mara."
    analysis = PlayerIntentAnalysis.from_payload(payload(), source_text=source)
    frame = analysis.steps[0].action_frame
    assert analysis.schema_version == 2
    assert frame is not None and frame.family.value == "transfer"
    assert frame.arguments[0].role is SemanticArgumentRole.THEME
    assert frame.arguments[0].mention.kind_hint is SemanticObjectKind.ITEM_INSTANCE
    assert frame.arguments[1].role is SemanticArgumentRole.RECIPIENT


def test_v2_round_trip_and_literal_evidence_validation():
    source = "Entrego la llave de hierro a Mara."
    analysis = PlayerIntentAnalysis.from_payload(payload(), source_text=source)
    assert PlayerIntentAnalysis.from_json(analysis.to_json(), source_text=source) == analysis
    invalid = payload()
    invalid["steps"][0]["action_frame"]["predicate"] = "teletransporto"
    with pytest.raises(ValueError, match="predicate is not literal"):
        PlayerIntentAnalysis.from_payload(invalid, source_text=source)


def test_semantic_mentions_cannot_include_model_supplied_ids():
    source = "Entrego la llave de hierro a Mara."
    invalid = payload()
    invalid["steps"][0]["action_frame"]["arguments"][1]["mention"]["entity_id"] = 42
    with pytest.raises(ValueError, match="missing or unexpected"):
        PlayerIntentAnalysis.from_payload(invalid, source_text=source)


def test_relation_claim_preserves_direction_attribution_and_reported_modality():
    source = "Mara dice que Aldric es su hermano."
    value = {
        "schema_version": 2, "category": "report",
        "steps": [{
            "index": 0, "source_excerpt": source, "actor": "npc",
            "action": "decir que Aldric es su hermano", "modality": "reported",
            "polarity": "positive", "reported_outcome": "not_claimed",
            "target_mentions": ["Mara", "Aldric"], "attributed_to": "Mara",
            "action_frame": {"predicate": "dice", "family": "communication", "arguments": []},
        }],
        "active_step_index": None, "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [{
            "step_index": 0,
            "subject": {"text": "Aldric", "kind_hint": "character"},
            "predicate": "hermano",
            "object": {"text": "Mara", "kind_hint": "character"},
            "relation_family": "kinship", "polarity": "positive",
            "modality": "reported", "source_excerpt": "Aldric es su hermano",
            "attributed_to": {"text": "Mara", "kind_hint": "character"},
            "temporal_expression": None,
        }],
    }
    claim = PlayerIntentAnalysis.from_payload(value, source_text=source).relation_claims[0]
    assert (claim.subject.text, claim.object.text) == ("Aldric", "Mara")
    assert claim.modality is SemanticModality.REPORTED
    assert claim.attributed_to.text == "Mara"


def test_v1_persisted_contract_remains_decodable():
    source = "Abro la puerta."
    v1 = {
        "schema_version": 1, "category": "action",
        "steps": [{
            "index": 0, "source_excerpt": source, "actor": "player",
            "action": "abrir la puerta", "modality": "attempted",
            "polarity": "positive", "reported_outcome": "not_claimed",
            "target_mentions": ["la puerta"], "attributed_to": None,
        }],
        "active_step_index": 0, "requires_clarification": False,
        "clarification_question": None,
    }
    analysis = PlayerIntentAnalysis.from_payload(v1, source_text=source)
    assert analysis.schema_version == 1
    assert analysis.steps[0].action_frame is None
    assert json.loads(analysis.to_json()) == v1


def test_v2_semantic_frames_survive_durable_intent_codec_recovery():
    source = "Entrego la llave de hierro a Mara."
    analysis = PlayerIntentAnalysis.from_payload(payload(), source_text=source)
    plan = TurnResolutionPlan(
        player_input=source,
        narrative="",
        world_operations=(),
        character_operations=(),
        ordered_operations=(),
        intent_analysis=analysis,
        intent_evidence_text=source,
    )

    encoded = TurnResolutionCodec.intent_to_json(plan)
    restored = TurnResolutionCodec.intent_from_json(
        encoded,
        original_input=source,
    )

    assert restored == analysis
