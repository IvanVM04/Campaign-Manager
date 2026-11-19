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



def test_ollama_runner_uses_the_latest_recorded_local_model_profile():
    source = RUNNER.read_text(encoding="utf-8")
    assert '"gemma4:12b-it-q4_K_M"' in source
    assert '"300"' in source
    assert 'CAMPAIGN_MANAGER_OLLAMA_THINK" -Value "false"' in source
    assert 'CAMPAIGN_MANAGER_REAL_LLM_THINK" -Value $env:CAMPAIGN_MANAGER_OLLAMA_THINK' in source


def test_ollama_runner_scopes_scenario_filters_to_one_matching_holdout():
    source = RUNNER.read_text(encoding="utf-8")
    assert 'ValidateSet("all", "language", "semantic-frames", "discourse", "compound-intent")' in source
    assert 'held_out_language_understanding_corpus_v1' in source
    assert 'held_out_semantic_frame_corpus_v1' in source
    assert 'held_out_discourse_intent_and_resolution_corpus' in source
    assert 'compound_intent_understanding_holdout' in source
    assert 'Remove-Item Env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID' in source
    assert 'Remove-Item Env:CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_SCENARIO_ID' in source



def test_explicit_common_parameters_override_role_environment_defaults():
    source = RUNNER.read_text(encoding="utf-8")
    assert 'if (-not [string]::IsNullOrWhiteSpace($Model)) {' in source
    assert '$roleParameters = @{' in source
    assert 'Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_LLM_$($role)_MODEL" -Value $Model' in source
    assert 'if (-not [string]::IsNullOrWhiteSpace($TimeoutSeconds)) {' in source
    assert 'Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_LLM_$($role)_TIMEOUT_SECONDS" -Value $TimeoutSeconds' in source
    assert 'if (-not [string]::IsNullOrWhiteSpace($Think)) {' in source
    assert 'Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_LLM_$($role)_THINK" -Value $Think' in source
    assert 'if ([string]::IsNullOrWhiteSpace($roleParameters[$role])) {' in source
