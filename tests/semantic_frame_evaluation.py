"""Scoring helpers for complete, evidence-bound semantic-frame holdouts."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

_FIXTURES = Path(__file__).parent / "fixtures"
_PRESENCE_GOLD = _FIXTURES / "semantic_frame_presence_gold_v1.json"
_MAX_PREDICTIONS = 8


def load_semantic_frame_presence_gold(
    corpus: dict[str, Any],
    *,
    path: str | Path = _PRESENCE_GOLD,
) -> dict[str, dict[str, int]]:
    """Load explicit frame/claim count gold; missing labels are never negatives."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != 1
        or payload.get("split") != "held_out_annotations"
        or payload.get("source_corpus") != "semantic_frame_corpus_holdout_v1.json"
    ):
        raise ValueError("unsupported semantic-frame presence gold contract")

    entries = payload.get("scenarios")
    scenarios = corpus.get("scenarios")
    if not isinstance(entries, list) or not isinstance(scenarios, list):
        raise TypeError("semantic-frame corpus and presence gold must contain arrays")

    corpus_ids = [item.get("id") for item in scenarios if isinstance(item, dict)]
    gold_ids = [item.get("id") for item in entries if isinstance(item, dict)]
    if (
        len(corpus_ids) != len(scenarios)
        or len(gold_ids) != len(entries)
        or any(not isinstance(value, str) or not value.strip() for value in corpus_ids + gold_ids)
        or len(set(corpus_ids)) != len(corpus_ids)
        or len(set(gold_ids)) != len(gold_ids)
        or set(corpus_ids) != set(gold_ids)
    ):
        raise ValueError("semantic-frame presence gold must cover every scenario exactly")

    result: dict[str, dict[str, int]] = {}
    for entry in entries:
        if set(entry) != {
            "id", "expected_action_frame_count", "expected_relation_count"
        }:
            raise ValueError("presence gold entries have an invalid field contract")
        counts: dict[str, int] = {}
        for field in ("expected_action_frame_count", "expected_relation_count"):
            value = entry[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= _MAX_PREDICTIONS
            ):
                raise ValueError(f"{field} must be an integer between 0 and 8")
            counts[field] = value
        source = next(item for item in scenarios if item["id"] == entry["id"])
        detailed_frames = len(_expected_list(source.get("expected_action_frame"), "expected_action_frame"))
        detailed_relations = len(_expected_list(source.get("expected_relation"), "expected_relation"))
        if detailed_frames > counts["expected_action_frame_count"]:
            raise ValueError("frame field gold exceeds its explicit count gold")
        if detailed_relations > counts["expected_relation_count"]:
            raise ValueError("relation field gold exceeds its explicit count gold")
        result[entry["id"]] = counts
    return result


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _label(value: Any) -> str:
    value = _value(value)
    if value is None:
        return "<none>"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int)):
        return str(value)
    raise TypeError("semantic evaluation values must be scalar")


def _relation_endpoint_signature(value: str) -> str:
    """Normalize NFKC/case and leading Spanish articles for entity mentions."""
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = re.sub(r"^[^\w]+|[^\w]+$", "", normalized)
    tokens = normalized.split()
    leading_articles = {
        "el", "la", "los", "las", "un", "una", "unos", "unas", "al", "del"
    }
    if tokens and tokens[0] in leading_articles:
        tokens = tokens[1:]
    return " ".join(tokens)


def _record_slots(
    ledger: SemanticEvaluationLedger | None,
    family: str,
    expected: tuple[str, ...],
    predicted: tuple[str, ...],
) -> None:
    if ledger is not None:
        ledger.record_semantic_slots(
            family,
            expected_slots=expected,
            predicted_slots=predicted,
        )


def _record_predicate_surface(
    ledger: SemanticEvaluationLedger | None,
    *,
    metric_family: str,
    scenario_id: str,
    expected: str,
    predicted: list[str],
) -> bool:
    """Record exact, case-sensitive written-form agreement independently."""
    matched = expected in predicted
    if ledger is not None:
        expected_signature = f"{scenario_id}::{expected}"
        predicted_signatures = tuple(
            f"{scenario_id}::{value}" for value in predicted
        )
        ledger.record_semantic_slots(
            metric_family,
            expected_slots=(expected_signature,),
            predicted_slots=predicted_signatures,
        )
        ledger.record_case(
            f"predicate_surface:{metric_family}",
            expected_slots=1,
            matched_slots=int(matched),
            elapsed_seconds=0,
            case_passed=matched,
        )
    return matched


def _expected_list(value: Any, field_name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    raise TypeError(f"{field_name} gold must be an object, an array of objects or null")


def _expected_count(
    value: int | None,
    *,
    detailed_count: int,
    field_name: str,
) -> int | None:
    if value is None:
        return detailed_count if detailed_count else None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not detailed_count <= value <= _MAX_PREDICTIONS
    ):
        raise ValueError(f"{field_name} must be between detailed gold count and 8")
    return value


def _argument_signature(argument: Any) -> str:
    role = _label(getattr(argument, "role", None))
    mention = getattr(argument, "mention", None)
    mention_text = getattr(mention, "text", None)
    kind_hint = _label(getattr(mention, "kind_hint", None))
    return (
        f"role={role}|mention={_relation_endpoint_signature(mention_text)}"
        f"|kind={kind_hint}"
    )


def _expected_argument_signature(argument: dict[str, Any]) -> str:
    role = argument["role"]
    mention = argument["mention"]
    kind_hint = argument["kind_hint"]
    return (
        f"role={role}|mention={_relation_endpoint_signature(mention)}"
        f"|kind={kind_hint}"
    )


def _frame_signature(frame: Any, index: int, *, expected: dict[str, Any]) -> str:
    """Project an observed frame onto fields which have independent gold."""
    values = [f"frame:{index}", f"family={_label(getattr(frame, 'family', None))}"]
    if "predicate" in expected:
        values.append(f"predicate={getattr(frame, 'predicate', None)}")
    if "arguments" in expected:
        arguments = sorted(
            _argument_signature(argument)
            for argument in getattr(frame, "arguments", ())
        )
        values.append(f"arguments={arguments!r}")
    return "|".join(values)


def _expected_frame_signature(frame: dict[str, Any], index: int) -> str:
    values = [f"frame:{index}", f"family={frame['family']}"]
    if "predicate" in frame:
        values.append(f"predicate={frame['predicate']}")
    if "arguments" in frame:
        arguments = sorted(
            _expected_argument_signature(argument)
            for argument in frame["arguments"]
        )
        values.append(f"arguments={arguments!r}")
    return "|".join(values)


def _relation_field_value(claim: Any, field: str) -> Any:
    if field in {"subject", "object"}:
        mention = getattr(claim, field, None)
        text = getattr(mention, "text", None)
        return _relation_endpoint_signature(text) if isinstance(text, str) else None
    if field == "attributed_to":
        mention = getattr(claim, "attributed_to", None)
        value = getattr(mention, "text", None)
        return _relation_endpoint_signature(value) if isinstance(value, str) else None
    value = getattr(claim, field, None)
    if field == "relation_family":
        return _value(value)
    if field == "temporal_expression" and isinstance(value, str):
        return unicodedata.normalize("NFKC", value).casefold().strip()
    return _value(value)


def _expected_relation_field_value(relation: dict[str, Any], field: str) -> Any:
    value = relation[field]
    if field in {"subject", "object", "attributed_to"}:
        return _relation_endpoint_signature(value) if value is not None else None
    if field == "temporal_expression" and isinstance(value, str):
        return unicodedata.normalize("NFKC", value).casefold().strip()
    return value


def _relation_signature(
    claim: Any,
    index: int,
    *,
    expected: dict[str, Any],
) -> str:
    fields = (
        "subject", "object", "predicate", "relation_family",
        "polarity", "modality", "attributed_to", "temporal_expression",
        "step_index",
    )
    values = [f"claim:{index}"]
    for field in fields:
        if field not in expected:
            continue
        if field == "predicate":
            observed = getattr(claim, "predicate", None)
        elif field == "step_index":
            observed = getattr(claim, "step_index", None)
        else:
            observed = _relation_field_value(claim, field)
        values.append(f"{field}={_label(observed)}")
    return "|".join(values)


def _expected_relation_signature(relation: dict[str, Any], index: int) -> str:
    fields = (
        "subject", "object", "predicate", "relation_family",
        "polarity", "modality", "attributed_to", "temporal_expression",
        "step_index",
    )
    values = [f"claim:{index}"]
    for field in fields:
        if field in relation:
            values.append(
                f"{field}={_label(_expected_relation_field_value(relation, field))}"
            )
    return "|".join(values)


def score_semantic_frame_scenario(
    analysis: Any,
    scenario: dict[str, Any],
    *,
    expected_action_frame_count: int | None = None,
    expected_relation_count: int | None = None,
    ledger: SemanticEvaluationLedger | None = None,
) -> tuple[int, int, list[str]]:
    """Score explicit counts and every independently golded frame/relation slot.

    Count gold is separate from detailed semantic gold. An absent detailed field
    is unmeasured unless an explicit count sidecar provides its expected
    cardinality. Frame/claim/argument extras and duplicates are false positives;
    missing detailed gold is a false negative. Unannotated fields stay unmeasured.
    """
    matched = 0
    total = 0
    failures: list[str] = []
    scenario_id = scenario["id"]
    family = scenario.get("family", "unclassified")
    if not isinstance(family, str) or not family.strip():
        raise ValueError("scenario family must be a non-empty string when supplied")
    steps = () if analysis is None else tuple(getattr(analysis, "steps", ()))
    frames = [
        step.action_frame
        for step in steps
        if getattr(step, "action_frame", None) is not None
    ]
    claims = () if analysis is None else tuple(getattr(analysis, "relation_claims", ()))
    expected_frames = _expected_list(
        scenario.get("expected_action_frame"), "expected_action_frame"
    )
    expected_relations = _expected_list(
        scenario.get("expected_relation"), "expected_relation"
    )
    expected_action_frame_count = _expected_count(
        expected_action_frame_count,
        detailed_count=len(expected_frames),
        field_name="expected_action_frame_count",
    )
    expected_relation_count = _expected_count(
        expected_relation_count,
        detailed_count=len(expected_relations),
        field_name="expected_relation_count",
    )

    if expected_action_frame_count is not None:
        total += 1
        count_matches = len(frames) == expected_action_frame_count
        if count_matches:
            matched += 1
        else:
            failures.append(
                f"action_frame.count: expected={expected_action_frame_count} "
                f"observed={len(frames)}"
            )
        _record_slots(
            ledger,
            f"action_frame_presence:{family}",
            tuple(f"frame:{index}" for index in range(expected_action_frame_count)),
            tuple(f"frame:{index}" for index in range(len(frames))),
        )

    # Detailed frame semantics are scored only where independent frame gold exists.
    if expected_frames:
        comparable_frames = frames[:len(expected_frames)]
        expected_frame_signatures = tuple(
            _expected_frame_signature(frame, index)
            for index, frame in enumerate(expected_frames)
        )
        predicted_frame_signatures = tuple(
            _frame_signature(frame, index, expected=expected_frames[index])
            for index, frame in enumerate(comparable_frames)
        )
        _record_slots(
            ledger,
            f"action_frame_exact:{family}",
            expected_frame_signatures,
            predicted_frame_signatures,
        )
        if Counter(expected_frame_signatures) != Counter(predicted_frame_signatures):
            failures.append("action_frame: one or more frames have wrong semantics")

        expected_families = tuple(
            f"frame:{index}|family|{frame['family']}"
            for index, frame in enumerate(expected_frames)
        )
        predicted_families = tuple(
            f"frame:{index}|family|{_label(frame.family)}"
            for index, frame in enumerate(comparable_frames)
        )
        _record_slots(
            ledger,
            f"action_frame_family:{family}",
            expected_families,
            predicted_families,
        )

        expected_arguments: list[str] = []
        predicted_arguments: list[str] = []
        for index, frame in enumerate(expected_frames):
            if "arguments" not in frame:
                continue
            expected_arguments.extend(
                f"frame:{index}|{_expected_argument_signature(argument)}"
                for argument in frame["arguments"]
            )
            actual = comparable_frames[index] if index < len(comparable_frames) else None
            predicted_arguments.extend(
                f"frame:{index}|{_argument_signature(argument)}"
                for argument in (() if actual is None else getattr(actual, "arguments", ()))
            )
        _record_slots(
            ledger,
            f"action_arguments:{family}",
            tuple(expected_arguments),
            tuple(predicted_arguments),
        )
        if Counter(expected_arguments) != Counter(predicted_arguments):
            failures.append("action_frame.arguments: missing, extra or duplicate arguments")

        for index, expected_frame in enumerate(expected_frames):
            actual = comparable_frames[index] if index < len(comparable_frames) else None
            total += 1
            observed_family = (
                _value(getattr(actual, "family", None)) if actual is not None else None
            )
            if actual is not None and observed_family == expected_frame["family"]:
                matched += 1
            else:
                failures.append(
                    f"action_frame.family[{index}]: expected={expected_frame['family']!r} "
                    f"observed={observed_family!r}"
                )

            expected_predicate = expected_frame.get("predicate")
            if expected_predicate is not None:
                total += 1
                predicted_predicate = (
                    getattr(actual, "predicate", None) if actual is not None else None
                )
                predicate_matched = _record_predicate_surface(
                    ledger,
                    metric_family="action_frame_predicate_surface",
                    scenario_id=f"{scenario_id}:{index}",
                    expected=expected_predicate,
                    predicted=(
                        [predicted_predicate]
                        if isinstance(predicted_predicate, str)
                        else []
                    ),
                )
                if predicate_matched:
                    matched += 1
                else:
                    failures.append(
                        f"action_frame.predicate[{index}]: expected={expected_predicate!r} "
                        f"observed={predicted_predicate!r}"
                    )

            expected_args = expected_frame.get("arguments")
            if expected_args is not None:
                actual_args = (
                    tuple(getattr(actual, "arguments", ())) if actual is not None else ()
                )
                expected_arg_signatures = Counter(
                    _expected_argument_signature(argument) for argument in expected_args
                )
                actual_arg_signatures = Counter(
                    _argument_signature(argument) for argument in actual_args
                )
                for signature, count in expected_arg_signatures.items():
                    total += count
                    matched += min(count, actual_arg_signatures[signature])

    if expected_relation_count is not None:
        total += 1
        count_matches = len(claims) == expected_relation_count
        if count_matches:
            matched += 1
        else:
            failures.append(
                f"relation.count: expected={expected_relation_count} observed={len(claims)}"
            )
        _record_slots(
            ledger,
            f"relation_presence:{family}",
            tuple(f"claim:{index}" for index in range(expected_relation_count)),
            tuple(f"claim:{index}" for index in range(len(claims))),
        )

    # Detailed relation semantics are measured only for relations with gold.
    if expected_relations:
        comparable_claims = claims[:len(expected_relations)]
        expected_signatures = tuple(
            _expected_relation_signature(relation, index)
            for index, relation in enumerate(expected_relations)
        )
        predicted_signatures = tuple(
            _relation_signature(claim, index, expected=expected_relations[index])
            for index, claim in enumerate(comparable_claims)
        )
        _record_slots(
            ledger,
            f"relation_exact:{family}",
            expected_signatures,
            predicted_signatures,
        )
        if Counter(expected_signatures) != Counter(predicted_signatures):
            failures.append("relation: one or more claims have wrong semantics")

        expected_directions = tuple(
            (
                f"claim:{index}|subject|{_relation_endpoint_signature(item['subject'])}"
                f"|object|{_relation_endpoint_signature(item['object'])}"
            )
            for index, item in enumerate(expected_relations)
        )
        predicted_directions = tuple(
            (
                f"claim:{index}|subject|{_relation_endpoint_signature(claim.subject.text)}"
                f"|object|{_relation_endpoint_signature(claim.object.text)}"
            )
            for index, claim in enumerate(comparable_claims)
        )
        _record_slots(
            ledger,
            f"relation_direction:{family}",
            expected_directions,
            predicted_directions,
        )

        for index, expected_relation in enumerate(expected_relations):
            actual = comparable_claims[index] if index < len(comparable_claims) else None
            total += 1
            expected_direction = (
                _relation_endpoint_signature(expected_relation["subject"]),
                _relation_endpoint_signature(expected_relation["object"]),
            )
            observed_direction = (
                (
                    _relation_endpoint_signature(actual.subject.text),
                    _relation_endpoint_signature(actual.object.text),
                )
                if actual is not None
                else None
            )
            if observed_direction == expected_direction:
                matched += 1
            else:
                failures.append(
                    f"relation direction[{index}]: expected={expected_direction!r} "
                    f"observed={observed_direction!r}"
                )

            expected_predicate = expected_relation.get("predicate")
            if expected_predicate is not None:
                total += 1
                predicted_predicate = (
                    getattr(actual, "predicate", None) if actual is not None else None
                )
                predicate_matches = _record_predicate_surface(
                    ledger,
                    metric_family="relation_predicate_surface",
                    scenario_id=f"{scenario_id}:{index}",
                    expected=expected_predicate,
                    predicted=(
                        [predicted_predicate]
                        if isinstance(predicted_predicate, str)
                        else []
                    ),
                )
                if predicate_matches:
                    matched += 1
                else:
                    failures.append(
                        f"relation.predicate[{index}]: expected={expected_predicate!r} "
                        f"observed={predicted_predicate!r}"
                    )

            for field in (
                "relation_family",
                "polarity",
                "modality",
                "attributed_to",
                "temporal_expression",
                "step_index",
            ):
                if field not in expected_relation:
                    continue
                total += 1
                wanted = _expected_relation_field_value(expected_relation, field)
                observed = _relation_field_value(actual, field) if actual is not None else None
                expected_signature = f"claim:{index}|{field}|{_label(wanted)}"
                if actual is not None:
                    predicted_signature = (
                        f"claim:{index}|{field}|"
                        f"{_label(_relation_field_value(actual, field))}"
                    )
                    predicted_signatures = (predicted_signature,)
                else:
                    predicted_signatures = ()
                _record_slots(
                    ledger,
                    f"relation_{field}:{family}",
                    (expected_signature,),
                    predicted_signatures,
                )
                if actual is not None and observed == wanted:
                    matched += 1
                else:
                    failures.append(
                        f"relation.{field}[{index}]: expected={wanted!r} observed={observed!r}"
                    )

    return matched, total, failures
