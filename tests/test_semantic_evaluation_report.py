"""Tests for per-evaluation output paths in the live report writer."""

import json

from tests.semantic_evaluation_report import write_live_evaluation_report


def test_report_writer_prefers_unique_report_directory_over_legacy_path(tmp_path, monkeypatch):
    report_dir = tmp_path / "run" / "reports"
    legacy_path = tmp_path / "legacy.json"
    monkeypatch.setenv("CAMPAIGN_MANAGER_REAL_LLM_REPORT_DIR", str(report_dir))
    monkeypatch.setenv("CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH", str(legacy_path))

    written = write_live_evaluation_report({
        "evaluation": "Semantic / Holdout v2",
        "metrics": {"entity_link_precision": 0.75},
    })

    expected = report_dir / "Semantic-Holdout-v2.json"
    assert written == str(expected)
    assert expected.is_file()
    assert json.loads(expected.read_text(encoding="utf-8"))["evaluation"] == "Semantic / Holdout v2"
    assert not legacy_path.exists()


def test_report_writer_keeps_legacy_path_when_report_directory_is_absent(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.json"
    monkeypatch.delenv("CAMPAIGN_MANAGER_REAL_LLM_REPORT_DIR", raising=False)
    monkeypatch.setenv("CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH", str(legacy_path))

    written = write_live_evaluation_report({"evaluation": "legacy"})

    assert written == str(legacy_path)
    assert legacy_path.is_file()
