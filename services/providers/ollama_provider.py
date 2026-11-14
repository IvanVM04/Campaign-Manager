from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .llm_provider import (
    LLMProvider,
    LLMProviderError,
)

logger = logging.getLogger(__name__)


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
        *,
        role: str | None = None,
        metrics_callback: Callable[[dict[str, Any]], None] | None = None,
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

        if role is not None:
            if not isinstance(role, str):
                raise TypeError("role must be a string or None")
            role = role.strip()
            if not role:
                raise ValueError("role must not be empty")
        if metrics_callback is not None and not callable(metrics_callback):
            raise TypeError("metrics_callback must be callable or None")

        self.model = model
        self.base_url = base_url
        self.timeout = float(timeout)
        self.role = role
        self.metrics_callback = metrics_callback

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

        response = self._request_with_metrics(payload, prompt)

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
        response = self._request_with_metrics(payload, normalized_prompt)
        return self._extract_response_text(response)

    def _request_with_metrics(
        self,
        payload: dict[str, Any],
        prompt: str,
    ) -> dict[str, Any]:
        """Send one request and emit content-free, role-tagged usage telemetry."""
        started = perf_counter()
        try:
            response = self._request(payload)
        except Exception as exc:
            self._emit_request_metrics(
                prompt=prompt,
                duration_ms=(perf_counter() - started) * 1000,
                response=None,
                error_type=type(exc).__name__,
            )
            raise

        response_error = bool(response.get("error"))
        self._emit_request_metrics(
            prompt=prompt,
            duration_ms=(perf_counter() - started) * 1000,
            response=response,
            error_type="OllamaResponseError" if response_error else None,
        )
        return response

    def _emit_request_metrics(
        self,
        *,
        prompt: str,
        duration_ms: float,
        response: dict[str, Any] | None,
        error_type: str | None,
    ) -> None:
        """Emit safe metadata only; never include prompt or completion text."""
        metrics: dict[str, Any] = {
            "provider_role": self.role,
            "provider_model": self.model,
            "prompt_bytes": len(prompt.encode("utf-8")),
            "duration_ms": round(duration_ms, 3),
            "request_status": "failed" if error_type else "completed",
        }
        if error_type is not None:
            metrics["error_type"] = error_type
        if response is not None:
            response_model = response.get("model")
            if isinstance(response_model, str) and response_model.strip():
                metrics["response_model"] = response_model.strip()[:120]
            done_reason = response.get("done_reason")
            if isinstance(done_reason, str) and done_reason.strip():
                metrics["done_reason"] = done_reason.strip()[:80]
            done = response.get("done")
            if isinstance(done, bool):
                metrics["done"] = done
            for field in (
                "prompt_eval_count",
                "eval_count",
                "total_duration",
                "load_duration",
                "prompt_eval_duration",
                "eval_duration",
            ):
                value = response.get(field)
                if (
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and value >= 0
                ):
                    metrics[field] = value
                    if field.endswith("_duration"):
                        metrics[f"{field}_ms"] = round(value / 1_000_000, 3)

        event = "ollama.request.failed" if error_type else "ollama.request.completed"
        if error_type:
            logger.warning(event, extra=metrics)
        else:
            logger.info(event, extra=metrics)

        if self.metrics_callback is not None:
            try:
                self.metrics_callback(dict(metrics))
            except Exception as exc:  # noqa: BLE001 - telemetry is best-effort
                # Telemetry must never turn a successful provider call into a failure.
                logger.warning(
                    "ollama.telemetry.callback_failed",
                    extra={
                        "provider_role": self.role,
                        "provider_model": self.model,
                        "error_type": type(exc).__name__,
                    },
                )

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

    def get_server_version(self) -> str | None:
        """Return the local Ollama version when its optional endpoint is available."""
        request = Request(
            f"{self.base_url}/api/version",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_body = response.read()
            payload = json.loads(raw_body.decode("utf-8"))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            logger.info(
                "ollama.version.unavailable",
                extra={
                    "provider_role": self.role,
                    "provider_model": self.model,
                    "error_type": type(exc).__name__,
                },
            )
            return None
        if not isinstance(payload, dict):
            return None
        version = payload.get("version")
        if not isinstance(version, str) or not version.strip():
            return None
        return version.strip()[:120]

    def get_model_digest(self) -> str | None:
        """Return the configured model's local digest when Ollama exposes it."""
        request = Request(
            f"{self.base_url}/api/tags",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_body = response.read()
            payload = json.loads(raw_body.decode("utf-8"))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            logger.info(
                "ollama.model_digest.unavailable",
                extra={
                    "provider_role": self.role,
                    "provider_model": self.model,
                    "error_type": type(exc).__name__,
                },
            )
            return None
        if not isinstance(payload, dict):
            return None
        models = payload.get("models")
        if not isinstance(models, list):
            return None
        for item in models:
            if not isinstance(item, dict) or item.get("name") != self.model:
                continue
            digest = item.get("digest")
            if isinstance(digest, str) and digest.strip():
                return digest.strip()[:160]
        return None

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