from __future__ import annotations

import json
import math
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .llm_provider import (
    LLMProvider,
    LLMProviderError,
)


class OllamaProvider(LLMProvider):
    """
    Proveedor LLM para una instancia local de Ollama.

    Por defecto utiliza:

        http://localhost:11434
        gemma4:26b

    Responsabilidad única:

        prompt -> Ollama -> texto generado

    No conoce:
    - WorldState
    - WorldOperation
    - memoria
    - SQLite
    - extracción de operaciones
    """

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "gemma4:26b"
    DEFAULT_TIMEOUT = 120.0

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:

        if not isinstance(model, str):
            raise TypeError(
                "model must be a string"
            )

        model = model.strip()

        if not model:
            raise ValueError(
                "model must not be empty"
            )

        if not isinstance(base_url, str):
            raise TypeError(
                "base_url must be a string"
            )

        base_url = base_url.strip().rstrip("/")

        if not base_url:
            raise ValueError(
                "base_url must not be empty"
            )

        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError(
                "timeout must be a number"
            )

        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError(
                "timeout must be > 0 and finite"
            )

        self.model = model
        self.base_url = base_url
        self.timeout = float(timeout)

    def generate(
        self,
        prompt: str,
    ) -> str:
        """
        Envía un prompt a Ollama y devuelve únicamente
        el texto generado.
        """

        if not isinstance(prompt, str):
            raise TypeError(
                "prompt must be a string"
            )

        prompt = prompt.strip()

        if not prompt:
            raise ValueError(
                "prompt must not be empty"
            )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        response = self._request(
            payload
        )

        return self._extract_response_text(
            response
        )

    def generate_structured(
        self,
        prompt: str,
        *,
        schema: dict[str, Any],
    ) -> str:
        """Generate a response constrained by an Ollama JSON Schema.

        This constrains formatting only; callers must still validate semantic
        content and trust boundaries in their own typed domain models.
        """
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            raise ValueError("prompt must not be empty")
        if not isinstance(schema, dict) or not schema:
            raise TypeError("schema must be a non-empty JSON Schema object")
        try:
            json.dumps(schema)
        except (TypeError, ValueError) as exc:
            raise TypeError("schema must be JSON serializable") from exc

        payload = {
            "model": self.model,
            "prompt": normalized_prompt,
            "stream": False,
            "format": schema,
        }
        response = self._request(payload)
        return self._extract_response_text(response)

    # ============================================================
    # HTTP
    # ============================================================

    def _request(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        url = (
            f"{self.base_url}/api/generate"
        )

        body = json.dumps(
            payload
        ).encode("utf-8")

        request = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout,
            ) as response:

                raw_body = response.read()

        except HTTPError as exc:

            raise LLMProviderError(
                self._http_error_message(exc)
            ) from exc

        except URLError as exc:

            raise LLMProviderError(
                "Could not connect to Ollama"
            ) from exc

        except TimeoutError as exc:

            raise LLMProviderError(
                "Ollama request timed out"
            ) from exc

        except OSError as exc:

            raise LLMProviderError(
                "Could not communicate with Ollama"
            ) from exc

        try:
            decoded = raw_body.decode(
                "utf-8"
            )

            result = json.loads(
                decoded
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:

            raise LLMProviderError(
                "Ollama returned invalid JSON"
            ) from exc

        if not isinstance(
            result,
            dict,
        ):
            raise LLMProviderError(
                "Ollama response must be a JSON object"
            )

        return result

    # ============================================================
    # RESPONSE
    # ============================================================

    @staticmethod
    def _extract_response_text(
        response: dict[str, Any],
    ) -> str:

        if "error" in response:

            error = response.get(
                "error"
            )

            if error:
                raise LLMProviderError(
                    f"Ollama error: {error}"
                )

        generated = response.get(
            "response"
        )

        if not isinstance(
            generated,
            str,
        ):
            raise LLMProviderError(
                "Ollama response is missing "
                "the generated text"
            )

        return generated

    # ============================================================
    # ERRORS
    # ============================================================

    @staticmethod
    def _http_error_message(
        error: HTTPError,
    ) -> str:

        try:
            body = error.read().decode(
                "utf-8"
            )

            payload = json.loads(
                body
            )

            if isinstance(
                payload,
                dict,
            ):
                message = payload.get(
                    "error"
                )

                if message:
                    return (
                        f"Ollama HTTP "
                        f"{error.code}: {message}"
                    )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            OSError,
        ):
            pass

        return (
            f"Ollama HTTP error "
            f"{error.code}"
        )