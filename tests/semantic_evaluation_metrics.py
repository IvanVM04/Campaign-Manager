"""Provider-agnostic ledger for semantic-understanding evaluation metrics."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from math import ceil


class SemanticEvaluationLedger:
    """Collect case, slot, discourse, operation and latency metrics.

    Metric schema v1 explicitly publishes gold/predicted denominators. Empty
    denominators remain unmeasured (None); they are never reported as 100%.
    """

    METRIC_SCHEMA_VERSION = 1

    def __init__(self) -> None:
        self._families: dict[str, dict[str, float]] = defaultdict(
            lambda: {
                "cases": 0,
                "passed_cases": 0,
                "expected_slots": 0,
                "matched_slots": 0,
                "latency_seconds": 0.0,
            }
        )
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._entity_tp = 0
        self._entity_fp = 0
        self._entity_fn = 0
        self._correct_abstentions = 0
        self._incorrect_abstentions = 0
        self._context_hits = 0
        self._context_expected = 0
        self._operation_tp = 0
        self._operation_fp = 0
        self._operation_fn = 0
        self._critical_false_persistent_changes = 0
        self._secret_leaks = 0
        self._semantic_slots: dict[str, dict[str, int]] = defaultdict(
            lambda: {"true_positive": 0, "false_positive": 0, "false_negative": 0}
        )

    def record_case(
        self,
        family: str,
        *,
        expected_slots: int,
        matched_slots: int,
        elapsed_seconds: float,
        case_passed: bool | None = None,
    ) -> None:
        """Record one case; callers can fail exact-case accuracy on extra FPs.

        `matched_slots` is bounded by the gold denominator and therefore
        measures recall. A scorer may set `case_passed=False` when it detects
        unsupported extra predictions even if all gold slots were present.
        """
        if not isinstance(family, str) or not family.strip():
            raise ValueError("family must not be empty")
        if (
            isinstance(expected_slots, bool)
            or not isinstance(expected_slots, int)
            or expected_slots < 0
            or isinstance(matched_slots, bool)
            or not isinstance(matched_slots, int)
            or not 0 <= matched_slots <= expected_slots
        ):
            raise ValueError("slot counts are inconsistent")
        if (
            isinstance(elapsed_seconds, bool)
            or not isinstance(elapsed_seconds, (int, float))
            or elapsed_seconds < 0
        ):
            raise ValueError("elapsed_seconds must be a non-negative number")
        if case_passed is not None and not isinstance(case_passed, bool):
            raise TypeError("case_passed must be a boolean or None")

        values = self._families[family]
        values["cases"] += 1
        passed = matched_slots == expected_slots if case_passed is None else case_passed
        values["passed_cases"] += int(passed)
        values["expected_slots"] += expected_slots
        values["matched_slots"] += matched_slots
        values["latency_seconds"] += float(elapsed_seconds)
        self._latencies[family].append(float(elapsed_seconds))

    def record_semantic_slots(
        self,
        family: str,
        *,
        expected_slots: Iterable[str],
        predicted_slots: Iterable[str],
    ) -> None:
        """Measure slot precision/recall with multiset matching.

        Duplicates and unsupported extras are false positives; omitted gold
        slots are false negatives. Signatures should be stable, text-free
        structural labels rather than utterances or raw model completions.
        """
        if not isinstance(family, str) or not family.strip():
            raise ValueError("family must not be empty")
        expected_values = tuple(expected_slots)
        predicted_values = tuple(predicted_slots)
        if any(
            not isinstance(item, str) or not item.strip()
            for item in (*expected_values, *predicted_values)
        ):
            raise ValueError("semantic slot signatures must be non-empty strings")
        expected = Counter(expected_values)
        predicted = Counter(predicted_values)
        matched = expected & predicted
        values = self._semantic_slots[family]
        values["true_positive"] += sum(matched.values())
        values["false_positive"] += sum((predicted - expected).values())
        values["false_negative"] += sum((expected - predicted).values())

    def record_entity_resolution(
        self,
        *,
        expected_entity_id: int | None,
        observed_entity_id: int | None,
        expected_abstention: bool,
    ) -> None:
        if expected_abstention:
            if observed_entity_id is None:
                self._correct_abstentions += 1
            else:
                self._incorrect_abstentions += 1
                self._entity_fp += 1
            return
        if expected_entity_id is None:
            raise ValueError("a resolvable case requires expected_entity_id")
        if observed_entity_id == expected_entity_id:
            self._entity_tp += 1
        else:
            self._entity_fn += 1
            if observed_entity_id is not None:
                self._entity_fp += 1

    def record_entity_group_resolution(
        self,
        *,
        expected_entity_ids: Iterable[int],
        observed_entity_ids: Iterable[int],
    ) -> None:
        """Score a plural reference as a set of distinct canonical entities."""
        expected = set(expected_entity_ids)
        observed = set(observed_entity_ids)
        for values, label in ((expected, "expected"), (observed, "observed")):
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value < 1
                for value in values
            ):
                raise ValueError(f"{label} group entity IDs must be positive integers")
        if not 2 <= len(expected) <= 8:
            raise ValueError("expected entity group must contain 2-8 unique IDs")
        self._entity_tp += len(expected & observed)
        self._entity_fp += len(observed - expected)
        self._entity_fn += len(expected - observed)

    def record_context_recall(
        self,
        *,
        expected_entity_ids: Iterable[int],
        retrieved_entity_ids: Iterable[int],
    ) -> None:
        expected = set(expected_entity_ids)
        retrieved = set(retrieved_entity_ids)
        self._context_expected += len(expected)
        self._context_hits += len(expected & retrieved)

    def record_operations(
        self,
        *,
        expected_operations: Iterable[str],
        predicted_operations: Iterable[str],
        critical_negative_control: bool = False,
    ) -> None:
        expected = set(expected_operations)
        predicted = set(predicted_operations)
        self._operation_tp += len(expected & predicted)
        false_positives = len(predicted - expected)
        self._operation_fp += false_positives
        self._operation_fn += len(expected - predicted)
        if critical_negative_control and false_positives:
            self._critical_false_persistent_changes += false_positives

    def record_secret_visibility(self, text: str, secret_markers: Iterable[str]) -> None:
        normalized = text.casefold()
        self._secret_leaks += sum(
            1
            for marker in secret_markers
            if marker and marker.casefold() in normalized
        )

    @staticmethod
    def _ratio(numerator: float, denominator: float) -> float | None:
        return None if denominator == 0 else round(numerator / denominator, 4)

    @staticmethod
    def _f1(
        true_positive: int,
        false_positive: int,
        false_negative: int,
    ) -> float | None:
        # No gold positives means that F1 is unmeasured, not a fabricated 1.0.
        if true_positive + false_negative == 0:
            return None
        denominator = 2 * true_positive + false_positive + false_negative
        return round((2 * true_positive) / denominator, 4)

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        """Return a nearest-rank percentile in seconds."""
        if not values:
            return None
        ordered = sorted(values)
        rank = max(1, ceil(percentile * len(ordered)))
        return round(ordered[rank - 1], 3)

    def summary(self) -> dict[str, object]:
        families: dict[str, dict[str, object]] = {}
        for name, values in sorted(self._families.items()):
            cases = int(values["cases"])
            slots = int(values["expected_slots"])
            latencies = self._latencies[name]
            passed_cases = int(values["passed_cases"])
            families[name] = {
                "cases": cases,
                "passed_cases": passed_cases,
                "failed_cases": cases - passed_cases,
                "case_accuracy": self._ratio(passed_cases, cases),
                "case_denominator": cases,
                "expected_slots": slots,
                "matched_slots": int(values["matched_slots"]),
                "slot_recall": self._ratio(values["matched_slots"], slots),
                "mean_latency_seconds": (
                    round(values["latency_seconds"] / cases, 3) if cases else None
                ),
                "latency_p50_seconds": self._percentile(latencies, 0.50),
                "latency_p95_seconds": self._percentile(latencies, 0.95),
                "latency_sample_count": len(latencies),
            }

        semantic_slot_quality: dict[str, dict[str, float | int | None]] = {}
        overall_tp = overall_fp = overall_fn = 0
        for family, values in sorted(self._semantic_slots.items()):
            tp = values["true_positive"]
            fp = values["false_positive"]
            fn = values["false_negative"]
            precision = self._ratio(tp, tp + fp)
            recall = self._ratio(tp, tp + fn)
            f1 = self._f1(tp, fp, fn)
            semantic_slot_quality[family] = {
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "gold_slots": tp + fn,
                "predicted_slots": tp + fp,
                "matched_slots": tp,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
            overall_tp += tp
            overall_fp += fp
            overall_fn += fn

        overall_precision = self._ratio(overall_tp, overall_tp + overall_fp)
        overall_recall = self._ratio(overall_tp, overall_tp + overall_fn)
        overall_f1 = self._f1(overall_tp, overall_fp, overall_fn)
        return {
            "metric_schema_version": self.METRIC_SCHEMA_VERSION,
            "families": families,
            "semantic_slot_quality": semantic_slot_quality,
            "semantic_slot_precision": overall_precision,
            "semantic_slot_recall": overall_recall,
            "semantic_slot_f1": overall_f1,
            "semantic_slot_gold_denominator": overall_tp + overall_fn,
            "semantic_slot_prediction_denominator": overall_tp + overall_fp,
            "entity_link_precision": self._ratio(
                self._entity_tp, self._entity_tp + self._entity_fp
            ),
            "entity_link_recall": self._ratio(
                self._entity_tp, self._entity_tp + self._entity_fn
            ),
            "correct_abstentions": self._correct_abstentions,
            "incorrect_abstentions": self._incorrect_abstentions,
            "context_recall": self._ratio(self._context_hits, self._context_expected),
            "operation_precision": self._ratio(
                self._operation_tp, self._operation_tp + self._operation_fp
            ),
            "operation_recall": self._ratio(
                self._operation_tp, self._operation_tp + self._operation_fn
            ),
            "critical_false_persistent_changes": self._critical_false_persistent_changes,
            "secret_leaks": self._secret_leaks,
        }

    def render(self) -> str:
        report = self.summary()
        lines = [f"Semantic-understanding evaluation (metric schema v{self.METRIC_SCHEMA_VERSION}):"]
        for family, values in report["families"].items():
            lines.append(
                f"- {family}: cases={values['cases']}, "
                f"passed={values['passed_cases']}, failed={values['failed_cases']}, "
                f"case_accuracy={values['case_accuracy']}, "
                f"expected_slots={values['expected_slots']}, "
                f"slot_recall={values['slot_recall']}, "
                f"latency_p50_seconds={values['latency_p50_seconds']}, "
                f"latency_p95_seconds={values['latency_p95_seconds']}"
            )
        for family, values in report["semantic_slot_quality"].items():
            lines.append(
                f"- semantic_slots[{family}]: tp={values['true_positive']}, "
                f"fp={values['false_positive']}, fn={values['false_negative']}, "
                f"gold={values['gold_slots']}, predicted={values['predicted_slots']}, "
                f"precision={values['precision']}, recall={values['recall']}, "
                f"f1={values['f1']}"
            )
        for name in (
            "semantic_slot_precision",
            "semantic_slot_recall",
            "semantic_slot_f1",
            "semantic_slot_gold_denominator",
            "semantic_slot_prediction_denominator",
            "entity_link_precision",
            "entity_link_recall",
            "correct_abstentions",
            "incorrect_abstentions",
            "context_recall",
            "operation_precision",
            "operation_recall",
            "critical_false_persistent_changes",
            "secret_leaks",
        ):
            lines.append(f"- {name}: {report[name]}")
        return "\n".join(lines)

    def emit(
        self,
        record_property: Callable[[str, object], None],
        *,
        prefix: str,
    ) -> None:
        report = self.summary()
        record_property(f"{prefix}_summary", self.render())
        for family, values in report["families"].items():
            safe_family = family.replace("-", "_")
            for metric, value in values.items():
                record_property(
                    f"{prefix}_{safe_family}_{metric}",
                    value if value is not None else "not_measured",
                )
        for family, values in report["semantic_slot_quality"].items():
            safe_family = family.replace("-", "_")
            for name, value in values.items():
                record_property(
                    f"{prefix}_{safe_family}_semantic_slots_{name}",
                    value if value is not None else "not_measured",
                )
        for metric, value in report.items():
            if metric in {"families", "semantic_slot_quality"}:
                continue
            record_property(
                f"{prefix}_{metric}",
                value if value is not None else "not_measured",
            )
