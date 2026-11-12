import math

import pytest

from services.providers import LLMSettings


def test_llm_settings_preserve_current_defaults():
    settings = LLMSettings.from_env({})

    assert settings.base_url == "http://localhost:11434"
    assert settings.narrative_model == "gemma4:26b"
    assert settings.extraction_model == "gemma4:26b"
    assert settings.mechanics_model == "gemma4:26b"
    assert settings.narrative_timeout_seconds == 120.0
    assert settings.extraction_timeout_seconds == 120.0
    assert settings.mechanics_timeout_seconds == 120.0
    assert settings.extraction_prompt_max_tokens == 8192
    assert settings.extraction_context_max_tokens == 4096
    assert settings.legacy_extraction_prompt_max_tokens == 65536
    assert settings.legacy_extraction_context_max_tokens == 8192
    assert settings.extraction_max_response_chars == 16000
    assert settings.extraction_repair_max_tokens == 2048


def test_llm_settings_read_role_models_and_timeouts_from_environment():
    settings = LLMSettings.from_env({
        "CAMPAIGN_MANAGER_OLLAMA_BASE_URL": "http://127.0.0.1:11435/",
        "CAMPAIGN_MANAGER_LLM_NARRATIVE_MODEL": "narrator:latest",
        "CAMPAIGN_MANAGER_LLM_EXTRACTION_MODEL": "extractor:latest",
        "CAMPAIGN_MANAGER_LLM_MECHANICS_MODEL": "mechanics:latest",
        "CAMPAIGN_MANAGER_LLM_NARRATIVE_TIMEOUT_SECONDS": "90",
        "CAMPAIGN_MANAGER_LLM_EXTRACTION_TIMEOUT_SECONDS": "45.5",
        "CAMPAIGN_MANAGER_LLM_MECHANICS_TIMEOUT_SECONDS": "30",
        "CAMPAIGN_MANAGER_LLM_EXTRACTION_PROMPT_MAX_TOKENS": "9000",
        "CAMPAIGN_MANAGER_LLM_EXTRACTION_CONTEXT_MAX_TOKENS": "5000",
        "CAMPAIGN_MANAGER_LLM_LEGACY_EXTRACTION_PROMPT_MAX_TOKENS": "72000",
        "CAMPAIGN_MANAGER_LLM_LEGACY_EXTRACTION_CONTEXT_MAX_TOKENS": "9000",
        "CAMPAIGN_MANAGER_LLM_EXTRACTION_MAX_RESPONSE_CHARS": "18000",
        "CAMPAIGN_MANAGER_LLM_EXTRACTION_REPAIR_MAX_TOKENS": "2500",
    })

    assert settings.base_url == "http://127.0.0.1:11435"
    assert settings.narrative_model == "narrator:latest"
    assert settings.extraction_model == "extractor:latest"
    assert settings.mechanics_model == "mechanics:latest"
    assert settings.narrative_timeout_seconds == 90.0
    assert settings.extraction_timeout_seconds == 45.5
    assert settings.mechanics_timeout_seconds == 30.0
    assert settings.extraction_prompt_max_tokens == 9000
    assert settings.extraction_context_max_tokens == 5000
    assert settings.legacy_extraction_prompt_max_tokens == 72000
    assert settings.legacy_extraction_context_max_tokens == 9000
    assert settings.extraction_max_response_chars == 18000
    assert settings.extraction_repair_max_tokens == 2500


def test_llm_settings_create_distinct_role_providers():
    settings = LLMSettings(
        base_url="http://localhost:11435",
        narrative_model="narrator",
        extraction_model="extractor",
        mechanics_model="adjudicator",
        narrative_timeout_seconds=90,
        extraction_timeout_seconds=45,
        mechanics_timeout_seconds=30,
    )

    narrative = settings.create_provider("narrative")
    extraction = settings.create_provider("extraction")
    mechanics = settings.create_provider("mechanics")

    assert narrative is not extraction
    assert extraction is not mechanics
    assert narrative.model == "narrator"
    assert extraction.model == "extractor"
    assert mechanics.model == "adjudicator"
    assert narrative.timeout == 90.0
    assert extraction.timeout == 45.0
    assert mechanics.timeout == 30.0
    assert {narrative.base_url, extraction.base_url, mechanics.base_url} == {
        "http://localhost:11435"
    }


@pytest.mark.parametrize("base_url", ["", "localhost:11434", "ftp://localhost:21", "http:///missing-host", "http://localhost:11434?x=1", "http://localhost:bad", "http://user:pass@localhost:11434"])
def test_llm_settings_reject_invalid_base_url(base_url):
    with pytest.raises(ValueError, match="absolute HTTP"):
        LLMSettings(base_url=base_url)


@pytest.mark.parametrize("model", ["", "   "])
def test_llm_settings_reject_empty_role_model(model):
    with pytest.raises(ValueError, match="must not be empty"):
        LLMSettings(narrative_model=model)


@pytest.mark.parametrize("timeout", [0, -1, math.inf, -math.inf, math.nan])
def test_llm_settings_reject_non_positive_or_non_finite_timeout(timeout):
    with pytest.raises(ValueError, match="finite number greater than zero"):
        LLMSettings(narrative_timeout_seconds=timeout)


def test_llm_settings_reject_boolean_timeout():
    with pytest.raises(TypeError, match="must be a number"):
        LLMSettings(narrative_timeout_seconds=True)


def test_llm_settings_reject_non_numeric_environment_timeout():
    with pytest.raises(ValueError, match="CAMPAIGN_MANAGER_LLM_EXTRACTION_TIMEOUT_SECONDS must be a number"):
        LLMSettings.from_env({
            "CAMPAIGN_MANAGER_LLM_EXTRACTION_TIMEOUT_SECONDS": "slow",
        })


def test_llm_settings_reject_unknown_provider_role():
    settings = LLMSettings()

    with pytest.raises(ValueError, match="unsupported LLM role"):
        settings.create_provider("other")


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("extraction_prompt_max_tokens", 0, ValueError),
        ("extraction_context_max_tokens", -1, ValueError),
        ("legacy_extraction_prompt_max_tokens", 0, ValueError),
        ("legacy_extraction_context_max_tokens", True, TypeError),
        ("extraction_max_response_chars", True, TypeError),
        ("extraction_repair_max_tokens", 1.5, TypeError),
    ],
)
def test_llm_settings_validate_extraction_budgets(field, value, error):
    with pytest.raises(error):
        LLMSettings(**{field: value})


def test_llm_settings_reject_context_budget_larger_than_prompt_budget():
    with pytest.raises(ValueError, match="cannot exceed"):
        LLMSettings(
            extraction_prompt_max_tokens=2048,
            extraction_context_max_tokens=4096,
        )


def test_llm_settings_reject_non_integer_extraction_budget_environment_value():
    with pytest.raises(
        ValueError,
        match="CAMPAIGN_MANAGER_LLM_EXTRACTION_CONTEXT_MAX_TOKENS must be an integer",
    ):
        LLMSettings.from_env({
            "CAMPAIGN_MANAGER_LLM_EXTRACTION_CONTEXT_MAX_TOKENS": "many",
        })



def test_llm_settings_reject_legacy_context_budget_larger_than_prompt_budget():
    with pytest.raises(ValueError, match="legacy_extraction_context_max_tokens cannot exceed"):
        LLMSettings(
            legacy_extraction_prompt_max_tokens=4096,
            legacy_extraction_context_max_tokens=8192,
        )


def test_llm_settings_reject_invalid_legacy_context_budget_environment_value():
    with pytest.raises(
        ValueError,
        match="CAMPAIGN_MANAGER_LLM_LEGACY_EXTRACTION_CONTEXT_MAX_TOKENS must be an integer",
    ):
        LLMSettings.from_env({
            "CAMPAIGN_MANAGER_LLM_LEGACY_EXTRACTION_CONTEXT_MAX_TOKENS": "large",
        })
