"""Graph-aware scoring for held-out v3 player-turn interpretations.

This module is test/evaluation infrastructure only. It compares full semantic
nodes and their relationships while keeping reports free of utterance text.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from models.player_turn_interpretation_v3 import TurnInterpretationV3
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

_GRAPH_CORPUS_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "player_turn_v3_graph_corpus_v1.json"
)
_GRAPH_KEYS = {"acts", "events", "links", "facts", "clarifications"}
_MENTION_KEYS = {"text", "kind_hint"}
_SPAN_KEYS = {"start", "end", "text"}
_REFERENCE_KINDS = {"act", "event", "fact"}


def _require_keys(value: Any, expected: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{name} has missing or unexpected fields")
    return value


def _validate_mention(value: Any, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    mention = _require_keys(value, _MENTION_KEYS, "graph gold mention")
    if (
        not isinstance(mention["text"], str)
        or not mention["text"].strip()
        or not isinstance(mention["kind_hint"], str)
        or not mention["kind_hint"].strip()
    ):
        raise ValueError("graph gold mention values must be non-empty strings")


def _span_texts(values: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(value["text"] for value in values)


def _require_literal_in_spans(
    value: str | None,
    spans: list[dict[str, Any]],
    field_name: str,
) -> None:
    if value is not None and not any(value in span for span in _span_texts(spans)):
        raise ValueError(f"{field_name} is not grounded in its gold evidence spans")


def _spans_within_parent(
    child: list[dict[str, Any]],
    parent: list[dict[str, Any]],
    field_name: str,
) -> None:
    for span in child:
        if not any(
            outer["start"] <= span["start"] and span["end"] <= outer["end"]
            for outer in parent
        ):
            raise ValueError(f"{field_name} is outside its source act evidence")


def _validate_spans(values: Any, source_text: str, *, minimum: int = 1) -> None:
    if not isinstance(values, list) or not minimum <= len(values) <= 4:
        raise ValueError("graph gold evidence spans must be a bounded array")
    previous_end = -1
    for value in values:
        span = _require_keys(value, _SPAN_KEYS, "graph gold evidence span")
        start, end, text = span["start"], span["end"], span["text"]
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or start < previous_end
            or end > len(source_text)
            or not isinstance(text, str)
            or not text
            or source_text[start:end] != text
        ):
            raise ValueError("graph gold evidence span is invalid or not literal")
        previous_end = end


def _validate_reference(value: Any, graph: dict[str, Any], *, nullable: bool) -> None:
    if value is None and nullable:
        return
    reference = _require_keys(value, {"kind", "index"}, "graph gold reference")
    kind, index = reference["kind"], reference["index"]
    if (
        kind not in _REFERENCE_KINDS
        or isinstance(index, bool)
        or not isinstance(index, int)
        or not 0 <= index < len(graph[f"{kind}s"])
    ):
        raise ValueError("graph gold reference does not resolve")


def _validate_graph(graph: Any, source_text: str) -> None:
    gold = _require_keys(graph, _GRAPH_KEYS, "expected_graph")
    if any(not isinstance(gold[key], list) for key in _GRAPH_KEYS):
        raise ValueError("expected_graph nodes must be arrays")

    for act in gold["acts"]:
        act = _require_keys(
            act,
            {
                "force", "speaker_role", "speaker_mention", "addressee_mention",
                "quote_spans", "evidence_spans",
            },
            "graph gold act",
        )
        for key in ("force", "speaker_role"):
            if not isinstance(act[key], str) or not act[key].strip():
                raise ValueError("graph gold act labels must be non-empty strings")
        _validate_mention(act["speaker_mention"], nullable=True)
        _validate_mention(act["addressee_mention"], nullable=True)
        _validate_spans(act["quote_spans"], source_text, minimum=0)
        _validate_spans(act["evidence_spans"], source_text)
        _require_literal_in_spans(
            None if act["speaker_mention"] is None else act["speaker_mention"]["text"],
            act["evidence_spans"],
            "speaker mention",
        )
        _require_literal_in_spans(
            None if act["addressee_mention"] is None else act["addressee_mention"]["text"],
            act["evidence_spans"],
            "addressee mention",
        )
        _spans_within_parent(
            act["quote_spans"], act["evidence_spans"], "quote span"
        )

    for event in gold["events"]:
        event = _require_keys(
            event,
            {
                "source_act_index", "predicate_surface", "family", "arguments",
                "polarity", "epistemic_status", "action_phase",
                "temporal_expression", "attributed_source", "evidence_spans",
            },
            "graph gold event",
        )
        source_index = event["source_act_index"]
        if (
            isinstance(source_index, bool)
            or not isinstance(source_index, int)
            or not 0 <= source_index < len(gold["acts"])
        ):
            raise ValueError("graph gold event source act does not resolve")
        for key in (
            "predicate_surface", "family", "polarity", "epistemic_status",
            "action_phase",
        ):
            if not isinstance(event[key], str) or not event[key].strip():
                raise ValueError("graph gold event labels must be non-empty strings")
        if event["temporal_expression"] is not None and not isinstance(
            event["temporal_expression"], str
        ):
            raise ValueError("graph gold temporal expression must be text or null")
        _validate_mention(event["attributed_source"], nullable=True)
        if not isinstance(event["arguments"], list) or len(event["arguments"]) > 12:
            raise ValueError("graph gold event arguments must be bounded")
        for argument in event["arguments"]:
            argument = _require_keys(
                argument, {"role", "mention"}, "graph gold event argument"
            )
            if not isinstance(argument["role"], str) or not argument["role"].strip():
                raise ValueError("graph gold argument role must be non-empty")
            _validate_mention(argument["mention"])
        _validate_spans(event["evidence_spans"], source_text)
        _require_literal_in_spans(
            event["predicate_surface"], event["evidence_spans"], "event predicate"
        )
        _require_literal_in_spans(
            event["temporal_expression"], event["evidence_spans"], "event temporal expression"
        )
        _require_literal_in_spans(
            None if event["attributed_source"] is None else event["attributed_source"]["text"],
            event["evidence_spans"],
            "event attributed source",
        )
        for argument in event["arguments"]:
            _require_literal_in_spans(
                argument["mention"]["text"],
                event["evidence_spans"],
                "event argument mention",
            )
        source_evidence = gold["acts"][source_index]["evidence_spans"]
        _spans_within_parent(
            event["evidence_spans"], source_evidence, "event evidence"
        )

    for link in gold["links"]:
        link = _require_keys(
            link,
            {"link_type", "source", "target", "anchor_candidate", "evidence_spans"},
            "graph gold link",
        )
        if not isinstance(link["link_type"], str) or not link["link_type"].strip():
            raise ValueError("graph gold link type must be non-empty")
        _validate_reference(link["source"], gold, nullable=False)
        _validate_reference(link["target"], gold, nullable=True)
        if link["link_type"] == "callback":
            if link["target"] is not None or not isinstance(
                link["anchor_candidate"], str
            ) or not link["anchor_candidate"].strip():
                raise ValueError("callback gold requires an anchor and no local target")
        elif link["target"] is None or link["anchor_candidate"] is not None:
            raise ValueError("non-callback gold requires a target and no anchor")
        _validate_spans(link["evidence_spans"], source_text)
        if link["link_type"] == "callback":
            _require_literal_in_spans(
                link["anchor_candidate"], link["evidence_spans"], "callback anchor"
            )

    for fact in gold["facts"]:
        fact = _require_keys(
            fact,
            {
                "source_act_index", "fact_kind", "subject", "predicate_surface",
                "object", "value_surface", "relation_family",
                "normalized_relation_type", "direction", "polarity",
                "epistemic_status", "temporal_scope", "attributed_source",
                "evidence_spans",
            },
            "graph gold fact",
        )
        source_index = fact["source_act_index"]
        if (
            isinstance(source_index, bool)
            or not isinstance(source_index, int)
            or not 0 <= source_index < len(gold["acts"])
        ):
            raise ValueError("graph gold fact source act does not resolve")
        for key in (
            "fact_kind", "predicate_surface", "polarity", "epistemic_status",
            "temporal_scope",
        ):
            if not isinstance(fact[key], str) or not fact[key].strip():
                raise ValueError("graph gold fact labels must be non-empty strings")
        _validate_mention(fact["subject"])
        _validate_mention(fact["object"], nullable=True)
        _validate_mention(fact["attributed_source"], nullable=True)
        for key in ("value_surface", "relation_family", "normalized_relation_type", "direction"):
            if fact[key] is not None and (
                not isinstance(fact[key], str) or not fact[key].strip()
            ):
                raise ValueError("graph gold fact optional labels must be text or null")
        _validate_spans(fact["evidence_spans"], source_text)
        _require_literal_in_spans(
            fact["subject"]["text"], fact["evidence_spans"], "fact subject"
        )
        _require_literal_in_spans(
            fact["predicate_surface"], fact["evidence_spans"], "fact predicate"
        )
        _require_literal_in_spans(
            None if fact["object"] is None else fact["object"]["text"],
            fact["evidence_spans"],
            "fact object",
        )
        _require_literal_in_spans(
            fact["value_surface"], fact["evidence_spans"], "fact value"
        )
        _require_literal_in_spans(
            None if fact["attributed_source"] is None else fact["attributed_source"]["text"],
            fact["evidence_spans"],
            "fact attributed source",
        )
        source_evidence = gold["acts"][source_index]["evidence_spans"]
        _spans_within_parent(
            fact["evidence_spans"], source_evidence, "fact evidence"
        )
        if fact["fact_kind"] == "relation":
            if (
                fact["object"] is None
                or fact["relation_family"] is None
                or fact["direction"] is None
                or fact["value_surface"] is not None
            ):
                raise ValueError("relation gold has invalid relation fields")
        elif fact["fact_kind"] == "entity_attribute":
            if (
                fact["object"] is not None
                or fact["value_surface"] is None
                or fact["relation_family"] is not None
                or fact["direction"] is not None
                or fact["normalized_relation_type"] is not None
            ):
                raise ValueError("entity-attribute gold has invalid attribute fields")
        elif fact["object"] is None and fact["value_surface"] is None:
            raise ValueError("other fact gold requires object or value")

    for clarification in gold["clarifications"]:
        clarification = _require_keys(
            clarification,
            {
                "ambiguity_kind", "missing_slot", "question_intent",
                "affected", "evidence_spans",
            },
            "graph gold clarification",
        )
        for key in ("ambiguity_kind", "missing_slot", "question_intent"):
            if not isinstance(clarification[key], str) or not clarification[key].strip():
                raise ValueError("graph gold clarification labels must be non-empty")
        if not isinstance(clarification["affected"], list) or not clarification["affected"]:
            raise ValueError("graph gold clarification requires affected references")
        for reference in clarification["affected"]:
            _validate_reference(reference, gold, nullable=False)
        _validate_spans(clarification["evidence_spans"], source_text)


def load_v3_graph_corpus() -> list[dict[str, Any]]:
    """Load the frozen graph-gold holdout; reject leakage-prone or malformed rows."""
    corpus = json.loads(_GRAPH_CORPUS_PATH.read_text(encoding="utf-8"))
    if (
        not isinstance(corpus, dict)
        or set(corpus) != {"schema_version", "split", "purpose", "scenarios"}
        or corpus["schema_version"] != 1
        or corpus["split"] != "held_out"
        or not isinstance(corpus["purpose"], str)
        or not isinstance(corpus["scenarios"], list)
        or not corpus["scenarios"]
    ):
        raise ValueError("unsupported v3 graph corpus contract")

    scenarios = corpus["scenarios"]
    identifiers: list[str] = []
    for scenario in scenarios:
        scenario = _require_keys(
            scenario,
            {
                "id", "family", "critical", "input", "recent_turns",
                "visible_entities", "expected_graph",
            },
            "v3 graph scenario",
        )
        if (
            not isinstance(scenario["id"], str)
            or not scenario["id"].strip()
            or not isinstance(scenario["family"], str)
            or not scenario["family"].strip()
            or not isinstance(scenario["critical"], bool)
            or not isinstance(scenario["input"], str)
            or not scenario["input"].strip()
            or not isinstance(scenario["recent_turns"], list)
            or not isinstance(scenario["visible_entities"], list)
        ):
            raise ValueError("v3 graph scenario metadata is invalid")
        for turn in scenario["recent_turns"]:
            turn = _require_keys(
                turn, {"id", "player_input", "narrative"}, "recent turn"
            )
            if (
                isinstance(turn["id"], bool)
                or not isinstance(turn["id"], int)
                or turn["id"] < 1
                or not isinstance(turn["player_input"], str)
                or not isinstance(turn["narrative"], str)
            ):
                raise ValueError("graph recent turn metadata is invalid")
        for entity in scenario["visible_entities"]:
            entity = _require_keys(
                entity,
                {"id", "name", "entity_type", "description"},
                "visible entity",
            )
            if (
                isinstance(entity["id"], bool)
                or not isinstance(entity["id"], int)
                or entity["id"] < 1
                or any(
                    not isinstance(entity[key], str) or not entity[key].strip()
                    for key in ("name", "entity_type", "description")
                )
            ):
                raise ValueError("graph visible entity metadata is invalid")
        identifiers.append(scenario["id"])
        _validate_graph(scenario["expected_graph"], scenario["input"])
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("v3 graph corpus scenario IDs must be unique")
    return scenarios


def _mention_signature(mention: Any) -> tuple[str, str] | None:
    if mention is None:
        return None
    return (mention.text, mention.kind_hint.value)


def _span_signature(spans: Any) -> tuple[tuple[int, int, str], ...]:
    return tuple((span.start, span.end, span.text) for span in spans)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _gold_span_signature(spans: list[dict[str, Any]]) -> tuple[tuple[int, int, str], ...]:
    return tuple((span["start"], span["end"], span["text"]) for span in spans)


def _expected_act_signature(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["force"],
        item["speaker_role"],
        None if item["speaker_mention"] is None else (
            item["speaker_mention"]["text"], item["speaker_mention"]["kind_hint"]
        ),
        None if item["addressee_mention"] is None else (
            item["addressee_mention"]["text"], item["addressee_mention"]["kind_hint"]
        ),
        _gold_span_signature(item["quote_spans"]),
        _gold_span_signature(item["evidence_spans"]),
    )


def _actual_act_signature(item: Any) -> tuple[Any, ...]:
    return (
        item.force.value,
        item.speaker_role.value,
        _mention_signature(item.speaker_mention),
        _mention_signature(item.addressee_mention),
        _span_signature(item.quote_spans),
        _span_signature(item.evidence_spans),
    )


def _expected_event_signature(item: dict[str, Any]) -> tuple[Any, ...]:
    arguments = tuple(sorted(
        (
            argument["role"],
            argument["mention"]["text"],
            argument["mention"]["kind_hint"],
        )
        for argument in item["arguments"]
    ))
    return (
        item["predicate_surface"],
        item["family"],
        arguments,
        item["polarity"],
        item["epistemic_status"],
        item["action_phase"],
        item["temporal_expression"],
        None if item["attributed_source"] is None else (
            item["attributed_source"]["text"],
            item["attributed_source"]["kind_hint"],
        ),
        _gold_span_signature(item["evidence_spans"]),
    )


def _actual_event_signature(item: Any) -> tuple[Any, ...]:
    arguments = tuple(sorted(
        (argument.role.value, argument.mention.text, argument.mention.kind_hint.value)
        for argument in item.arguments
    ))
    return (
        item.predicate_surface,
        item.family.value,
        arguments,
        item.polarity.value,
        item.epistemic_status.value,
        item.action_phase.value,
        item.temporal_expression,
        _mention_signature(item.attributed_source),
        _span_signature(item.evidence_spans),
    )


def _expected_fact_signature(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["fact_kind"],
        (item["subject"]["text"], item["subject"]["kind_hint"]),
        item["predicate_surface"],
        None if item["object"] is None else (
            item["object"]["text"], item["object"]["kind_hint"]
        ),
        item["value_surface"],
        item["relation_family"],
        item["normalized_relation_type"],
        item["direction"],
        item["polarity"],
        item["epistemic_status"],
        item["temporal_scope"],
        None if item["attributed_source"] is None else (
            item["attributed_source"]["text"],
            item["attributed_source"]["kind_hint"],
        ),
        _gold_span_signature(item["evidence_spans"]),
    )


def _actual_fact_signature(item: Any) -> tuple[Any, ...]:
    return (
        item.fact_kind.value,
        _mention_signature(item.subject),
        item.predicate_surface,
        _mention_signature(item.object),
        item.value_surface,
        None if item.relation_family is None else item.relation_family.value,
        item.normalized_relation_type,
        None if item.direction is None else item.direction.value,
        item.polarity.value,
        item.epistemic_status.value,
        item.temporal_scope.value,
        _mention_signature(item.attributed_source),
        _span_signature(item.evidence_spans),
    )


def _expected_link_node_signature(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["link_type"],
        item["anchor_candidate"],
        _gold_span_signature(item["evidence_spans"]),
    )


def _actual_link_node_signature(item: Any) -> tuple[Any, ...]:
    return (
        item.link_type.value,
        item.anchor_candidate,
        _span_signature(item.evidence_spans),
    )


def _expected_clarification_node_signature(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["ambiguity_kind"],
        item["missing_slot"],
        _gold_span_signature(item["evidence_spans"]),
    )


def _actual_clarification_node_signature(item: Any) -> tuple[Any, ...]:
    return (
        item.ambiguity_kind.value,
        item.missing_slot,
        _span_signature(item.evidence_spans),
    )


def _match_nodes(
    *,
    metric_family: str,
    expected: list[Any],
    observed: list[Any],
    expected_signature: Any,
    observed_signature: Any,
    observed_id: Any,
    ledger: SemanticEvaluationLedger,
) -> tuple[bool, dict[str, int], dict[str, Any]]:
    expected_values = [_canonical(expected_signature(item)) for item in expected]
    observed_values = [_canonical(observed_signature(item)) for item in observed]
    expected_counts = Counter(expected_values)
    observed_counts = Counter(observed_values)
    matched = sum((expected_counts & observed_counts).values())
    ledger.record_semantic_slots(
        metric_family,
        expected_slots=expected_values,
        predicted_slots=observed_values,
    )
    ledger.record_case(
        metric_family,
        expected_slots=len(expected_values),
        matched_slots=matched,
        elapsed_seconds=0,
        case_passed=expected_counts == observed_counts,
    )

    expected_indexes: dict[str, deque[int]] = defaultdict(deque)
    for index, signature in enumerate(expected_values):
        expected_indexes[signature].append(index)
    mapping: dict[str, int] = {}
    for item, signature in zip(observed, observed_values, strict=True):
        indexes = expected_indexes.get(signature)
        if indexes:
            mapping[observed_id(item)] = indexes.popleft()
    return expected_counts == observed_counts, mapping, {
        "expected": len(expected_values),
        "predicted": len(observed_values),
        "matched": matched,
        "false_positives": len(observed_values) - matched,
        "false_negatives": len(expected_values) - matched,
    }


def _gold_ref_signature(reference: dict[str, Any] | None) -> tuple[str, int] | None:
    if reference is None:
        return None
    return (reference["kind"], reference["index"])


def _actual_ref_signature(
    reference: str | None,
    mappings: dict[str, dict[str, int]],
) -> tuple[str, int] | None:
    if reference is None:
        return None
    kind, separator, local_id = reference.partition(":")
    if not separator or kind not in _REFERENCE_KINDS:
        return ("unmatched", -1)
    index = mappings[kind].get(local_id)
    return (kind, index if index is not None else -1)


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 4)


def _counter_result(
    *,
    metric_family: str,
    expected: list[Any],
    observed: list[Any],
    ledger: SemanticEvaluationLedger,
) -> tuple[bool, dict[str, int | float | None]]:
    expected_values = [_canonical(item) for item in expected]
    observed_values = [_canonical(item) for item in observed]
    expected_counts = Counter(expected_values)
    observed_counts = Counter(observed_values)
    matched = sum((expected_counts & observed_counts).values())
    false_positives = len(observed_values) - matched
    false_negatives = len(expected_values) - matched
    ledger.record_semantic_slots(
        metric_family,
        expected_slots=expected_values,
        predicted_slots=observed_values,
    )
    ledger.record_case(
        metric_family,
        expected_slots=len(expected_values),
        matched_slots=matched,
        elapsed_seconds=0,
        case_passed=expected_counts == observed_counts,
    )
    return expected_counts == observed_counts, {
        "expected": len(expected_values),
        "predicted": len(observed_values),
        "matched": matched,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": _ratio(matched, matched + false_positives),
        "recall": _ratio(matched, matched + false_negatives),
    }


def score_v3_graph_scenario(
    scenario: dict[str, Any],
    interpretation: TurnInterpretationV3 | None,
    ledger: SemanticEvaluationLedger,
    *,
    interpretation_status: str = "valid",
) -> dict[str, Any]:
    """Score nodes and typed edges; diagnostics never contain literal content.

    Nodes are aligned by their full non-edge semantics and exact evidence spans,
    not by model-generated local IDs. Edges are scored only after this alignment,
    so a correct label attached to the wrong event or act is a graph error.
    """
    if not isinstance(ledger, SemanticEvaluationLedger):
        raise TypeError("ledger must be a SemanticEvaluationLedger")
    if interpretation is not None and not isinstance(interpretation, TurnInterpretationV3):
        raise TypeError("interpretation must be TurnInterpretationV3 or None")
    gold = scenario["expected_graph"]
    if interpretation_status != "valid":
        interpretation = None

    observed_acts = [] if interpretation is None else list(interpretation.utterance_acts)
    observed_events = [] if interpretation is None else list(interpretation.events)
    observed_links = [] if interpretation is None else list(interpretation.discourse_links)
    observed_facts = [] if interpretation is None else list(interpretation.world_facts)
    observed_clarifications = (
        [] if interpretation is None else list(interpretation.clarification_candidates)
    )
    family = scenario["family"]
    components: dict[str, dict[str, int | float | None]] = {}
    mismatches: list[str] = []

    acts_exact, act_map, components["acts"] = _match_nodes(
        metric_family=f"v3_graph_nodes.acts:{family}",
        expected=gold["acts"],
        observed=observed_acts,
        expected_signature=_expected_act_signature,
        observed_signature=_actual_act_signature,
        observed_id=lambda item: item.local_id,
        ledger=ledger,
    )
    events_exact, event_map, components["events"] = _match_nodes(
        metric_family=f"v3_graph_nodes.events:{family}",
        expected=gold["events"],
        observed=observed_events,
        expected_signature=_expected_event_signature,
        observed_signature=_actual_event_signature,
        observed_id=lambda item: item.local_id,
        ledger=ledger,
    )
    facts_exact, fact_map, components["facts"] = _match_nodes(
        metric_family=f"v3_graph_nodes.facts:{family}",
        expected=gold["facts"],
        observed=observed_facts,
        expected_signature=_expected_fact_signature,
        observed_signature=_actual_fact_signature,
        observed_id=lambda item: item.local_id,
        ledger=ledger,
    )
    links_exact, _link_map, components["links"] = _match_nodes(
        metric_family=f"v3_graph_nodes.links:{family}",
        expected=gold["links"],
        observed=observed_links,
        expected_signature=_expected_link_node_signature,
        observed_signature=_actual_link_node_signature,
        observed_id=lambda item: item.local_id,
        ledger=ledger,
    )
    clarifications_exact, clarification_map, components["clarifications"] = _match_nodes(
        metric_family=f"v3_graph_nodes.clarifications:{family}",
        expected=gold["clarifications"],
        observed=observed_clarifications,
        expected_signature=_expected_clarification_node_signature,
        observed_signature=_actual_clarification_node_signature,
        observed_id=lambda item: item.local_id,
        ledger=ledger,
    )
    mappings = {"act": act_map, "event": event_map, "fact": fact_map}

    expected_event_sources = [
        (index, item["source_act_index"])
        for index, item in enumerate(gold["events"])
    ]
    observed_event_sources = [
        (
            event_map.get(item.local_id, -1),
            act_map.get(item.source_act_id, -1),
        )
        for item in observed_events
    ]
    event_sources_exact, components["event_sources"] = _counter_result(
        metric_family=f"v3_graph_edges.event_sources:{family}",
        expected=expected_event_sources,
        observed=observed_event_sources,
        ledger=ledger,
    )

    expected_fact_sources = [
        (index, item["source_act_index"])
        for index, item in enumerate(gold["facts"])
    ]
    observed_fact_sources = [
        (
            fact_map.get(item.local_id, -1),
            act_map.get(item.source_act_id, -1),
        )
        for item in observed_facts
    ]
    fact_sources_exact, components["fact_sources"] = _counter_result(
        metric_family=f"v3_graph_edges.fact_sources:{family}",
        expected=expected_fact_sources,
        observed=observed_fact_sources,
        ledger=ledger,
    )

    expected_links = [
        (
            item["link_type"],
            _gold_ref_signature(item["source"]),
            _gold_ref_signature(item["target"]),
            item["anchor_candidate"],
            _gold_span_signature(item["evidence_spans"]),
        )
        for item in gold["links"]
    ]
    observed_links_normalized = [
        (
            item.link_type.value,
            _actual_ref_signature(item.source_ref, mappings),
            _actual_ref_signature(item.target_ref, mappings),
            item.anchor_candidate,
            _span_signature(item.evidence_spans),
        )
        for item in observed_links
    ]
    discourse_edges_exact, components["discourse_edges"] = _counter_result(
        metric_family=f"v3_graph_edges.discourse:{family}",
        expected=expected_links,
        observed=observed_links_normalized,
        ledger=ledger,
    )

    expected_affected = [
        (
            index,
            tuple(sorted(
                _gold_ref_signature(reference)
                for reference in item["affected"]
            )),
        )
        for index, item in enumerate(gold["clarifications"])
    ]
    observed_affected = []
    for item in observed_clarifications:
        affected: list[tuple[str, int]] = []
        for local_id in item.affected_local_ids:
            kind = (
                "act" if local_id.startswith("act_")
                else "event" if local_id.startswith("event_")
                else "fact" if local_id.startswith("fact_")
                else "unmatched"
            )
            affected.append((kind, mappings.get(kind, {}).get(local_id, -1)))
        observed_affected.append((
            clarification_map.get(item.local_id, -1),
            tuple(sorted(affected)),
        ))
    clarification_edges_exact, components["clarification_edges"] = _counter_result(
        metric_family=f"v3_graph_edges.clarification_affected:{family}",
        expected=expected_affected,
        observed=observed_affected,
        ledger=ledger,
    )

    exact = all((
        acts_exact,
        events_exact,
        facts_exact,
        links_exact,
        clarifications_exact,
        event_sources_exact,
        fact_sources_exact,
        discourse_edges_exact,
        clarification_edges_exact,
    ))
    for name, passed in (
        ("acts", acts_exact),
        ("events", events_exact),
        ("facts", facts_exact),
        ("links", links_exact),
        ("clarifications", clarifications_exact),
        ("event_sources", event_sources_exact),
        ("fact_sources", fact_sources_exact),
        ("discourse_edges", discourse_edges_exact),
        ("clarification_edges", clarification_edges_exact),
    ):
        if not passed:
            mismatches.append(name)

    ledger.record_case(
        f"v3_graph_exact_match:{family}",
        expected_slots=1,
        matched_slots=int(exact),
        elapsed_seconds=0,
        case_passed=exact,
    )
    return {
        "case_id": scenario["id"],
        "family": family,
        "critical": scenario["critical"],
        "interpretation_status": interpretation_status,
        "graph_exact_match": exact,
        "mismatch_components": mismatches,
        "components": components,
        "expected_node_counts": {
            "acts": len(gold["acts"]),
            "events": len(gold["events"]),
            "links": len(gold["links"]),
            "facts": len(gold["facts"]),
            "clarifications": len(gold["clarifications"]),
        },
        "observed_node_counts": {
            "acts": len(observed_acts),
            "events": len(observed_events),
            "links": len(observed_links),
            "facts": len(observed_facts),
            "clarifications": len(observed_clarifications),
        },
    }
