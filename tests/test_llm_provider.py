from __future__ import annotations

import pytest

from services.providers import FakeLLMProvider, LLMProvider, LLMProviderError

# ============================================================
# LLMProvider
# ============================================================


def test_llm_provider_is_abstract():
    with pytest.raises(
        TypeError
    ):
        LLMProvider()


# ============================================================
# FakeLLMProvider - response fija
# ============================================================


def test_fake_provider_returns_fixed_response():

    provider = FakeLLMProvider(
        response='{"operations": []}'
    )

    result = provider.generate(
        "hola"
    )

    assert result == '{"operations": []}'


def test_fake_provider_is_callable():

    provider = FakeLLMProvider(
        response="respuesta"
    )

    result = provider(
        "hola"
    )

    assert result == "respuesta"


def test_fake_provider_records_prompt():

    provider = FakeLLMProvider(
        response="respuesta"
    )

    provider.generate(
        "primer prompt"
    )

    provider.generate(
        "segundo prompt"
    )

    assert provider.prompts == [
        "primer prompt",
        "segundo prompt",
    ]


def test_fake_provider_call_count():

    provider = FakeLLMProvider(
        response="respuesta"
    )

    assert provider.call_count == 0

    provider.generate(
        "uno"
    )

    assert provider.call_count == 1

    provider.generate(
        "dos"
    )

    assert provider.call_count == 2


def test_fake_provider_last_prompt():

    provider = FakeLLMProvider(
        response="respuesta"
    )

    assert provider.last_prompt is None

    provider.generate(
        "uno"
    )

    assert provider.last_prompt == "uno"

    provider.generate(
        "dos"
    )

    assert provider.last_prompt == "dos"


def test_fake_provider_reset():

    provider = FakeLLMProvider(
        response="respuesta"
    )

    provider.generate(
        "uno"
    )

    provider.generate(
        "dos"
    )

    assert provider.call_count == 2

    provider.reset()

    assert provider.call_count == 0
    assert provider.prompts == []
    assert provider.last_prompt is None


# ============================================================
# FakeLLMProvider - respuestas por prompt
# ============================================================


def test_fake_provider_selects_response_by_prompt():

    provider = FakeLLMProvider(
        responses={
            "Fungoso": "respuesta fungoso",
            "Aldric": "respuesta aldric",
        }
    )

    assert provider.generate(
        "Habla de Fungoso"
    ) == "respuesta fungoso"

    assert provider.generate(
        "Habla de Aldric"
    ) == "respuesta aldric"


def test_fake_provider_raises_when_prompt_has_no_response():

    provider = FakeLLMProvider(
        responses={
            "Fungoso": "respuesta"
        }
    )

    with pytest.raises(
        LLMProviderError,
        match="no response",
    ):
        provider.generate(
            "Habla de Vera"
        )


# ============================================================
# Validation
# ============================================================


def test_fake_provider_rejects_non_string_response():

    with pytest.raises(
        TypeError,
        match="response must be a string",
    ):
        FakeLLMProvider(
            response=123
        )


def test_fake_provider_rejects_non_dict_responses():

    with pytest.raises(
        TypeError,
        match="responses must be a dict",
    ):
        FakeLLMProvider(
            responses="invalid"
        )


def test_fake_provider_rejects_non_string_response_key():

    with pytest.raises(
        TypeError,
        match="response keys must be strings",
    ):
        FakeLLMProvider(
            responses={
                123: "respuesta"
            }
        )


def test_fake_provider_rejects_non_string_response_value():

    with pytest.raises(
        TypeError,
        match="response values must be strings",
    ):
        FakeLLMProvider(
            responses={
                "Fungoso": 123
            }
        )


def test_fake_provider_requires_configuration():

    with pytest.raises(
        ValueError,
        match="requires response",
    ):
        FakeLLMProvider()


def test_fake_provider_rejects_response_and_responses_together():

    with pytest.raises(
        ValueError,
        match="mutually exclusive",
    ):
        FakeLLMProvider(
            response="respuesta",
            responses={
                "Fungoso": "otra respuesta"
            },
        )


def test_fake_provider_rejects_invalid_error():

    with pytest.raises(
        TypeError,
        match="error must be an Exception",
    ):
        FakeLLMProvider(
            response="respuesta",
            error="error",
        )


def test_fake_provider_rejects_non_string_prompt():

    provider = FakeLLMProvider(
        response="respuesta"
    )

    with pytest.raises(
        TypeError,
        match="prompt must be a string",
    ):
        provider.generate(123)


# ============================================================
# Error propagation
# ============================================================


def test_fake_provider_wraps_provider_error():

    original_error = RuntimeError(
        "connection failed"
    )

    provider = FakeLLMProvider(
        error=original_error
    )

    with pytest.raises(
        LLMProviderError,
        match="Fake LLM provider error",
    ) as exc_info:

        provider.generate(
            "prompt"
        )

    assert exc_info.value.__cause__ is original_error


# ============================================================
# Integration with callable contract
# ============================================================


def test_fake_provider_satisfies_callable_contract():

    provider = FakeLLMProvider(
        response='{"operations": []}'
    )

    assert callable(provider)

    response = provider(
        "prompt"
    )

    assert response == '{"operations": []}'


def test_fake_provider_can_be_used_as_simple_provider():

    provider = FakeLLMProvider(
        response="ok"
    )

    def consume_provider(
        llm_provider,
    ):
        return llm_provider(
            "prompt"
        )

    assert consume_provider(
        provider
    ) == "ok"