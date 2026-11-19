"""Deterministic tests for live Ollama provider configuration."""

import pytest

from tests.live_llm_config import (
    optional_bool_environment_variable,
    thinking_for_role,
)


@pytest.mark.parametrize(
    ("role", "environment", "expected"),
    [
        ("intent", {"CAMPAIGN_MANAGER_LLM_INTENT_THINK": "true"}, True),
        ("mechanics", {"CAMPAIGN_MANAGER_LLM_MECHANICS_THINK": "false"}, False),
        ("extraction", {"CAMPAIGN_MANAGER_LLM_EXTRACTION_THINK": "off"}, False),
        ("narrative", {"CAMPAIGN_MANAGER_LLM_NARRATIVE_THINK": "yes"}, True),
    ],
)
def test_role_specific_thinking_setting_wins_over_common_defaults(
    monkeypatch, role: str, environment: dict[str, str], expected: bool
):
    monkeypatch.setenv("CAMPAIGN_MANAGER_OLLAMA_THINK", "false")
    monkeypatch.setenv("CAMPAIGN_MANAGER_REAL_LLM_THINK", "true")
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    assert thinking_for_role(role) is expected


def test_real_llm_thinking_setting_overrides_global_ollama_default(monkeypatch):
    monkeypatch.setenv("CAMPAIGN_MANAGER_OLLAMA_THINK", "true")
    monkeypatch.setenv("CAMPAIGN_MANAGER_REAL_LLM_THINK", "false")
    assert thinking_for_role("intent") is False


def test_global_ollama_thinking_setting_is_used_when_no_live_override(monkeypatch):
    monkeypatch.delenv("CAMPAIGN_MANAGER_REAL_LLM_THINK", raising=False)
    monkeypatch.setenv("CAMPAIGN_MANAGER_OLLAMA_THINK", "false")
    assert thinking_for_role("intent") is False


def test_unset_thinking_settings_preserve_model_default(monkeypatch):
    monkeypatch.delenv("CAMPAIGN_MANAGER_REAL_LLM_THINK", raising=False)
    monkeypatch.delenv("CAMPAIGN_MANAGER_OLLAMA_THINK", raising=False)
    monkeypatch.delenv("CAMPAIGN_MANAGER_LLM_INTENT_THINK", raising=False)
    assert thinking_for_role("intent") is None


def test_invalid_thinking_setting_is_rejected(monkeypatch):
    monkeypatch.setenv("CAMPAIGN_MANAGER_REAL_LLM_THINK", "sometimes")
    with pytest.raises(ValueError, match="CAMPAIGN_MANAGER_REAL_LLM_THINK"):
        thinking_for_role("intent")


def test_unknown_provider_role_is_rejected():
    with pytest.raises(ValueError, match="unsupported Ollama provider role"):
        thinking_for_role("unknown")



def test_optional_bool_environment_variable_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("SAMPLE_BOOLEAN", raising=False)
    assert optional_bool_environment_variable("SAMPLE_BOOLEAN") is None


@pytest.mark.parametrize("value", ["false", "False", "0", "no", "off"])
def test_optional_bool_environment_variable_parses_false_values(monkeypatch, value):
    monkeypatch.setenv("SAMPLE_BOOLEAN", value)
    assert optional_bool_environment_variable("SAMPLE_BOOLEAN") is False


@pytest.mark.parametrize("value", ["true", "True", "1", "yes", "on"])
def test_optional_bool_environment_variable_parses_true_values(monkeypatch, value):
    monkeypatch.setenv("SAMPLE_BOOLEAN", value)
    assert optional_bool_environment_variable("SAMPLE_BOOLEAN") is True


def test_optional_bool_environment_variable_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv("SAMPLE_BOOLEAN", "sometimes")
    with pytest.raises(ValueError, match="SAMPLE_BOOLEAN must be a boolean"):
        optional_bool_environment_variable("SAMPLE_BOOLEAN")
