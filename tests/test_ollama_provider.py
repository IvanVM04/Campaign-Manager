from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from services.providers import LLMProvider, LLMProviderError, OllamaProvider

# ============================================================
# CONSTRUCTION
# ============================================================


def test_ollama_provider_is_llm_provider():

    provider = OllamaProvider()

    assert isinstance(
        provider,
        LLMProvider,
    )


def test_ollama_provider_default_model():

    provider = OllamaProvider()

    assert provider.model == "gemma4:26b"


def test_ollama_provider_default_base_url():

    provider = OllamaProvider()

    assert provider.base_url == (
        "http://localhost:11434"
    )


def test_ollama_provider_default_timeout():

    provider = OllamaProvider()

    assert provider.timeout == 120.0


def test_ollama_provider_accepts_custom_configuration():

    provider = OllamaProvider(
        model="other-model",
        base_url="http://127.0.0.1:9999/",
        timeout=30,
    )

    assert provider.model == "other-model"
    assert provider.base_url == (
        "http://127.0.0.1:9999"
    )
    assert provider.timeout == 30.0


# ============================================================
# VALIDATION
# ============================================================


def test_ollama_provider_rejects_non_string_model():

    with pytest.raises(
        TypeError,
        match="model must be a string",
    ):
        OllamaProvider(
            model=123
        )


def test_ollama_provider_rejects_empty_model():

    with pytest.raises(
        ValueError,
        match="model must not be empty",
    ):
        OllamaProvider(
            model="   "
        )


def test_ollama_provider_rejects_non_string_base_url():

    with pytest.raises(
        TypeError,
        match="base_url must be a string",
    ):
        OllamaProvider(
            base_url=123
        )


def test_ollama_provider_rejects_empty_base_url():

    with pytest.raises(
        ValueError,
        match="base_url must not be empty",
    ):
        OllamaProvider(
            base_url="   "
        )


def test_ollama_provider_rejects_invalid_timeout():

    with pytest.raises(
        TypeError,
        match="timeout must be a number",
    ):
        OllamaProvider(
            timeout="120"
        )


def test_ollama_provider_rejects_zero_timeout():

    with pytest.raises(
        ValueError,
        match="timeout must be > 0",
    ):
        OllamaProvider(
            timeout=0
        )


def test_ollama_provider_rejects_negative_timeout():

    with pytest.raises(
        ValueError,
        match="timeout must be > 0",
    ):
        OllamaProvider(
            timeout=-1
        )


# ============================================================
# PROMPT VALIDATION
# ============================================================


def test_ollama_provider_rejects_non_string_prompt():

    provider = OllamaProvider()

    with pytest.raises(
        TypeError,
        match="prompt must be a string",
    ):
        provider.generate(123)


def test_ollama_provider_rejects_empty_prompt():

    provider = OllamaProvider()

    with pytest.raises(
        ValueError,
        match="prompt must not be empty",
    ):
        provider.generate("   ")


# ============================================================
# REQUEST PAYLOAD
# ============================================================


def test_ollama_provider_builds_expected_request(
    monkeypatch,
):

    captured = {}

    class FakeResponse:

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def read(self):
            return json.dumps(
                {
                    "response": "respuesta"
                }
            ).encode("utf-8")

    def fake_urlopen(
        request,
        timeout,
    ):

        captured["request"] = request
        captured["timeout"] = timeout

        return FakeResponse()

    monkeypatch.setattr(
        "services.providers.ollama_provider.urlopen",
        fake_urlopen,
    )

    provider = OllamaProvider()

    result = provider.generate(
        "Hola mundo"
    )

    assert result == "respuesta"

    request = captured["request"]

    assert request.full_url == (
        "http://localhost:11434/api/generate"
    )

    assert request.get_method() == "POST"

    assert request.headers[
        "Content-type"
    ] == "application/json"

    assert captured["timeout"] == 120.0

    payload = json.loads(
        request.data.decode("utf-8")
    )

    assert payload == {
        "model": "gemma4:26b",
        "prompt": "Hola mundo",
        "stream": False,
    }


def test_ollama_provider_strips_prompt():

    captured = {}

    class FakeResponse:

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def read(self):
            return (
                b'{"response":"ok"}'
            )

    def fake_urlopen(
        request,
        timeout,
    ):

        captured["request"] = request

        return FakeResponse()

    monkeypatch = pytest.MonkeyPatch()

    monkeypatch.setattr(
        "services.providers.ollama_provider.urlopen",
        fake_urlopen,
    )

    try:

        provider = OllamaProvider()

        provider.generate(
            "   hola   "
        )

        payload = json.loads(
            captured["request"]
            .data
            .decode("utf-8")
        )

        assert payload["prompt"] == (
            "hola"
        )

    finally:
        monkeypatch.undo()


# ============================================================
# RESPONSE PARSING
# ============================================================


def test_ollama_provider_returns_generated_text():

    provider = OllamaProvider()

    response = {
        "response": "Texto generado por Gemma."
    }

    assert provider._extract_response_text(
        response
    ) == "Texto generado por Gemma."


def test_ollama_provider_accepts_empty_generated_text():

    provider = OllamaProvider()

    response = {
        "response": ""
    }

    assert provider._extract_response_text(
        response
    ) == ""


def test_ollama_provider_rejects_missing_response():

    provider = OllamaProvider()

    with pytest.raises(
        LLMProviderError,
        match="missing the generated text",
    ):
        provider._extract_response_text(
            {}
        )


def test_ollama_provider_rejects_non_string_response():

    provider = OllamaProvider()

    with pytest.raises(
        LLMProviderError,
        match="missing the generated text",
    ):
        provider._extract_response_text(
            {
                "response": 123
            }
        )


def test_ollama_provider_handles_ollama_error():

    provider = OllamaProvider()

    with pytest.raises(
        LLMProviderError,
        match="Ollama error: model not found",
    ):
        provider._extract_response_text(
            {
                "error": "model not found"
            }
        )


# ============================================================
# INVALID JSON
# ============================================================


def test_ollama_provider_rejects_invalid_json(
    monkeypatch,
):

    class FakeResponse:

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def read(self):
            return b"not-json"

    monkeypatch.setattr(
        "services.providers.ollama_provider.urlopen",
        lambda request, timeout: FakeResponse(),
    )

    provider = OllamaProvider()

    with pytest.raises(
        LLMProviderError,
        match="invalid JSON",
    ):
        provider.generate(
            "Hola"
        )


def test_ollama_provider_rejects_non_object_json(
    monkeypatch,
):

    class FakeResponse:

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def read(self):
            return b"[]"

    monkeypatch.setattr(
        "services.providers.ollama_provider.urlopen",
        lambda request, timeout: FakeResponse(),
    )

    provider = OllamaProvider()

    with pytest.raises(
        LLMProviderError,
        match="must be a JSON object",
    ):
        provider.generate(
            "Hola"
        )


# ============================================================
# NETWORK ERRORS
# ============================================================


def test_ollama_provider_converts_connection_error(
    monkeypatch,
):

    from urllib.error import URLError

    def fake_urlopen(
        request,
        timeout,
    ):
        raise URLError(
            "connection refused"
        )

    monkeypatch.setattr(
        "services.providers.ollama_provider.urlopen",
        fake_urlopen,
    )

    provider = OllamaProvider()

    with pytest.raises(
        LLMProviderError,
        match="Could not connect to Ollama",
    ):
        provider.generate(
            "Hola"
        )


def test_ollama_provider_converts_timeout(
    monkeypatch,
):

    def fake_urlopen(
        request,
        timeout,
    ):
        raise TimeoutError(
            "timed out"
        )

    monkeypatch.setattr(
        "services.providers.ollama_provider.urlopen",
        fake_urlopen,
    )

    provider = OllamaProvider()

    with pytest.raises(
        LLMProviderError,
        match="timed out",
    ):
        provider.generate(
            "Hola"
        )


# ============================================================
# CALLABLE CONTRACT
# ============================================================


def test_ollama_provider_is_callable(
    monkeypatch,
):

    class FakeResponse:

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def read(self):
            return (
                b'{"response":"ok"}'
            )

    monkeypatch.setattr(
        "services.providers.ollama_provider.urlopen",
        lambda request, timeout: FakeResponse(),
    )

    provider = OllamaProvider()

    assert callable(provider)

    assert provider(
        "Hola"
    ) == "ok"

def test_ollama_provider_converts_http_error_with_provider_message(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 404, "Not Found", None, BytesIO(b'{"error":"model not found"}'))
    monkeypatch.setattr("services.providers.ollama_provider.urlopen", fake_urlopen)
    with pytest.raises(LLMProviderError, match="Ollama HTTP 404: model not found"):
        OllamaProvider().generate("Hola")


def test_ollama_provider_uses_stable_http_error_when_body_is_malformed(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 500, "Internal Server Error", None, BytesIO(b"not-json"))
    monkeypatch.setattr("services.providers.ollama_provider.urlopen", fake_urlopen)
    with pytest.raises(LLMProviderError, match="Ollama HTTP error 500"):
        OllamaProvider().generate("Hola")


def test_ollama_provider_does_not_retry_transport_failures(monkeypatch):
    calls = 0
    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        raise URLError("connection refused")
    monkeypatch.setattr("services.providers.ollama_provider.urlopen", fake_urlopen)
    with pytest.raises(LLMProviderError, match="Could not connect to Ollama"):
        OllamaProvider().generate("Hola")
    assert calls == 1


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf")])
def test_ollama_provider_rejects_non_finite_timeout(timeout):
    with pytest.raises(ValueError, match="timeout must be > 0"):
        OllamaProvider(timeout=timeout)


def test_ollama_provider_rejects_boolean_timeout():
    with pytest.raises(TypeError, match="timeout must be a number"):
        OllamaProvider(timeout=True)



def test_ollama_provider_generate_structured_sends_json_schema(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b'{"response":"{\\"ok\\":true}"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(
        "services.providers.ollama_provider.urlopen",
        fake_urlopen,
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["ok"],
        "properties": {"ok": {"type": "boolean"}},
    }

    result = OllamaProvider().generate_structured("  Return JSON  ", schema=schema)

    assert result == '{"ok":true}'
    assert captured["payload"] == {
        "model": "gemma4:26b",
        "prompt": "Return JSON",
        "stream": False,
        "format": schema,
    }


def test_ollama_provider_generate_structured_rejects_invalid_schema():
    with pytest.raises(TypeError, match="non-empty JSON Schema"):
        OllamaProvider().generate_structured("hello", schema={})
