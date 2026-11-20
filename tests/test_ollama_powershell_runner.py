"""Static safety and completeness checks for the Windows quality runner."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run-ollama-tests.ps1"


def test_runner_updates_main_only_with_clean_tree_and_fast_forward():
    source = RUNNER.read_text(encoding="utf-8")
    assert 'git -C $script:RepoRoot status --porcelain' in source
    assert 'Invoke-Git @("fetch", "origin", "main")' in source
    assert 'Invoke-Git @("pull", "--ff-only", "origin", "main")' in source
    assert "if ($dirty)" in source


def test_runner_never_discards_work_or_downloads_ollama_models():
    source = RUNNER.read_text(encoding="utf-8").casefold()
    assert "invoke-expression" not in source
    assert "git reset" not in source
    assert "git clean" not in source
    assert "git stash" not in source
    assert "ollama pull" not in source


def test_runner_installs_only_local_evaluation_groups_and_skips_ci_gates():
    source = RUNNER.read_text(encoding="utf-8")
    assert '"test"' in source
    assert '"nlp-pilot"' in source
    # Keep environment setup aligned with AGENTS.md and CI. The repository
    # root is not installed as an editable package by the local runner.
    assert '"--no-install-project"' in source
    assert '"-r", "requirements.txt"' in source
    assert 'pip", "install", "-e", "."' not in source
    assert 'Install project package' not in source
    assert '"--group", "lint"' not in source
    assert '"--group", "typing"' not in source
    assert '"not real_llm"' not in source
    assert 'Invoke-CommandStage "Ruff"' not in source
    assert 'Invoke-CommandStage "Pyright' not in source
    assert 'npm run test:js' not in source.casefold()
    assert 'coverage report' not in source.casefold()
    assert 'scripts/ci/coverage_summary.py' not in source
    assert 'SkipLocalChecks' not in source
    assert 'real_llm and not nlp_pilot' in source
    assert 'scripts.run_nlp_pilot' in source


def test_runner_integrates_stanza_download_offline_and_guarded_ab():
    source = RUNNER.read_text(encoding="utf-8")
    assert "scripts.download_nlp_pilot_models" in source
    assert "scripts.run_nlp_pilot" in source
    assert '"--split", "both"' in source
    assert "CAMPAIGN_MANAGER_NLP_PILOT_LIVE" in source
    assert "tests/test_real_llm_nlp_pilot.py" in source
    assert "RunNlpAb" in source
    assert "SkipNlpModelDownload" in source


def test_runner_separates_regular_llm_tests_from_optional_nlp_ab():
    source = RUNNER.read_text(encoding="utf-8")
    assert '"real_llm and not nlp_pilot"' in source
    assert '"real_llm and nlp_pilot"' in source
    assert "CAMPAIGN_MANAGER_REAL_LLM_REPORT_DIR" in source
    assert "scripts/ollama_test_report.py" in source
    assert 'CAMPAIGN_MANAGER_REAL_LLM_V3_SHADOW_REPORT_PATH' in source
    assert 'player-turn-v3-shadow.json' in source
    assert 'player_turn_v3_shadow_holdout' in source
    assert 'ValidateSet("all", "language", "semantic-frames", "discourse", "compound-intent", "v3-shadow")' in source


def test_runner_writes_unique_machine_readable_and_human_reports():
    source = RUNNER.read_text(encoding="utf-8")
    assert "artifacts/quality-runs" in source
    assert "scripts/quality_run_report.py" in source
    assert "summary.md" in source
    assert "summary.json" in source
    assert "run-manifest.json" in source
    assert "coverage.xml" not in source
    assert "ollama.junit.xml" in source
    assert "nlp-ab.junit.xml" in source


def test_runner_keeps_local_configuration_and_role_overrides():
    source = RUNNER.read_text(encoding="utf-8")
    assert ".env.ollama" in source
    assert "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL" in source
    assert "CAMPAIGN_MANAGER_OLLAMA_BASE_URL" in source
    assert "CAMPAIGN_MANAGER_REAL_LLM_THINK" in source
    assert "CAMPAIGN_MANAGER_OLLAMA_THINK" in source
    assert "CAMPAIGN_MANAGER_LLM_$($role)_MODEL" in source
    assert "CAMPAIGN_MANAGER_LLM_$($role)_TIMEOUT_SECONDS" in source
    assert "gemma4:12b-it-q4_K_M" in source
    assert '"300"' in source


def test_runner_scopes_single_scenario_filters_to_the_matching_suite():
    source = RUNNER.read_text(encoding="utf-8")
    assert 'ValidateSet("all", "language", "semantic-frames", "discourse", "compound-intent", "v3-shadow")' in source
    assert "held_out_language_understanding_corpus_v1" in source
    assert "held_out_semantic_frame_corpus_v1" in source
    assert "held_out_discourse_intent_and_resolution_corpus" in source
    assert "compound_intent_understanding_holdout" in source
    assert "Remove-Item Env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID" in source
    assert "Remove-Item Env:CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_SCENARIO_ID" in source


def test_git_wrapper_treats_native_stderr_as_diagnostic_and_checks_exit_code():
    source = RUNNER.read_text(encoding="utf-8")
    start = source.index("function Invoke-Git(")
    end = source.index("\nfunction Set-EnvDefault", start)
    wrapper = source[start:end]

    # Git emits fetch progress on stderr even when the operation succeeds.
    # The script uses ErrorActionPreference=Stop, so the wrapper must locally
    # relax it, capture output, restore it, and rely on LASTEXITCODE for failure.
    assert '$savedErrorActionPreference = $ErrorActionPreference' in wrapper
    assert '$ErrorActionPreference = "Continue"' in wrapper
    assert '$gitOutput = @(& git -C $script:RepoRoot @Arguments 2>&1)' in wrapper
    assert '$gitExitCode = $LASTEXITCODE' in wrapper
    assert '$ErrorActionPreference = $savedErrorActionPreference' in wrapper
    assert 'Write-Host $line.ToString()' in wrapper
    assert 'if ($gitExitCode -ne 0)' in wrapper
    assert '| Out-Host' not in wrapper


def test_runner_does_not_shadow_automatic_powershell_args_variable():
    source = RUNNER.read_text(encoding="utf-8")
    assert "[string[]]$Args" not in source
    assert "& $Exe @CommandArgs" in source
    assert "$ollamaPytestArgs" in source
