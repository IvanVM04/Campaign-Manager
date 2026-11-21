"""Create a content-free summary from pytest JUnit XML and live-run JSON reports."""

from __future__ import annotations

import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_SAFE_COMMIT = re.compile(r"^[0-9a-fA-F]{7,64}$")

_SAFE_METADATA_FIELDS = {
    "git_commit",
    "model",
    "model_digest",
    "ollama_version",
    "timeout_seconds",
    "think",
    "scenario_count",
    "provider_calls",
    "elapsed_seconds",
    "scenario_filter",
    "hardware_label",
    "github_run_id",
    "github_run_attempt",
}
_SAFE_USAGE_FIELDS = {
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
}
_SAFE_NUMERIC_PROPERTY_SUFFIXES = (
    "_timeout_seconds",
    "_provider_calls",
    "_total_seconds",
    "_elapsed_seconds",
    "_critical_failure_count",
    "_observational_failure_count",
    "_provider_error_case_count",
    "_cases",
    "_scenarios",
    "_case_accuracy",
    "_passed_cases",
    "_expected_slots",
    "_slot_recall",
    "_mean_latency_seconds",
    "_semantic_slot_precision",
    "_semantic_slot_recall",
    "_semantic_slot_f1",
    "_semantic_slots_true_positive",
    "_semantic_slots_false_positive",
    "_semantic_slots_false_negative",
    "_semantic_slots_precision",
    "_semantic_slots_recall",
    "_semantic_slots_f1",
    "_entity_link_precision",
    "_entity_link_recall",
    "_correct_abstentions",
    "_incorrect_abstentions",
    "_context_recall",
    "_operation_precision",
    "_operation_recall",
    "_critical_false_persistent_changes",
    "_secret_leaks",
)
_SAFE_PROPERTY_SUFFIXES = (
    "_model",
    "_model_digest",
    "_ollama_version",
    "_timeout_seconds",
    "_think",
    "_provider_calls",
    "_total_seconds",
    "_elapsed_seconds",
    "_critical_failure_count",
    "_observational_failure_count",
    "_cases",
    "_scenarios",
    "_case_accuracy",
    "_passed_cases",
    "_expected_slots",
    "_slot_recall",
    "_mean_latency_seconds",
    "_semantic_slot_precision",
    "_semantic_slot_recall",
    "_semantic_slot_f1",
    "_semantic_slots_true_positive",
    "_semantic_slots_false_positive",
    "_semantic_slots_false_negative",
    "_semantic_slots_precision",
    "_semantic_slots_recall",
    "_semantic_slots_f1",
    "_provider_error_case_count",
    "_entity_link_precision",
    "_entity_link_recall",
    "_correct_abstentions",
    "_incorrect_abstentions",
    "_context_recall",
    "_operation_precision",
    "_operation_recall",
    "_critical_false_persistent_changes",
    "_secret_leaks",
    "_scenario_filter",
    "_hardware",
    "_git_commit",
    "_provider_usage",
)


def _safe_scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str) and len(value) <= 160 and "\n" not in value and "\r" not in value:
        return value
    return None


_UNSAFE = object()


def _safe_numeric_tree(value: Any) -> Any:
    """Keep numerical metric structures while excluding arbitrary text values."""
    if value is None or isinstance(value, (bool, int, float)):
        return _safe_scalar(value)
    if isinstance(value, dict):
        return {
            str(key): safe
            for key, item in value.items()
            if (safe := _safe_numeric_tree(item)) is not _UNSAFE
        }
    if isinstance(value, list):
        return [
            safe
            for item in value
            if (safe := _safe_numeric_tree(item)) is not _UNSAFE
        ]
    return _UNSAFE


def _junit_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "junit_available": False,
            "tests": 0,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "duration_seconds": 0.0,
            "failed_tests": [],
            "safe_properties": {},
        }

    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {
            "junit_available": False,
            "junit_error": "missing_or_invalid",
            "tests": 0,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "duration_seconds": 0.0,
            "failed_tests": [],
            "safe_properties": {},
        }
    testcases = list(root.iter("testcase"))
    failed_tests: list[str] = []
    skipped = failures = errors = 0
    duration = 0.0
    for case in testcases:
        try:
            duration += max(0.0, float(case.attrib.get("time", "0") or 0))
        except (TypeError, ValueError):
            pass
        case_failed = False
        for child in case:
            if child.tag == "skipped":
                skipped += 1
            elif child.tag == "failure":
                failures += 1
                case_failed = True
            elif child.tag == "error":
                errors += 1
                case_failed = True
        if case_failed:
            classname = case.attrib.get("classname", "")
            name = case.attrib.get("name", "unknown")
            failed_tests.append(f"{classname}::{name}" if classname else name)

    safe_properties: dict[str, Any] = {}
    for prop in root.iter("property"):
        name = prop.attrib.get("name", "")
        if not name or not name.endswith(_SAFE_PROPERTY_SUFFIXES):
            continue
        raw_value = prop.attrib.get("value", "")
        if name.endswith("_provider_usage"):
            try:
                usage_value = _safe_numeric_tree(json.loads(raw_value))
            except json.JSONDecodeError:
                continue
            if usage_value is not _UNSAFE:
                safe_properties[name] = usage_value
            continue
        if name.endswith("_think") and raw_value.casefold() in {"true", "false"}:
            safe_properties[name] = raw_value.casefold() == "true"
            continue
        if name.endswith(_SAFE_NUMERIC_PROPERTY_SUFFIXES):
            normalized = raw_value.strip()
            try:
                value = (
                    int(normalized)
                    if normalized.lstrip("+-").isdigit()
                    else float(normalized)
                )
            except ValueError:
                value = _safe_scalar(raw_value)
            if isinstance(value, float) and not math.isfinite(value):
                value = None
        else:
            value = _safe_scalar(raw_value)
        if value is not None:
            safe_properties[name] = value

    return {
        "junit_available": True,
        "tests": len(testcases),
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "duration_seconds": round(duration, 3),
        "failed_tests": sorted(set(failed_tests)),
        "safe_properties": dict(sorted(safe_properties.items())),
    }


def _safe_usage(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for event in value:
        if not isinstance(event, dict):
            continue
        safe_event = {
            key: scalar
            for key, raw in event.items()
            if key in _SAFE_USAGE_FIELDS
            and (scalar := _safe_scalar(raw)) is not None
        }
        if safe_event:
            result.append(safe_event)
    return result


def _safe_report(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"file": path.name, "readable": False}
    if not isinstance(raw, dict):
        return {"file": path.name, "readable": False}

    result: dict[str, Any] = {"file": path.name, "readable": True}
    for field in ("evaluation", "corpus", "schema_version"):
        scalar = _safe_scalar(raw.get(field))
        if scalar is not None:
            result[field] = scalar

    metadata = raw.get("metadata")
    if isinstance(metadata, dict):
        result["metadata"] = {
            field: scalar
            for field in _SAFE_METADATA_FIELDS
            if (scalar := _safe_scalar(metadata.get(field))) is not None
        }

    for field in ("metrics", "ledger_summary", "control_summary", "family_calls", "prompt_observations"):
        safe = _safe_numeric_tree(raw.get(field))
        if safe is not _UNSAFE and safe:
            result[field] = safe

    for field in ("provider_usage", "usage_events"):
        safe = _safe_usage(raw.get(field))
        if safe:
            result[field] = safe
    return result



def _validate_report_commits(paths: list[Path], expected_commit: str | None) -> dict[str, Any]:
    """Require each emitted live report to identify the exact checked-out commit."""
    if expected_commit is None:
        return {
            "checked": False,
            "passed": True,
            "expected_commit": None,
            "reports_checked": 0,
            "mismatched_reports": [],
        }

    expected = expected_commit.strip()
    if not _SAFE_COMMIT.fullmatch(expected):
        return {
            "checked": True,
            "passed": False,
            "expected_commit": "invalid",
            "reports_checked": len(paths),
            "mismatched_reports": [
                {"file": path.name, "reported_commit": "not_checked"}
                for path in paths
            ] or [{"file": "<runner_commit>", "reported_commit": "invalid"}],
        }

    mismatches: list[dict[str, str]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            mismatches.append({"file": path.name, "reported_commit": "unreadable"})
            continue
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        reported = metadata.get("git_commit") if isinstance(metadata, dict) else None
        if not isinstance(reported, str) or not _SAFE_COMMIT.fullmatch(reported.strip()):
            mismatches.append({"file": path.name, "reported_commit": "missing_or_invalid"})
        elif reported.strip().casefold() != expected.casefold():
            mismatches.append({"file": path.name, "reported_commit": reported.strip()})

    if not paths:
        mismatches.append({"file": "<reports>", "reported_commit": "no_live_reports"})

    return {
        "checked": True,
        "passed": not mismatches,
        "expected_commit": expected,
        "reports_checked": len(paths),
        "mismatched_reports": mismatches,
    }


def build_summary(
    *,
    junit_xml: Path,
    output_dir: Path,
    commit: str | None = None,
) -> dict[str, Any]:
    """Build a safe aggregate. Failure messages and captured stdout are never read."""
    output_dir.mkdir(parents=True, exist_ok=True)
    junit = _junit_summary(junit_xml)
    reports_dir = output_dir / "reports"
    report_paths = sorted(reports_dir.glob("*.json")) if reports_dir.exists() else []
    live_reports = [_safe_report(path) for path in report_paths]
    commit_validation = _validate_report_commits(report_paths, commit)

    summary = {
        "schema_version": 1,
        "commit": _safe_scalar(commit),
        "status": (
            "not_run"
            if not junit["junit_available"]
            else "failed"
            if junit["failures"] or junit["errors"] or not commit_validation["passed"]
            else "passed"
        ),
        "pytest": junit,
        "commit_validation": commit_validation,
        "live_reports": live_reports,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    pytest_summary = summary["pytest"]
    lines = [
        "# Ollama real-test run",
        "",
        f"- Status: **{summary['status']}**",
        f"- Commit: {summary.get('commit') or 'unavailable'}",
        f"- Tests: {pytest_summary['tests']}",
        f"- Failures: {pytest_summary['failures']}",
        f"- Errors: {pytest_summary['errors']}",
        f"- Skipped: {pytest_summary['skipped']}",
        f"- Test duration: {pytest_summary['duration_seconds']} seconds",
        "",
    ]

    validation = summary.get("commit_validation", {})
    if validation.get("checked"):
        lines.extend([
            "## Commit provenance validation",
            "",
            f"- Status: **{'PASS' if validation.get('passed') else 'FAIL'}**",
            f"- Expected commit: {validation.get('expected_commit')}",
            f"- Reports checked: {validation.get('reports_checked', 0)}",
        ])
        for mismatch in validation.get("mismatched_reports", []):
            lines.append(
                f"- Mismatch: {mismatch.get('file')} "
                f"(reported: {mismatch.get('reported_commit')})"
            )
        lines.append("")

    if pytest_summary["failed_tests"]:
        lines.extend(["## Failed test names", ""])
        lines.extend(f"- {name}" for name in pytest_summary["failed_tests"])
        lines.append("")

    if pytest_summary["safe_properties"]:
        lines.extend(["## Pytest metadata", ""])
        lines.extend(
            f"- {name}: {value}"
            for name, value in pytest_summary["safe_properties"].items()
        )
        lines.append("")

    if summary["live_reports"]:
        lines.extend(["## Live evaluation reports", ""])
        for report in summary["live_reports"]:
            lines.append(f"### {report['file']}")
            if not report.get("readable", False):
                lines.append("- Report could not be read.")
                lines.append("")
                continue
            metadata = report.get("metadata", {})
            for field in (
                "model",
                "model_digest",
                "ollama_version",
                "timeout_seconds",
                "think",
                "scenario_count",
                "provider_calls",
                "elapsed_seconds",
                "git_commit",
                "hardware_label",
            ):
                if field in metadata:
                    lines.append(f"- {field}: {metadata[field]}")
            for field in ("metrics", "ledger_summary", "control_summary", "family_calls"):
                metrics = report.get(field)
                if isinstance(metrics, dict) and metrics:
                    lines.append(f"- {field}: {json.dumps(metrics, ensure_ascii=False, sort_keys=True)}")
            lines.append("")

    if not pytest_summary["junit_available"]:
        lines.extend([
            "JUnit XML was not produced. Check the adjacent pytest.log for the startup error.",
            "",
        ])
    lines.extend([
        "This summary intentionally excludes prompts, completions, assertion messages and captured test output.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit-xml", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--commit")
    args = parser.parse_args()
    summary = build_summary(
        junit_xml=args.junit_xml,
        output_dir=args.output_dir,
        commit=args.commit,
    )
    print(
        "Ollama test summary: "
        f"status={summary['status']}; "
        f"tests={summary['pytest']['tests']}; "
        f"failures={summary['pytest']['failures']}; "
        f"errors={summary['pytest']['errors']}; "
        f"skipped={summary['pytest']['skipped']}"
    )
    print(f"Markdown report: {args.output_dir / 'summary.md'}")
    if not summary["commit_validation"]["passed"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
