"""Per-step scoring and privacy-safe reporting for compound player messages."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).parent / "fixtures"
_CORPUS = _FIXTURES / "compound_intent_corpus_holdout_v1.json"
_STEP_GOLD = _FIXTURES / "compound_intent_step_gold_v1.json"

_VALID_ACTORS = frozenset({"player", "npc", "other", "unknown"})
_VALID_MODALITIES = frozenset({
    "attempted", "completed", "observed", "planned", "conditional",
    "question", "dialogue", "reported", "negated", "correction", "unknown",
})
_VALID_POLARITIES = frozenset({"positive", "negative", "uncertain"})


def load_compound_intent_corpus() -> tuple[list[dict[str, Any]], dict[str, tuple[dict[str, str], ...]]]:
    """Load frozen utterances and their text-free per-step gold annotations."""
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    gold = json.loads(_STEP_GOLD.read_text(encoding="utf-8"))
    if corpus.get("schema_version") != 1 or corpus.get("split") != "held_out":
        raise ValueError("unsupported compound-intent corpus contract")
    if gold.get("schema_version") != 1 or gold.get("split") != "held_out_annotations":
        raise ValueError("unsupported compound-intent step-gold contract")
    scenarios = corpus.get("scenarios")
    entries = gold.get("scenarios")
    if not isinstance(scenarios, list) or not isinstance(entries, list):
        raise TypeError("compound-intent scenarios and annotations must be arrays")

    scenario_ids = [item.get("id") for item in scenarios if isinstance(item, dict)]
    gold_ids = [item.get("id") for item in entries if isinstance(item, dict)]
    if (
        len(scenario_ids) != len(scenarios)
        or any(not isinstance(value, str) or not value.strip() for value in scenario_ids)
        or len(set(scenario_ids)) != len(scenario_ids)
    ):
        raise ValueError("compound-intent scenario IDs must be unique non-empty strings")
    if (
        len(gold_ids) != len(entries)
        or any(not isinstance(value, str) or not value.strip() for value in gold_ids)
        or len(set(gold_ids)) != len(gold_ids)
    ):
        raise ValueError("compound-intent gold IDs must be unique non-empty strings")
    if set(scenario_ids) != set(gold_ids):
        raise ValueError("compound-intent gold must cover every corpus scenario exactly")

    gold_by_id: dict[str, tuple[dict[str, str], ...]] = {}
    for entry in entries:
        if set(entry) != {"id", "steps"} or not isinstance(entry["steps"], list):
            raise ValueError("compound-intent gold entries may contain only id and steps")
        labels = []
        for step in entry["steps"]:
            if (
                not isinstance(step, dict)
                or set(step) != {"actor", "modality", "polarity"}
                or step.get("actor") not in _VALID_ACTORS
                or step.get("modality") not in _VALID_MODALITIES
                or step.get("polarity") not in _VALID_POLARITIES
            ):
                raise ValueError("compound-intent step gold has an invalid label contract")
            labels.append(dict(step))
        gold_by_id[entry["id"]] = tuple(labels)

    for scenario in scenarios:
        if (
            not isinstance(scenario, dict)
            or set(scenario) != {
                "id", "family", "critical", "input", "recent_turns",
                "visible_entities", "expected",
            }
            or not isinstance(scenario["input"], str)
            or not scenario["input"].strip()
            or not isinstance(scenario["critical"], bool)
        ):
            raise ValueError("compound-intent scenario has an invalid shape")
        expected = scenario["expected"]
        if not isinstance(expected, dict) or set(expected) != {
            "category", "active_step_index", "step_count",
        }:
            raise ValueError("compound-intent expected contract is invalid")
        if (
            not isinstance(scenario["family"], str)
            or not scenario["family"].strip()
            or not isinstance(scenario["recent_turns"], list)
            or not isinstance(scenario["visible_entities"], list)
        ):
            raise ValueError("compound-intent family/context fields are invalid")
        step_count = expected["step_count"]
        active_index = expected["active_step_index"]
        if (
            not isinstance(expected["category"], str)
            or not expected["category"].strip()
            or isinstance(step_count, bool)
            or not isinstance(step_count, int)
            or not 1 <= step_count <= 8
            or (
                active_index is not None
                and (
                    isinstance(active_index, bool)
                    or not isinstance(active_index, int)
                    or not 0 <= active_index < step_count
                )
            )
            or step_count != len(gold_by_id[scenario["id"]])
        ):
            raise ValueError("compound-intent expected step contract is invalid")
    return scenarios, gold_by_id


def _value(value: Any) -> str | None:
    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) else None


def score_compound_intent_analysis(
    analysis: Any,
    *,
    expected: dict[str, Any],
    step_gold: tuple[dict[str, str], ...],
    family: str,
    ledger: Any,
    elapsed_seconds: float = 0.0,
) -> tuple[tuple[str, ...], int, int]:
    """Score category, active-step, count and each step's actor/modality/polarity."""
    steps = tuple(getattr(analysis, "steps", ())) if analysis is not None else ()
    predicted_category = _value(getattr(analysis, "category", None))
    predicted_active = getattr(analysis, "active_step_index", None) if analysis is not None else None
    predicted_count = len(steps)
    expected_count = len(step_gold)
    failures: list[str] = []
    expected_slots = 3 + expected_count * 3
    matched_slots = 0

    comparisons = (
        ("category", expected["category"], predicted_category),
        ("active_step_index", expected["active_step_index"], predicted_active),
        ("step_count", expected["step_count"], predicted_count),
    )
    for field, wanted, observed in comparisons:
        if wanted == observed:
            matched_slots += 1
        else:
            failures.append(f"intent.{field}_mismatch")
        ledger.record_semantic_slots(
            f"compound_{field}:{family}",
            expected_slots=(f"{field}:{wanted!s}",),
            predicted_slots=(f"{field}:{observed!s}",),
        )

    fields = ("actor", "modality", "polarity")
    for field in fields:
        wanted_slots = tuple(
            f"step:{index}:{field}:{label[field]}"
            for index, label in enumerate(step_gold)
        )
        observed_slots = tuple(
            f"step:{index}:{field}:{_value(getattr(step, field, None)) or 'missing'}"
            for index, step in enumerate(steps)
        )
        ledger.record_semantic_slots(
            f"compound_step_{field}:{family}",
            expected_slots=wanted_slots,
            predicted_slots=observed_slots,
        )
        for index, label in enumerate(step_gold):
            if index >= len(steps):
                failures.append(f"intent.step_{index}_{field}_missing")
                continue
            observed = _value(getattr(steps[index], field, None))
            if observed == label[field]:
                matched_slots += 1
            else:
                failures.append(f"intent.step_{index}_{field}_mismatch")
    if predicted_count > expected_count:
        failures.append("intent.extra_steps")
    ledger.record_case(
        f"compound:{family}",
        expected_slots=expected_slots,
        matched_slots=matched_slots,
        elapsed_seconds=elapsed_seconds,
        case_passed=not failures,
    )
    return tuple(failures), matched_slots, expected_slots


def build_compound_intent_report(
    *,
    ledger_summary: dict[str, Any],
    usage_events: list[dict[str, Any]],
    model: str,
    model_digest: str | None,
    ollama_version: str | None,
    timeout_seconds: float,
    think: bool | str | None,
    git_commit: str | None,
    scenario_filter: str | None,
    scenario_count: int,
    provider_calls: int,
    elapsed_seconds: float,
    critical_failure_count: int,
    observational_failure_count: int,
) -> dict[str, Any]:
    """Build aggregate-only output: never persist prompts, completions or campaign text."""
    usage_fields = (
        "prompt_bytes", "prompt_eval_count", "eval_count", "load_duration_ms",
        "prompt_eval_duration_ms", "eval_duration_ms", "total_duration_ms",
        "duration_ms",
    )
    usage_totals: dict[str, int] = {"event_count": len(usage_events)}
    for field in usage_fields:
        values = [
            event.get(field)
            for event in usage_events
            if isinstance(event.get(field), int)
            and not isinstance(event.get(field), bool)
            and event.get(field) >= 0
        ]
        usage_totals[f"{field}_total"] = sum(values)
        usage_totals[f"{field}_max"] = max(values, default=0)

    # Explicitly allowlist aggregate fields. In particular, the in-memory
    # secret marker counter is intentionally excluded from persisted artifacts.
    metrics = {
        field: ledger_summary[field]
        for field in (
            "families",
            "semantic_slot_quality",
            "semantic_slot_precision",
            "semantic_slot_recall",
            "semantic_slot_f1",
        )
        if field in ledger_summary
    }
    safe_commit = (
        git_commit.strip()[:64]
        if isinstance(git_commit, str) and git_commit.strip()
        else None
    )
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "metadata": {
            "git_commit": safe_commit,
            "model": model,
            "model_digest": model_digest,
            "ollama_version": ollama_version,
            "timeout_seconds": timeout_seconds,
            "think": think if isinstance(think, (bool, str)) else None,
        },
        "run": {
            "scenario_count": scenario_count,
            "provider_calls": provider_calls,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "scenario_filter": scenario_filter,
            "critical_failure_count": critical_failure_count,
            "observational_failure_count": observational_failure_count,
        },
        "metrics": metrics,
        "provider_usage_totals": usage_totals,
    }
