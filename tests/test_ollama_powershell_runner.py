"""Static safety checks for the repeatable Windows Ollama runner."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run-ollama-tests.ps1"


def test_ollama_runner_requires_clean_git_state_and_fast_forward_only_update():
    source = RUNNER.read_text(encoding="utf-8")
    assert "git -C $script:RepoRoot status --porcelain" in source
    assert 'Invoke-Git -Arguments @("fetch", "origin", "main")' in source
    assert 'Invoke-Git -Arguments @("pull", "--ff-only", "origin", "main")' in source


def test_ollama_runner_never_discards_work_or_downloads_models():
    source = RUNNER.read_text(encoding="utf-8").casefold()
    assert "invoke-expression" not in source
    assert "git reset" not in source
    assert "git clean" not in source
    assert "git stash" not in source
    assert "& ollama pull" not in source
    assert "ollama pull <modelo>" in source


def test_ollama_runner_synchronizes_shared_endpoint_and_think_defaults():
    source = RUNNER.read_text(encoding="utf-8")
    assert "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL" in source
    assert "CAMPAIGN_MANAGER_OLLAMA_BASE_URL" in source
    assert "CAMPAIGN_MANAGER_REAL_LLM_THINK" in source
    assert "CAMPAIGN_MANAGER_OLLAMA_THINK" in source
    assert "Mirror one configured value only when the other is not explicit." in source


def test_ollama_runner_propagates_common_model_and_timeout_to_unset_roles():
    source = RUNNER.read_text(encoding="utf-8")
    assert 'foreach ($role in @("INTENT", "MECHANICS", "EXTRACTION", "NARRATIVE"))' in source
    assert 'CAMPAIGN_MANAGER_LLM_$($role)_MODEL' in source
    assert 'CAMPAIGN_MANAGER_LLM_$($role)_TIMEOUT_SECONDS' in source


def test_ollama_runner_executes_real_llm_tests_and_keeps_machine_readable_results():
    source = RUNNER.read_text(encoding="utf-8")
    assert '"-m", "real_llm"' in source
    assert '"--junitxml", $junitPath' in source
    assert "scripts/ollama_test_report.py" in source
    assert "CAMPAIGN_MANAGER_REAL_LLM_REPORT_DIR" in source
    assert "artifacts/ollama" in source
