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


def test_runner_installs_all_python_groups_and_runs_the_ci_gates():
    source = RUNNER.read_text(encoding="utf-8")
    for group in ("test", "lint", "typing", "nlp-pilot"):
        assert f'"{group}"' in source
    assert '"not real_llm"' in source
    assert '"check", "."' in source
    assert '"models", "rules_engine", "bootstrap", "operations"' in source
    assert '"--outputjson"' in source
    assert '"run", "test:js"' in source
    assert "coverage", "report" in source


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


def test_runner_writes_unique_machine_readable_and_human_reports():
    source = RUNNER.read_text(encoding="utf-8")
    assert "artifacts/quality-runs" in source
    assert "scripts/quality_run_report.py" in source
    assert "summary.md" in source
    assert "summary.json" in source
    assert "run-manifest.json" in source
    assert "coverage.xml" in source
    assert "junit.xml" in source


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
    assert 'ValidateSet("all", "language", "semantic-frames", "discourse", "compound-intent")' in source
    assert "held_out_language_understanding_corpus_v1" in source
    assert "held_out_semantic_frame_corpus_v1" in source
    assert "held_out_discourse_intent_and_resolution_corpus" in source
    assert "compound_intent_understanding_holdout" in source
    assert "Remove-Item Env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID" in source
    assert "Remove-Item Env:CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_SCENARIO_ID" in source
