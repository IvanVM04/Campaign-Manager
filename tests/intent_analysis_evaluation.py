"""Complete, gold-driven scoring for ordered player-intent analyses.

This module is evaluation-only. It never changes prompts or production intent
normalization and never persists player text or raw model output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).parent / "fixtures"
_STEP_COUNT_GOLD = _FIXTURES / "language_understanding_step_count_gold_v1.json"
_MAX_STEPS = 8
_ALLOWED_STEP_FIELDS = frozenset({
    "actor",
    "modality",
    "polarity",
    "reported_outcome",
    "attributed_to",
})


def _value(value: Any) -> Any:
    """Read enum values without depending on a particular enum class."""
    return getattr(value, "value", value)


def _label(value: Any) -> str:
    """Encode a metric value as a bounded scalar label."""
    value = _value(value)
    if value is None:
        return "<none>"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int)):
        return str(value)
    raise TypeError("intent evaluation fields must be scalar values")


def load_language_step_count_gold(
    corpus: dict[str, Any],
    *,
    path: str | Path = _STEP_COUNT_GOLD,
) -> dict[str, int]:
    """Load the text-free step-count sidecar and require exact corpus coverage."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != 1
        or payload.get("split") != "held_out_annotations"
        or payload.get("source_corpus") != "language_understanding_corpus_holdout_v1.json"
    ):
        raise ValueError("unsupported language step-count gold contract")
    entries = payload.get("scenarios")
    scenarios = corpus.get("scenarios")
    if not isinstance(entries, list) or not isinstance(scenarios, list):
        raise TypeError("language corpus and step-count gold must contain scenario arrays")

    corpus_ids = [item.get("id") for item in scenarios if isinstance(item, dict)]
    gold_ids = [item.get("id") for item in entries if isinstance(item, dict)]
    if (
        len(corpus_ids) != len(scenarios)
        or len(gold_ids) != len(entries)
        or any(not isinstance(item, str) or not item.strip() for item in corpus_ids + gold_ids)
        or len(set(corpus_ids)) != len(corpus_ids)
        or len(set(gold_ids)) != len(gold_ids)
        or set(corpus_ids) != set(gold_ids)
    ):
        raise ValueError("language step-count gold must cover every corpus scenario exactly")

    result: dict[str, int] = {}
    for entry in entries:
        if set(entry) != {"id", "step_count"}:
            raise ValueError("step-count gold entries may contain only id and step_count")
        count = entry["step_count"]
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 0 <= count <= _MAX_STEPS
        ):
            raise ValueError("step_count gold must be an integer between 0 and 8")
        result[entry["id"]] = count
    return result


def _step_gold_by_index(expected: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Merge the legacy step/first_step/later_step gold aliases by ordered index."""
    active_index = expected["active_step_index"]
    aliases = (
        ("step", active_index if active_index is not None else 0),
        ("first_step", 0),
        ("later_step", 1),
    )
    result: dict[int, dict[str, Any]] = {}
    for key, index in aliases:
        fields = expected.get(key)
        if fields is None:
            continue
        if not isinstance(fields, dict) or set(fields) - _ALLOWED_STEP_FIELDS:
            raise ValueError(f"{key} contains unsupported step gold fields")
        target = result.setdefault(index, {})
        for field, wanted in fields.items():
            if field in target and target[field] != wanted:
                raise ValueError(f"conflicting {field} gold for step {index}")
            target[field] = wanted
    return result


def score_intent_analysis(
    analysis: Any,
    *,
    expected: dict[str, Any],
    expected_step_count: int,
    family: str,
    ledger: Any,
    elapsed_seconds: float = 0.0,
) -> tuple[int, int, tuple[str, ...]]:
    """Score global intent fields, exact ordered step count and every gold step slot.

    Unannotated fields are intentionally not scored. Every expected field is
    compared at its gold step index, never at an index selected by the model.
    Step presence is multiset-scored, so missing and extra steps become FN/FP.
    """
    if not isinstance(expected, dict) or not {
        "category", "active_step_index", "requires_clarification"
    }.issubset(expected):
        raise ValueError("language expected contract is incomplete")
    if not isinstance(family, str) or not family.strip():
        raise ValueError("family must not be empty")
    if (
        isinstance(expected_step_count, bool)
        or not isinstance(expected_step_count, int)
        or not 0 <= expected_step_count <= _MAX_STEPS
    ):
        raise ValueError("expected_step_count must be an integer between 0 and 8")

    steps = tuple(getattr(analysis, "steps", ())) if analysis is not None else ()
    if len(steps) > _MAX_STEPS:
        raise ValueError("observed step count exceeds the PlayerIntentAnalysis limit")
    failures: list[str] = []
    matched = 0
    total = 0

    global_fields = ("category", "active_step_index", "requires_clarification")
    for field in global_fields:
        wanted = expected[field]
        observed = _value(getattr(analysis, field, None)) if analysis is not None else None
        total += 1
        if observed == wanted:
            matched += 1
        else:
            failures.append(f"{field}: expected={wanted!r} observed={observed!r}")
        ledger.record_semantic_slots(
            f"intent_{field}:{family}",
            expected_slots=(f"{field}|{_label(wanted)}",),
            predicted_slots=(f"{field}|{_label(observed)}",) if analysis is not None else (),
        )

    expected_count_signature = f"step_count|{expected_step_count}"
    observed_count_signature = f"step_count|{len(steps)}"
    total += 1
    count_matches = len(steps) == expected_step_count
    if count_matches:
        matched += 1
    else:
        failures.append(
            f"step_count: expected={expected_step_count} observed={len(steps)}"
        )
    ledger.record_semantic_slots(
        f"intent_step_count:{family}",
        expected_slots=(expected_count_signature,),
        predicted_slots=(observed_count_signature,),
    )

    ledger.record_semantic_slots(
        f"intent_step_presence:{family}",
        expected_slots=tuple(f"step:{index}" for index in range(expected_step_count)),
        predicted_slots=tuple(f"step:{index}" for index in range(len(steps))),
    )

    step_gold = _step_gold_by_index(expected)
    if any(index >= expected_step_count for index in step_gold):
        raise ValueError("step gold references an index outside expected_step_count")

    for index, fields in sorted(step_gold.items()):
        actual = steps[index] if index < len(steps) else None
        for field, wanted in sorted(fields.items()):
            observed = (
                _value(getattr(actual, field, None))
                if actual is not None
                else None
            )
            total += 1
            if actual is not None and observed == wanted:
                matched += 1
            else:
                failures.append(
                    f"step[{index}].{field}: expected={wanted!r} observed={observed!r}"
                )
            ledger.record_semantic_slots(
                f"intent_step_{field}:{family}",
                expected_slots=(f"step:{index}|{field}|{_label(wanted)}",),
                predicted_slots=(
                    (f"step:{index}|{field}|{_label(observed)}",)
                    if actual is not None
                    else ()
                ),
            )

    ledger.record_case(
        f"intent:{family}",
        expected_slots=total,
        matched_slots=matched,
        elapsed_seconds=elapsed_seconds,
        case_passed=not failures,
    )
    return matched, total, tuple(failures)
