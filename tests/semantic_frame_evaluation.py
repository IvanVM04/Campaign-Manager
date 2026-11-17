"""Scoring helpers for evidence-bound semantic-frame holdouts."""

from __future__ import annotations

import re
import unicodedata

from tests.semantic_evaluation_metrics import SemanticEvaluationLedger


def _value(value):
    return value.value if hasattr(value, "value") else value


def _relation_endpoint_signature(value: str) -> str:
    """Normalize only Spanish leading articles for endpoint identity matching."""
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = re.sub(r"^[^\w]+|[^\w]+$", "", normalized)
    tokens = normalized.split()
    leading_articles = {
        "el", "la", "los", "las", "un", "una", "unos", "unas", "al", "del"
    }
    if tokens and tokens[0] in leading_articles:
        tokens = tokens[1:]
    return " ".join(tokens)


def _same_unordered_relation_endpoints(
    claim,
    subject: str,
    object_: str,
) -> bool:
    observed = sorted(
        (
            _relation_endpoint_signature(claim.subject.text),
            _relation_endpoint_signature(claim.object.text),
        )
    )
    expected = sorted(
        (
            _relation_endpoint_signature(subject),
            _relation_endpoint_signature(object_),
        )
    )
    return observed == expected


def _record_predicate_surface(
    ledger: SemanticEvaluationLedger | None,
    *,
    metric_family: str,
    scenario_id: str,
    expected: str,
    predicted: list[str],
) -> bool:
    """Record exact, case-sensitive surface-form agreement without lemmatizing."""
    matched = expected in predicted
    if ledger is not None:
        # Scenario-scoped signatures prevent another case's correct verb from
        # compensating for a mismatch in this scenario.
        expected_signature = f"{scenario_id}::{expected}"
        predicted_signatures = [f"{scenario_id}::{value}" for value in predicted]
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
        )
    return matched


def score_semantic_frame_scenario(
    analysis,
    scenario: dict,
    *,
    ledger: SemanticEvaluationLedger | None = None,
) -> tuple[int, int, list[str]]:
    """Score frames, arguments, relations and exact surface predicate spans.

    Predicate metrics are independent of frame-family and relation-direction
    metrics. This distinguishes a copied verb from a correctly understood frame.
    """
    matched = 0
    total = 0
    failures: list[str] = []
    scenario_id = scenario["id"]
    steps = () if analysis is None else analysis.steps
    frames = [step.action_frame for step in steps if step.action_frame is not None]
    claims = () if analysis is None else analysis.relation_claims

    expected_frame = scenario.get("expected_action_frame")
    if expected_frame is not None:
        total += 1
        if frames:
            matched += 1
        else:
            failures.append("action_frame: no frame returned")

        family = expected_frame.get("family")
        if family is not None:
            total += 1
            family_matches = [
                frame for frame in frames if frame.family.value == family
            ]
            if family_matches:
                matched += 1
            else:
                failures.append(
                    f"action_frame.family: expected={family!r}; "
                    f"observed={[frame.family.value for frame in frames]!r}"
                )

        expected_predicate = expected_frame.get("predicate")
        if expected_predicate is not None:
            total += 1
            predicted_predicates = [frame.predicate for frame in frames]
            predicate_matched = _record_predicate_surface(
                ledger,
                metric_family="action_frame_predicate_surface",
                scenario_id=scenario_id,
                expected=expected_predicate,
                predicted=predicted_predicates,
            )
            if predicate_matched:
                matched += 1
            else:
                failures.append(
                    "action_frame.predicate: "
                    f"expected={expected_predicate!r}; "
                    f"observed={predicted_predicates!r}"
                )

        for expected_argument in expected_frame["arguments"]:
            total += 1
            argument_matches = any(
                argument.role.value == expected_argument["role"]
                and _relation_endpoint_signature(argument.mention.text)
                == _relation_endpoint_signature(expected_argument["mention"])
                and argument.mention.kind_hint.value
                == expected_argument["kind_hint"]
                for frame in frames
                for argument in frame.arguments
            )
            if argument_matches:
                matched += 1
            else:
                failures.append(
                    f"action_frame.argument: expected={expected_argument!r}"
                )

    expected_relation = scenario.get("expected_relation")
    if expected_relation is not None:
        subject = expected_relation["subject"].casefold()
        object_ = expected_relation["object"].casefold()
        direction_matches = [
            claim for claim in claims
            if (
                _relation_endpoint_signature(claim.subject.text)
                == _relation_endpoint_signature(subject)
                and _relation_endpoint_signature(claim.object.text)
                == _relation_endpoint_signature(object_)
            )
        ]
        unordered_endpoint_matches = [
            claim for claim in claims
            if _same_unordered_relation_endpoints(claim, subject, object_)
        ]
        total += 1
        if direction_matches:
            matched += 1
        else:
            failures.append(
                "relation direction: expected="
                f"({expected_relation['subject']!r}, {expected_relation['object']!r}) "
                "observed="
                f"{[(claim.subject.text, claim.object.text) for claim in claims]!r}"
            )

        expected_predicate = expected_relation.get("predicate")
        if expected_predicate is not None:
            total += 1
            predicted_predicates = [
                claim.predicate for claim in unordered_endpoint_matches
            ]
            predicate_matched = _record_predicate_surface(
                ledger,
                metric_family="relation_predicate_surface",
                scenario_id=scenario_id,
                expected=expected_predicate,
                predicted=predicted_predicates,
            )
            if predicate_matched:
                matched += 1
            else:
                failures.append(
                    "relation.predicate: "
                    f"expected={expected_predicate!r}; "
                    f"observed={predicted_predicates!r}"
                )

        for field, wanted in expected_relation.items():
            if field in {"subject", "object", "predicate"}:
                continue
            total += 1
            observed_values = []
            # Family, polarity, modality and attribution belong to the
            # relation claim regardless of which endpoint the model placed first.
            for claim in unordered_endpoint_matches:
                if field == "attributed_to":
                    observed = (
                        None if claim.attributed_to is None
                        else claim.attributed_to.text
                    )
                else:
                    observed = getattr(claim, field, None)
                    observed = _value(observed)
                observed_values.append(observed)
            if any(
                (observed.casefold() if isinstance(observed, str) else observed)
                == (wanted.casefold() if isinstance(wanted, str) else wanted)
                for observed in observed_values
            ):
                matched += 1
            else:
                failures.append(
                    f"relation.{field}: expected={wanted!r} "
                    f"observed={observed_values!r}"
                )
    return matched, total, failures
