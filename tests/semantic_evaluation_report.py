"""Safe, reproducible JSON reports for opt-in local LLM evaluations."""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:/@+-]{1,160}$")
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9_.+-]{1,80}$")
_SAFE_ROLE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_SAFE_COMMIT = re.compile(r"^[0-9a-fA-F]{7,64}$")
_SAFE_FILTER = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_VALID_REQUEST_STATUSES = frozenset({"completed", "failed"})
_VALID_DONE_REASONS = frozenset({"stop", "length", "error", "load", "unload"})

_NUMERIC_USAGE_FIELDS = (
    "prompt_bytes",
    "duration_ms",
    "prompt_eval_count",
    "eval_count",
    "total_duration_ms",
    "load_duration_ms",
    "prompt_eval_duration_ms",
    "eval_duration_ms",
)


def _safe_token(value: Any, *, pattern: re.Pattern[str] = _SAFE_TOKEN) -> str | None:
    """Accept bounded identifiers only; reject arbitrary provider/user text."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if pattern.fullmatch(normalized) else None


def _safe_number(value: Any) -> int | float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        return None
    return value


def _optional_provider_call(provider: object, method_name: str) -> str | None:
    method = getattr(provider, method_name, None)
    if not callable(method):
        return None
    try:
        value = method()
    except Exception:  # noqa: BLE001 - telemetry must not mask evaluation results
        return None
    return _safe_token(value)


def _safe_usage_event(event: dict[str, Any]) -> dict[str, Any]:
    """Project an event onto fixed enums, identifiers and non-negative numbers."""
    safe: dict[str, Any] = {}
    provider_role = _safe_token(event.get("provider_role"), pattern=_SAFE_ROLE)
    if provider_role is not None:
        safe["provider_role"] = provider_role
    for field in ("provider_model", "response_model"):
        value = _safe_token(event.get(field))
        if value is not None:
            safe[field] = value

    request_status = event.get("request_status")
    if request_status in _VALID_REQUEST_STATUSES:
        safe["request_status"] = request_status

    done_reason = event.get("done_reason")
    if done_reason in _VALID_DONE_REASONS:
        safe["done_reason"] = done_reason

    for field in ("think", "done"):
        value = event.get(field)
        if isinstance(value, bool):
            safe[field] = value

    for field in _NUMERIC_USAGE_FIELDS:
        value = _safe_number(event.get(field))
        if value is not None:
            safe[field] = value
    return safe


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
    model = _safe_token(getattr(provider, "model", None)) or "unavailable"
    timeout = _safe_number(getattr(provider, "timeout", None))
    think = getattr(provider, "think", None)
    if not isinstance(think, bool):
        think = None

    raw_commit = (
        os.getenv("GITHUB_SHA")
        or os.getenv("CAMPAIGN_MANAGER_GIT_COMMIT")
        or ""
    )
    safe_commit = raw_commit.strip() if _SAFE_COMMIT.fullmatch(raw_commit.strip()) else None
    raw_filter = scenario_filter.strip() if isinstance(scenario_filter, str) else ""
    safe_filter = raw_filter if _SAFE_FILTER.fullmatch(raw_filter) else None

    report_name = _safe_token(evaluation_name, pattern=_SAFE_LABEL) or "evaluation"
    report_corpus = _safe_token(corpus_name, pattern=_SAFE_LABEL) or "unknown-corpus"
    hardware = _safe_token(
        os.getenv("CAMPAIGN_MANAGER_REAL_LLM_HARDWARE"),
        pattern=_SAFE_LABEL,
    )

    safe_usage = [_safe_usage_event(event) for event in usage_events]
    return {
        "schema_version": 1,
        "metric_schema_version": SemanticEvaluationLedger.METRIC_SCHEMA_VERSION,
        "evaluation": report_name,
        "corpus": report_corpus,
        "metadata": {
            "git_commit": safe_commit,
            "model": model,
            "model_digest": _optional_provider_call(provider, "get_model_digest"),
            "ollama_version": _optional_provider_call(provider, "get_server_version"),
            "timeout_seconds": timeout,
            "think": think,
            "scenario_count": max(0, int(scenario_count)),
            "provider_calls": max(0, int(provider_calls)),
            "elapsed_seconds": round(max(0.0, float(elapsed_seconds)), 3),
            "scenario_filter": safe_filter,
            "github_run_id": _safe_token(os.getenv("GITHUB_RUN_ID"), pattern=_SAFE_LABEL),
            "github_run_attempt": _safe_token(os.getenv("GITHUB_RUN_ATTEMPT"), pattern=_SAFE_LABEL),
            "hardware_label": hardware,
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
    if path is not None:
        configured_path = str(path)
    else:
        report_dir = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_REPORT_DIR")
        if report_dir and report_dir.strip():
            safe_name = re.sub(
                r"[^a-zA-Z0-9_.-]+",
                "-",
                str(report.get("evaluation", "evaluation")).strip(),
            ).strip("-.") or "evaluation"
            configured_path = str(Path(report_dir).expanduser() / f"{safe_name}.json")
        else:
            configured_path = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH")
    if not configured_path or not configured_path.strip():
        return None
    target = Path(configured_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    target.write_text(serialized + "\n", encoding="utf-8")
    return str(target)
