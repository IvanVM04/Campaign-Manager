"""Tests for the safe consolidated quality-run reporter."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.quality_run_report import (
    build_report,
    coverage_summary,
    junit_summary,
    nlp_ab_summary,
    nlp_offline_summary,
)


def test_junit_summary_counts_results_without_copying_failure_messages(tmp_path: Path):
    source = tmp_path / "results.xml"
    source.write_text(
        """<testsuites><testsuite tests="4">
        <testcase classname="suite" name="passed" time="1.2"/>
        <testcase classname="suite" name="failed" time="0.1">
          <failure message="DO NOT COPY THIS MESSAGE">PRIVATE FAILURE DETAIL</failure>
        </testcase>
        <testcase classname="suite" name="errored" time="0.2">
          <error message="PRIVATE ERROR">PRIVATE ERROR DETAIL</error>
        </testcase>
        <testcase classname="suite" name="skipped" time="0.0"><skipped/></testcase>
        </testsuite></testsuites>""",
        encoding="utf-8",
    )
    result = junit_summary(source)
    assert result == {
        "available": True, "tests": 4, "failures": 1, "errors": 1,
        "skipped": 1, "passed": 1, "duration_seconds": 1.5,
        "failed_tests": ["suite::errored", "suite::failed"],
    }
    assert "PRIVATE" not in json.dumps(result)


def test_coverage_summary_uses_combined_line_and_branch_denominator(tmp_path: Path):
    source = tmp_path / "coverage.xml"
    source.write_text(
        """<coverage><packages><package name="services"><classes>
        <class filename="services/a.py"><lines>
          <line number="1" hits="1"/>
          <line number="2" hits="0"/>
          <line number="3" hits="1" branch="true" condition-coverage="50% (1/2)"/>
        </lines></class></classes></package></packages></coverage>""",
        encoding="utf-8",
    )
    result = coverage_summary(source)
    assert result is not None
    assert result["lines_covered"] == 2
    assert result["lines_valid"] == 3
    assert result["branches_covered"] == 1
    assert result["branches_valid"] == 2
    assert result["combined_percent"] == 60.0
    assert result["gate_passed"] is False


def test_nlp_offline_summary_aggregates_cues_across_families(tmp_path: Path):
    source = tmp_path / "offline.json"
    source.write_text(json.dumps({
        "corpora": {
            "split": "both", "scenario_count": 10, "successful_parses": 9,
            "failed_parses": 1, "parse_coverage": 0.9,
        },
        "parser": {
            "model_package": "default", "library_version": "1.15.1",
            "model_directory_megabytes": 130.5,
        },
        "performance": {"wall_latency_p50_ms": 15.0, "wall_latency_p95_ms": 40.0},
        "probe_metrics": {"families": {
            "development:action": {
                "lexical_baseline": {"negation": {
                    "sample_count": 2, "true_positive": 1, "false_positive": 1,
                    "false_negative": 0, "true_negative": 0}},
                "stanza": {"negation": {
                    "sample_count": 2, "true_positive": 2, "false_positive": 0,
                    "false_negative": 0, "true_negative": 0}},
            },
            "held_out:action": {
                "lexical_baseline": {"negation": {
                    "sample_count": 1, "true_positive": 0, "false_positive": 1,
                    "false_negative": 0, "true_negative": 0}},
                "stanza": {"negation": {
                    "sample_count": 1, "true_positive": 1, "false_positive": 0,
                    "false_negative": 0, "true_negative": 0}},
            },
        }},
    }), encoding="utf-8")
    result = nlp_offline_summary(source)
    assert result is not None
    assert result["scenario_count"] == 10
    assert result["cue_metrics"]["lexical_baseline"]["negation"]["samples"] == 3
    assert result["cue_metrics"]["lexical_baseline"]["negation"]["precision"] == 0.5
    assert result["cue_metrics"]["stanza"]["negation"]["f1"] == 1.0


def test_nlp_ab_summary_exposes_metrics_not_prompts(tmp_path: Path):
    source = tmp_path / "ab.json"
    source.write_text(json.dumps({
        "comparison": {
            "model_only": {
                "passed_cases": 3, "scored_cases": 4,
                "metrics": {
                    "semantic_slot_precision": 0.7, "semantic_slot_recall": 0.8,
                    "semantic_slot_f1": 0.7467, "families": {"action": {"cases": 4}},
                },
            },
            "model_plus_stanza_hints": {
                "passed_cases": 4, "scored_cases": 4,
                "metrics": {
                    "semantic_slot_precision": 0.9, "semantic_slot_recall": 0.8,
                    "semantic_slot_f1": 0.8471, "families": {"action": {"cases": 4}},
                },
            },
        },
        "parser": {"attempted_parses": 4, "successful_parses": 4, "latency_p50_ms": 10},
        "private_prompt": "PLAYER SECRET TEXT",
    }), encoding="utf-8")
    result = nlp_ab_summary(source)
    assert result is not None
    assert result["model_only"]["case_accuracy"] == 0.75
    assert result["model_plus_stanza_hints"]["semantic_slot_f1"] == 0.8471
    assert "private_prompt" not in json.dumps(result)


def test_build_report_writes_markdown_and_json_and_fails_if_any_stage_failed(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest = run_dir / "run-manifest.json"
    manifest.write_text(json.dumps({
        "started_at": "2026-11-19T10:00:00",
        "finished_at": "2026-11-19T10:01:00",
        "duration_seconds": 60,
        "stages": [
            {"name": "Python tests", "status": "success", "duration_seconds": 50,
             "exit_code": 0, "log": "logs/python.log"},
            {"name": "Ruff", "status": "failed", "duration_seconds": 1,
             "exit_code": 1, "log": "logs/ruff.log"},
        ],
    }), encoding="utf-8")
    result = build_report(run_dir=run_dir, manifest_path=manifest, commit="abc1234")
    assert result["status"] == "failed"
    assert (run_dir / "summary.md").is_file()
    assert (run_dir / "summary.json").is_file()
    markdown = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "Estado global: FAILED" in markdown
    assert "Python tests" in markdown
    assert "ruff.log" in markdown
