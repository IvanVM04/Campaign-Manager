from __future__ import annotations

import json

import pytest

from models.player_turn_interpretation_v3 import TurnInterpretationV3
from tests.player_turn_v3_graph_evaluation import (
    _validate_graph,
    load_v3_graph_corpus,
    score_v3_graph_scenario,
)
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger


def _span(source: str, text: str | None = None) -> dict[str, object]:
    """Build a model EvidenceSpan, including its required source marker."""
    value = source if text is None else text
    start = source.index(value)
    return {
        "start": start,
        "end": start + len(value),
        "text": value,
        "source": "current_utterance",
    }


def _gold_span(source: str, text: str | None = None) -> dict[str, object]:
    """Build a corpus annotation span; gold intentionally has no source field."""
    value = source if text is None else text
    start = source.index(value)
    return {
        "start": start,
        "end": start + len(value),
        "text": value,
    }


def _open_door_payload(source: str, *, role: str = "theme") -> str:
    span = _span(source)
    return json.dumps({
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_player_9",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [span],
        }],
        "events": [{
            "local_id": "event_open_9",
            "source_act_id": "act_player_9",
            "predicate_surface": "Abro",
            "family": "interaction",
            "arguments": [{
                "role": role,
                "mention": {"text": "la puerta", "kind_hint": "world_entity"},
            }],
            "polarity": "positive",
            "epistemic_status": "asserted",
            "action_phase": "attempted",
            "temporal_expression": None,
            "attributed_source": None,
            "evidence_spans": [_span(source, "Abro la puerta")],
        }],
        "discourse_links": [],
        "world_facts": [],
        "clarification_candidates": [],
    }, ensure_ascii=False)


def _conditional_payload(source: str, *, reverse_link: bool = False) -> str:
    act_span = _span(source)
    open_span = _span(source, "abro la puerta")
    enter_span = _span(source, "entro en la sala")
    link_span = _span(source, "Si abro la puerta")
    source_event = "event_open" if reverse_link else "event_enter"
    target_event = "event_enter" if reverse_link else "event_open"
    return json.dumps({
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_player",
            "force": "hypothesis",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [act_span],
        }],
        "events": [
            {
                "local_id": "event_open",
                "source_act_id": "act_player",
                "predicate_surface": "abro",
                "family": "interaction",
                "arguments": [{
                    "role": "theme",
                    "mention": {"text": "la puerta", "kind_hint": "world_entity"},
                }],
                "polarity": "positive",
                "epistemic_status": "hypothetical",
                "action_phase": "planned",
                "temporal_expression": None,
                "attributed_source": None,
                "evidence_spans": [open_span],
            },
            {
                "local_id": "event_enter",
                "source_act_id": "act_player",
                "predicate_surface": "entro",
                "family": "movement",
                "arguments": [{
                    "role": "destination",
                    "mention": {"text": "la sala", "kind_hint": "location"},
                }],
                "polarity": "positive",
                "epistemic_status": "hypothetical",
                "action_phase": "planned",
                "temporal_expression": None,
                "attributed_source": None,
                "evidence_spans": [enter_span],
            },
        ],
        "discourse_links": [{
            "local_id": "link_condition",
            "source_ref": f"event:{source_event}",
            "target_ref": f"event:{target_event}",
            "link_type": "condition_on_success",
            "anchor_candidate": None,
            "evidence_spans": [link_span],
        }],
        "world_facts": [],
        "clarification_candidates": [],
    }, ensure_ascii=False)


def test_graph_corpus_is_held_out_and_has_unique_scenarios():
    scenarios = load_v3_graph_corpus()

    assert len(scenarios) == 20
    assert len({item["id"] for item in scenarios}) == 20
    assert all(item["critical"] for item in scenarios)
    assert {
        "simple_action",
        "speech_quote",
        "conditional_dependency",
        "persistent_relation",
        "persistent_attribute",
        "transfer_roles",
        "epistemic_uncertainty",
        "callback_reference",
        "clarification_reference",
        "multiple_fact_candidates",
    }.issubset({item["family"] for item in scenarios})


def test_graph_scorer_accepts_exact_graph_without_relying_on_model_local_ids():
    scenarios = load_v3_graph_corpus()
    scenario = next(item for item in scenarios if item["id"] == "open_door_attempt")
    interpretation = TurnInterpretationV3.from_json(
        _open_door_payload(scenario["input"]),
        source_text=scenario["input"],
    )
    ledger = SemanticEvaluationLedger()

    result = score_v3_graph_scenario(scenario, interpretation, ledger)

    assert result["graph_exact_match"] is True
    assert result["mismatch_components"] == []
    assert result["components"]["events"]["matched"] == 1
    assert result["components"]["discourse_edges"]["expected"] == 0
    serialized = json.dumps(result, ensure_ascii=False)
    summary = json.dumps(ledger.summary(), ensure_ascii=False)
    assert scenario["input"] not in serialized
    assert "la puerta" not in serialized
    assert scenario["input"] not in summary
    assert "la puerta" not in summary


def test_graph_scorer_detects_argument_role_attached_to_wrong_event():
    scenarios = load_v3_graph_corpus()
    scenario = next(item for item in scenarios if item["id"] == "open_door_attempt")
    interpretation = TurnInterpretationV3.from_json(
        _open_door_payload(scenario["input"], role="patient"),
        source_text=scenario["input"],
    )
    result = score_v3_graph_scenario(
        scenario, interpretation, SemanticEvaluationLedger()
    )

    assert result["graph_exact_match"] is False
    assert "events" in result["mismatch_components"]
    assert "event_sources" in result["mismatch_components"]


def test_graph_scorer_checks_conditional_edge_endpoints_after_node_alignment():
    scenarios = load_v3_graph_corpus()
    scenario = next(
        item for item in scenarios if item["id"] == "conditional_open_then_enter"
    )
    interpretation = TurnInterpretationV3.from_json(
        _conditional_payload(scenario["input"], reverse_link=True),
        source_text=scenario["input"],
    )
    result = score_v3_graph_scenario(
        scenario, interpretation, SemanticEvaluationLedger()
    )

    assert result["components"]["acts"]["matched"] == 1
    assert result["components"]["events"]["matched"] == 2
    assert result["components"]["links"]["matched"] == 1
    assert result["graph_exact_match"] is False
    assert result["mismatch_components"] == ["discourse_edges"]


def test_graph_scorer_counts_extra_nodes_as_false_positives():
    scenarios = load_v3_graph_corpus()
    scenario = next(item for item in scenarios if item["id"] == "open_door_attempt")
    payload = json.loads(_open_door_payload(scenario["input"]))
    extra = dict(payload["events"][0])
    extra["local_id"] = "event_extra"
    payload["events"].append(extra)
    interpretation = TurnInterpretationV3.from_payload(
        payload, source_text=scenario["input"]
    )
    result = score_v3_graph_scenario(
        scenario, interpretation, SemanticEvaluationLedger()
    )

    assert result["components"]["events"]["expected"] == 1
    assert result["components"]["events"]["predicted"] == 2
    assert result["components"]["events"]["false_positives"] == 1
    assert result["graph_exact_match"] is False


def test_graph_scorer_treats_invalid_interpretation_as_all_missing_nodes():
    scenarios = load_v3_graph_corpus()
    scenario = next(item for item in scenarios if item["id"] == "open_door_attempt")
    result = score_v3_graph_scenario(
        scenario,
        None,
        SemanticEvaluationLedger(),
        interpretation_status="invalid",
    )

    assert result["graph_exact_match"] is False
    assert result["interpretation_status"] == "invalid"
    assert result["components"]["acts"]["false_negatives"] == 1
    assert result["observed_node_counts"]["events"] == 0


def test_graph_scorer_resolves_clarification_affected_discourse_link():
    source = "Retomando lo de la pared, intento escalarla."
    scenarios = load_v3_graph_corpus()
    base = next(
        item for item in scenarios if item["id"] == "callback_then_attempt"
    )
    scenario = json.loads(json.dumps(base))
    scenario["expected_graph"]["clarifications"] = [{
        "ambiguity_kind": "referent",
        "missing_slot": "callback_reference",
        "question_intent": "¿Qué referencia quieres retomar?",
        "affected": [{"kind": "link", "index": 0}],
        "evidence_spans": [_gold_span(source, "lo de la pared")],
    }]
    _validate_graph(scenario["expected_graph"], source)
    payload = {
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_player",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [_span(source)],
        }],
        "events": [{
            "local_id": "event_climb",
            "source_act_id": "act_player",
            "predicate_surface": "escalar",
            "family": "movement",
            "arguments": [{
                "role": "theme",
                "mention": {"text": "la pared", "kind_hint": "location"},
            }],
            "polarity": "positive",
            "epistemic_status": "asserted",
            "action_phase": "attempted",
            "temporal_expression": None,
            "attributed_source": None,
            "evidence_spans": [_span(source)],
        }],
        "discourse_links": [{
            "local_id": "link_callback",
            "source_ref": "event:event_climb",
            "target_ref": None,
            "link_type": "callback",
            "anchor_candidate": "lo de la pared",
            "evidence_spans": [_span(source)],
        }],
        "world_facts": [],
        "clarification_candidates": [{
            "local_id": "clarify_link",
            "affected_local_ids": ["link_callback"],
            "ambiguity_kind": "referent",
            "missing_slot": "callback_reference",
            "question_intent": "¿Qué referencia quieres retomar?",
            "evidence_spans": [_span(source)],
        }],
    }
    interpretation = TurnInterpretationV3.from_payload(
        payload, source_text=source
    )

    result = score_v3_graph_scenario(
        scenario, interpretation, SemanticEvaluationLedger()
    )

    assert result["graph_exact_match"] is True
    assert result["components"]["clarification_edges"]["matched"] == 1


def test_graph_gold_rejects_evidence_outside_the_player_message():
    scenarios = load_v3_graph_corpus()
    scenario = next(item for item in scenarios if item["id"] == "open_door_attempt")
    graph = json.loads(json.dumps(scenario["expected_graph"]))
    graph["acts"][0]["evidence_spans"][0]["text"] = "texto externo"

    with pytest.raises(ValueError, match="not literal"):
        _validate_graph(graph, scenario["input"])
