"""Discourse holdout gold labels, control metrics and privacy-safe reports."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).parent / "fixtures"
_PRIMARY_ACTOR_GOLD = _FIXTURES / "discourse_pipeline_actor_gold_v1.json"
_VALID_ACTORS = frozenset({"player", "npc", "other", "unknown"})
_CONTROL_DIMENSIONS = frozenset({
    "topic_shift",
    "callback",
    "history_scope",
    "ellipsis_hint",
})


def load_primary_actor_gold() -> dict[str, str]:
    """Load the sidecar that scores the primary fictional actor, not the sender."""
    payload = json.loads(_PRIMARY_ACTOR_GOLD.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("split") != "held_out":
        raise ValueError("unsupported discourse actor gold contract")
    entries = payload.get("scenarios")
    if not isinstance(entries, list):
        raise TypeError("discourse actor gold scenarios must be a list")

    result: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError("discourse actor gold entries must be objects")
        scenario_id = entry.get("id")
        actor = entry.get("primary_actor")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError("discourse actor gold requires a non-empty scenario id")
        if actor not in _VALID_ACTORS:
            raise ValueError(f"unsupported primary actor for {scenario_id}")
        if scenario_id in result:
            raise ValueError(f"duplicate discourse actor gold id: {scenario_id}")
        result[scenario_id] = actor
    return result


class DiscourseControlLedger:
    """Score deterministic discourse controls independently of LLM interpretation."""

    def __init__(self) -> None:
        self._counts: dict[str, Counter[str]] = {
            name: Counter() for name in _CONTROL_DIMENSIONS
        }

    def record(self, dimension: str, *, expected: Any, observed: Any) -> None:
        if dimension not in _CONTROL_DIMENSIONS:
            raise ValueError(f"unknown discourse control dimension: {dimension}")
        counts = self._counts[dimension]
        counts["cases"] += 1
        counts["exact_matches"] += int(expected == observed)

    def summary(self) -> dict[str, dict[str, int | float | None]]:
        result: dict[str, dict[str, int | float | None]] = {}
        for dimension, counts in sorted(self._counts.items()):
            cases = counts["cases"]
            matches = counts["exact_matches"]
            result[dimension] = {
                "cases": cases,
                "exact_matches": matches,
                "exact_accuracy": round(matches / cases, 4) if cases else None,
            }
        return result


def build_live_discourse_report(
    *,
    ledger_summary: dict[str, Any],
    control_summary: dict[str, Any],
    prompt_observations: dict[str, int],
    family_calls: dict[str, int],
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
    """Build a reproducible aggregate-only artifact; never persist game text."""
    safe_events = []
    allowed_event_fields = (
        "provider_role",
        "provider_model",
        "response_model",
        "request_status",
        "prompt_bytes",
        "prompt_eval_count",
        "eval_count",
        "load_duration_ms",
        "prompt_eval_duration_ms",
        "eval_duration_ms",
        "total_duration_ms",
        "duration_ms",
        "think",
        "done",
        "done_reason",
    )
    for event in usage_events:
        safe_events.append({
            key: event.get(key)
            for key in allowed_event_fields
            if key in event
        })

    safe_think = think if isinstance(think, (bool, str)) else None
    safe_commit = (
        git_commit.strip()[:64]
        if isinstance(git_commit, str) and git_commit.strip()
        else None
    )
    return {
        "schema_version": 5,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "metadata": {
            "git_commit": safe_commit,
            "model": model,
            "model_digest": model_digest,
            "ollama_version": ollama_version,
            "timeout_seconds": timeout_seconds,
            "think": safe_think,
        },
        "run": {
            "scenario_count": scenario_count,
            "provider_calls": provider_calls,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "scenario_filter": scenario_filter,
            "critical_failure_count": critical_failure_count,
            "observational_failure_count": observational_failure_count,
        },
        "metrics": ledger_summary,
        "discourse_controls": control_summary,
        "diagnostics": {
            "family_calls": dict(sorted(family_calls.items())),
            "prompt_observations": dict(sorted(prompt_observations.items())),
            "provider_usage": safe_events,
        },
    }
