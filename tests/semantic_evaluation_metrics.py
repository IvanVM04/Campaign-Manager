"""Small, provider-agnostic metrics ledger for semantic-understanding evaluations."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable


class SemanticEvaluationLedger:
    """Collect comparable case, slot, discourse, operation and latency metrics."""

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
    ) -> None:
        if not family.strip():
            raise ValueError("family must not be empty")
        if expected_slots < 0 or not 0 <= matched_slots <= expected_slots:
            raise ValueError("slot counts are inconsistent")
        if elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must not be negative")
        values = self._families[family]
        values["cases"] += 1
        values["passed_cases"] += int(matched_slots == expected_slots)
        values["expected_slots"] += expected_slots
        values["matched_slots"] += matched_slots
        values["latency_seconds"] += elapsed_seconds

    def record_semantic_slots(
        self,
        family: str,
        *,
        expected_slots: Iterable[str],
        predicted_slots: Iterable[str],
    ) -> None:
        """Measure semantic-slot precision/recall, including unsupported extras.

        Counter-based matching preserves multiplicity: a model cannot receive
        full precision by returning every expected role plus duplicate or
        invented arguments/relations.
        """
        if not isinstance(family, str) or not family.strip():
            raise ValueError("family must not be empty")
        expected = Counter(expected_slots)
        predicted = Counter(predicted_slots)
        if any(not isinstance(item, str) or not item.strip() for item in (*expected, *predicted)):
            raise ValueError("semantic slot signatures must be non-empty strings")
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

    def summary(self) -> dict[str, object]:
        families: dict[str, dict[str, object]] = {}
        for name, values in sorted(self._families.items()):
            cases = values["cases"]
            slots = values["expected_slots"]
            families[name] = {
                "cases": int(cases),
                "case_accuracy": self._ratio(values["passed_cases"], cases),
                "expected_slots": int(slots),
                "slot_recall": self._ratio(values["matched_slots"], slots),
                "mean_latency_seconds": (
                    round(values["latency_seconds"] / cases, 3)
                    if cases
                    else None
                ),
            }
        semantic_slot_quality: dict[str, dict[str, float | int | None]] = {}
        overall_tp = overall_fp = overall_fn = 0
        for family, values in sorted(self._semantic_slots.items()):
            tp, fp, fn = (
                values["true_positive"],
                values["false_positive"],
                values["false_negative"],
            )
            precision = self._ratio(tp, tp + fp)
            recall = self._ratio(tp, tp + fn)
            f1 = (
                None
                if precision is None or recall is None or precision + recall == 0
                else round(2 * precision * recall / (precision + recall), 4)
            )
            semantic_slot_quality[family] = {
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
            overall_tp += tp
            overall_fp += fp
            overall_fn += fn
        overall_precision = self._ratio(overall_tp, overall_tp + overall_fp)
        overall_recall = self._ratio(overall_tp, overall_tp + overall_fn)
        overall_f1 = (
            None
            if overall_precision is None or overall_recall is None or overall_precision + overall_recall == 0
            else round(2 * overall_precision * overall_recall / (overall_precision + overall_recall), 4)
        )
        return {
            "families": families,
            "semantic_slot_quality": semantic_slot_quality,
            "semantic_slot_precision": overall_precision,
            "semantic_slot_recall": overall_recall,
            "semantic_slot_f1": overall_f1,
            "entity_link_precision": self._ratio(
                self._entity_tp, self._entity_tp + self._entity_fp
            ),
            "entity_link_recall": self._ratio(
                self._entity_tp, self._entity_tp + self._entity_fn
            ),
            "correct_abstentions": self._correct_abstentions,
            "incorrect_abstentions": self._incorrect_abstentions,
            "context_recall": self._ratio(
                self._context_hits, self._context_expected
            ),
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
        lines = ["Semantic-understanding evaluation:"]
        for family, values in report["families"].items():
            lines.append(
                f"- {family}: cases={values['cases']}, "
                f"case_accuracy={values['case_accuracy']}, "
                f"slot_recall={values['slot_recall']}, "
                f"mean_latency_seconds={values['mean_latency_seconds']}"
            )
        for family, values in report["semantic_slot_quality"].items():
            lines.append(
                f"- semantic_slots[{family}]: "
                f"precision={values['precision']}, recall={values['recall']}, "
                f"f1={values['f1']}, fp={values['false_positive']}, "
                f"fn={values['false_negative']}"
            )
        for name in (
            "semantic_slot_precision",
            "semantic_slot_recall",
            "semantic_slot_f1",
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
