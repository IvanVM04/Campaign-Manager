"""Scoring helpers for complete, evidence-bound semantic-frame holdouts."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

from tests.semantic_evaluation_metrics import SemanticEvaluationLedger


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


def _same_unordered_relation_endpoints(claim: Any, subject: str, object_: str) -> bool:
    observed = sorted((
        _relation_endpoint_signature(claim.subject.text),
        _relation_endpoint_signature(claim.object.text),
    ))
    expected = sorted((
        _relation_endpoint_signature(subject),
        _relation_endpoint_signature(object_),
    ))
    return observed == expected


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
    ledger: SemanticEvaluationLedger | None = None,
) -> tuple[int, int, list[str]]:
    """Score complete frame/relation counts and all independently-golded slots.

    Frame/claim and argument collections use multiset matching: duplicates and
    unsupported extras are false positives. Direction is scored separately
    from relation family/predicate/polarity so diagnostics remain actionable.
    A missing expected field is unmeasured, not implicitly correct.
    """
    matched = 0
    total = 0
    failures: list[str] = []
    scenario_id = scenario["id"]
    family = scenario["family"]
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

    # Frame count and presence are exact, including scenarios with no frame gold.
    total += 1
    frame_count_matches = len(frames) == len(expected_frames)
    if frame_count_matches:
        matched += 1
    else:
        failures.append(
            f"action_frame.count: expected={len(expected_frames)} observed={len(frames)}"
        )
    _record_slots(
        ledger,
        f"action_frame_presence:{family}",
        tuple(f"frame:{index}" for index in range(len(expected_frames))),
        tuple(f"frame:{index}" for index in range(len(frames))),
    )

    expected_frame_signatures = tuple(
        _expected_frame_signature(frame, index)
        for index, frame in enumerate(expected_frames)
    )
    predicted_frame_signatures = tuple(
        _frame_signature(
            frame,
            index,
            expected=expected_frames[index] if index < len(expected_frames) else {},
        )
        for index, frame in enumerate(frames)
    )
    _record_slots(
        ledger,
        f"action_frame_exact:{family}",
        expected_frame_signatures,
        predicted_frame_signatures,
    )
    if Counter(expected_frame_signatures) != Counter(predicted_frame_signatures):
        failures.append("action_frame: one or more frames have wrong or extra semantics")

    expected_families = tuple(
        f"frame:{index}|family|{frame['family']}"
        for index, frame in enumerate(expected_frames)
    )
    predicted_families = tuple(
        f"frame:{index}|family|{_label(frame.family)}"
        for index, frame in enumerate(frames)
    )
    _record_slots(
        ledger,
        f"action_frame_family:{family}",
        expected_families,
        predicted_families,
    )

    expected_arguments: list[str] = []
    for index, frame in enumerate(expected_frames):
        if "arguments" in frame:
            expected_arguments.extend(
                f"frame:{index}|{_expected_argument_signature(argument)}"
                for argument in frame["arguments"]
            )
    predicted_arguments = [
        f"frame:{index}|{_argument_signature(argument)}"
        for index, frame in enumerate(frames)
        for argument in getattr(frame, "arguments", ())
    ]
    _record_slots(
        ledger,
        f"action_arguments:{family}",
        tuple(expected_arguments),
        tuple(predicted_arguments),
    )
    if Counter(expected_arguments) != Counter(predicted_arguments):
        failures.append("action_frame.arguments: missing, extra or duplicate arguments")

    for index, expected_frame in enumerate(expected_frames):
        actual = frames[index] if index < len(frames) else None
        total += 1
        observed_family = _value(getattr(actual, "family", None)) if actual is not None else None
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
            predicted_predicates = [
                getattr(frame, "predicate", None) for frame in frames
            ]
            predicate_matched = _record_predicate_surface(
                ledger,
                metric_family="action_frame_predicate_surface",
                scenario_id=f"{scenario_id}:{index}",
                expected=expected_predicate,
                predicted=[
                    value for value in predicted_predicates if isinstance(value, str)
                ],
            )
            if predicate_matched:
                matched += 1
            else:
                failures.append(
                    f"action_frame.predicate[{index}]: expected={expected_predicate!r} "
                    f"observed={predicted_predicates!r}"
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

    # Relation count and exact relation signatures include unsupported extras.
    total += 1
    relation_count_matches = len(claims) == len(expected_relations)
    if relation_count_matches:
        matched += 1
    else:
        failures.append(
            f"relation.count: expected={len(expected_relations)} observed={len(claims)}"
        )
    _record_slots(
        ledger,
        f"relation_presence:{family}",
        tuple(f"claim:{index}" for index in range(len(expected_relations))),
        tuple(f"claim:{index}" for index in range(len(claims))),
    )
    _record_slots(
        ledger,
        f"relation_exact:{family}",
        tuple(
            _expected_relation_signature(relation, index)
            for index, relation in enumerate(expected_relations)
        ),
        tuple(
            _relation_signature(
                claim,
                index,
                expected=expected_relations[index] if index < len(expected_relations) else {},
            )
            for index, claim in enumerate(claims)
        ),
    )
    if Counter(
        _expected_relation_signature(relation, index)
        for index, relation in enumerate(expected_relations)
    ) != Counter(
        _relation_signature(
            claim,
            index,
            expected=expected_relations[index] if index < len(expected_relations) else {},
        )
        for index, claim in enumerate(claims)
    ):
        failures.append("relation: one or more claims have wrong or extra semantics")

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
        for index, claim in enumerate(claims)
    )
    _record_slots(
        ledger,
        f"relation_direction:{family}",
        expected_directions,
        predicted_directions,
    )

    for index, expected_relation in enumerate(expected_relations):
        actual = claims[index] if index < len(claims) else None
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
            predicates = [
                getattr(claim, "predicate", None) for claim in claims
            ]
            predicate_matches = _record_predicate_surface(
                ledger,
                metric_family="relation_predicate_surface",
                scenario_id=f"{scenario_id}:{index}",
                expected=expected_predicate,
                predicted=[value for value in predicates if isinstance(value, str)],
            )
            if predicate_matches:
                matched += 1
            else:
                failures.append(
                    f"relation.predicate[{index}]: expected={expected_predicate!r} "
                    f"observed={predicates!r}"
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
            predicted_signatures = tuple(
                f"claim:{claim_index}|{field}|{_label(_relation_field_value(claim, field))}"
                for claim_index, claim in enumerate(claims)
            )
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
