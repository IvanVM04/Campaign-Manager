"""Evaluate the V3 rollout evidence bundle without changing runtime flags."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from tests.v3_rollout_gate import build_v3_rollout_decision


def _read_json_object(path: Path, *, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read {description} as JSON") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{description} must contain a JSON object")
    return value


def _read_check_evidence(
    path: Path,
    *,
    description: str,
    candidate_commit: str,
) -> dict[str, Any]:
    value = _read_json_object(path, description=description)
    manifest = value.get("run_manifest")
    if (
        value.get("schema_version") != 1
        or not isinstance(manifest, dict)
        or not isinstance(value.get("checks"), dict)
    ):
        raise ValueError(
            f"{description} must use schema_version 1 and contain "
            "run_manifest and checks objects"
        )
    evidence_commit = manifest.get("campaign_manager_commit")
    if (
        not isinstance(evidence_commit, str)
        or evidence_commit.casefold() != candidate_commit.casefold()
    ):
        raise ValueError(
            f"{description} campaign_manager_commit must match --candidate-commit"
        )
    return value["checks"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check v3 semantic, durable-runtime and SillyTavern evidence. "
            "This command never enables v3 or authorizes automatic cutover."
        )
    )
    parser.add_argument(
        "--candidate-commit",
        required=True,
        help="full 40-character commit SHA shared by every evidence bundle",
    )
    parser.add_argument("--acceptance-report", required=True, type=Path)
    parser.add_argument("--runtime-evidence", required=True, type=Path)
    parser.add_argument("--sillytavern-evidence", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-review-eligible",
        action="store_true",
        help="exit with status 2 unless all three evidence gates pass",
    )
    args = parser.parse_args()

    if re.fullmatch(r"[0-9a-fA-F]{40}", args.candidate_commit) is None:
        parser.error("--candidate-commit must be a full 40-character commit SHA")

    acceptance_report = _read_json_object(
        args.acceptance_report,
        description="Ollama acceptance report",
    )
    if not isinstance(acceptance_report.get("acceptance_matrix"), dict):
        raise TypeError("Ollama acceptance report must contain an acceptance_matrix object")

    decision = build_v3_rollout_decision(
        candidate_commit=args.candidate_commit,
        acceptance_report=acceptance_report,
        runtime_checks=_read_check_evidence(
            args.runtime_evidence,
            description="durable runtime evidence",
            candidate_commit=args.candidate_commit,
        ),
        sillytavern_checks=_read_check_evidence(
            args.sillytavern_evidence,
            description="SillyTavern evidence",
            candidate_commit=args.candidate_commit,
        ),
    )
    rendered = json.dumps(
        decision,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)

    if args.require_review_eligible and (
        decision["decision"] != "eligible_for_controlled_rollout_review"
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
