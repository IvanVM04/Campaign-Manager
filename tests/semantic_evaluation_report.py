"""Safe, reproducible JSON reports for opt-in local LLM evaluations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

_SAFE_USAGE_FIELDS = (
    "provider_role",
    "provider_model",
    "response_model",
    "request_status",
    "prompt_bytes",
    "duration_ms",
    "think",
    "done_reason",
    "done",
    "prompt_eval_count",
    "eval_count",
    "total_duration_ms",
    "load_duration_ms",
    "prompt_eval_duration_ms",
    "eval_duration_ms",
)


def _optional_provider_call(provider: object, method_name: str) -> str | None:
    method = getattr(provider, method_name, None)
    if not callable(method):
        return None
    try:
        value = method()
    except Exception:  # noqa: BLE001 - telemetry must not mask evaluation results
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:160]


def build_live_evaluation_report(
    *,
    evaluation_name: str,
    corpus_name: str,
    provider: object,
    ledger: SemanticEvaluationLedger,
    scenario_count: int,
    provider_calls: int,
    elapsed_seconds: float,
    usage_events: list[dict[str, Any]],
    scenario_filter: str | None = None,
) -> dict[str, Any]:
    """Build a content-free report; no prompts, completions or player text."""
    model = getattr(provider, "model", None)
    timeout = getattr(provider, "timeout", None)
    think = getattr(provider, "think", None)
    if not isinstance(model, str) or not model.strip():
        model = "unavailable"
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        timeout = None
    if not isinstance(think, bool):
        think = None

    safe_usage = [
        {
            field: event[field]
            for field in _SAFE_USAGE_FIELDS
            if field in event and isinstance(event[field], (str, int, float, bool))
        }
        for event in usage_events
    ]
    return {
        "schema_version": 1,
        "evaluation": evaluation_name,
        "corpus": corpus_name,
        "metadata": {
            "git_commit": (
                os.getenv("GITHUB_SHA")
                or os.getenv("CAMPAIGN_MANAGER_GIT_COMMIT")
                or None
            ),
            "model": model,
            "model_digest": _optional_provider_call(provider, "get_model_digest"),
            "ollama_version": _optional_provider_call(provider, "get_server_version"),
            "timeout_seconds": timeout,
            "think": think,
            "scenario_count": scenario_count,
            "provider_calls": provider_calls,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "scenario_filter": scenario_filter,
            "github_run_id": os.getenv("GITHUB_RUN_ID") or None,
            "github_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT") or None,
            "hardware_label": os.getenv("CAMPAIGN_MANAGER_REAL_LLM_HARDWARE") or None,
        },
        "metrics": ledger.summary(),
        "provider_usage": safe_usage,
    }


def write_live_evaluation_report(
    report: dict[str, Any],
    *,
    path: str | Path | None = None,
) -> str | None:
    """Write the report when a path is supplied or configured by environment."""
    configured_path = (
        str(path)
        if path is not None
        else os.getenv("CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH")
    )
    if not configured_path or not configured_path.strip():
        return None
    target = Path(configured_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    target.write_text(serialized + "\n", encoding="utf-8")
    return str(target)
