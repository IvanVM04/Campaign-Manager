"""Tests for per-evaluation output paths in the live report writer."""

import json

from tests.semantic_evaluation_metrics import SemanticEvaluationLedger
from tests.semantic_evaluation_report import (
    build_live_evaluation_report,
    write_live_evaluation_report,
)


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



def test_live_report_drops_untrusted_provider_strings_and_invalid_metadata(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    class Provider:
        model = "gemma4:12b"
        timeout = 120
        think = False

        def get_model_digest(self):
            return "sha256:deadbeef"

        def get_server_version(self):
            return "0.40.16"

    monkeypatch.setenv("CAMPAIGN_MANAGER_GIT_COMMIT", "not-a-valid-sha PLAYER SECRET")
    monkeypatch.setenv("CAMPAIGN_MANAGER_REAL_LLM_HARDWARE", "GPU label with private text")
    ledger = SemanticEvaluationLedger()
    report = build_live_evaluation_report(
        evaluation_name="safe_eval",
        corpus_name="holdout_v1.json",
        provider=Provider(),
        ledger=ledger,
        scenario_count=1,
        provider_calls=1,
        elapsed_seconds=0.5,
        scenario_filter="../private prompt",
        usage_events=[{
            "provider_role": "intent\\nSECRET",
            "provider_model": "gemma4:12b",
            "response_model": "private completion text",
            "request_status": "completed",
            "done_reason": "private completion",
            "prompt": "PLAYER PRIVATE TEXT",
            "completion": "SECRET COMPLETION",
            "duration_ms": 100,
            "prompt_eval_count": 20,
        }],
    )

    assert report["metadata"]["git_commit"] is None
    assert report["metadata"]["hardware_label"] is None
    assert report["metadata"]["scenario_filter"] is None
    assert report["provider_usage"] == [{
        "provider_model": "gemma4:12b",
        "request_status": "completed",
        "duration_ms": 100,
        "prompt_eval_count": 20,
    }]

    target = tmp_path / "safe.json"
    write_live_evaluation_report(report, path=target)
    serialized = target.read_text(encoding="utf-8")
    assert "PLAYER PRIVATE TEXT" not in serialized
    assert "SECRET COMPLETION" not in serialized
    assert "private completion text" not in serialized
    assert "private prompt" not in serialized
    assert report["metric_schema_version"] == 1
