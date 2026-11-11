from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from .ollama_provider import OllamaProvider

LLMRole = Literal["narrative", "extraction", "mechanics"]


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """Validated provider configuration for each model-facing responsibility."""

    base_url: str = OllamaProvider.DEFAULT_BASE_URL
    narrative_model: str = OllamaProvider.DEFAULT_MODEL
    extraction_model: str = OllamaProvider.DEFAULT_MODEL
    mechanics_model: str = OllamaProvider.DEFAULT_MODEL
    narrative_timeout_seconds: float = OllamaProvider.DEFAULT_TIMEOUT
    extraction_timeout_seconds: float = OllamaProvider.DEFAULT_TIMEOUT
    mechanics_timeout_seconds: float = OllamaProvider.DEFAULT_TIMEOUT
    extraction_prompt_max_tokens: int = 8192
    extraction_context_max_tokens: int = 4096
    extraction_max_response_chars: int = 16000
    extraction_repair_max_tokens: int = 2048

    def __post_init__(self) -> None:
        if not isinstance(self.base_url, str):
            raise TypeError("LLM base_url must be a string")
        normalized_url = self.base_url.strip().rstrip("/")
        try:
            parsed_url = urlsplit(normalized_url)
            _ = parsed_url.port
        except ValueError as exc:
            raise ValueError("LLM base_url must be a valid absolute HTTP(S) URL") from exc
        if (
            not normalized_url
            or parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("LLM base_url must be an absolute HTTP(S) URL without credentials, query or fragment")
        object.__setattr__(self, "base_url", normalized_url)

        for field_name in (
            "narrative_model",
            "extraction_model",
            "mechanics_model",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            value = value.strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value)

        for field_name in (
            "narrative_timeout_seconds",
            "extraction_timeout_seconds",
            "mechanics_timeout_seconds",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{field_name} must be a number")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be a finite number greater than zero")
            object.__setattr__(self, field_name, float(value))

        for field_name in (
            "extraction_prompt_max_tokens",
            "extraction_context_max_tokens",
            "extraction_max_response_chars",
            "extraction_repair_max_tokens",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
            if value <= 0:
                raise ValueError(f"{field_name} must be greater than zero")

        if self.extraction_context_max_tokens > self.extraction_prompt_max_tokens:
            raise ValueError(
                "extraction_context_max_tokens cannot exceed extraction_prompt_max_tokens"
            )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> LLMSettings:
        """Read validated settings from environment variables."""

        values = os.environ if environ is None else environ

        def timeout_value(name: str, default: float) -> float:
            raw_value = values.get(name)
            if raw_value is None:
                return default
            try:
                return float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a number") from exc

        defaults = cls()
        def integer_value(name: str, default: int) -> int:
            raw_value = values.get(name)
            if raw_value is None:
                return default
            try:
                return int(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be an integer") from exc

        return cls(
            base_url=values.get("CAMPAIGN_MANAGER_OLLAMA_BASE_URL", defaults.base_url),
            narrative_model=values.get(
                "CAMPAIGN_MANAGER_LLM_NARRATIVE_MODEL",
                defaults.narrative_model,
            ),
            extraction_model=values.get(
                "CAMPAIGN_MANAGER_LLM_EXTRACTION_MODEL",
                defaults.extraction_model,
            ),
            mechanics_model=values.get(
                "CAMPAIGN_MANAGER_LLM_MECHANICS_MODEL",
                defaults.mechanics_model,
            ),
            narrative_timeout_seconds=timeout_value(
                "CAMPAIGN_MANAGER_LLM_NARRATIVE_TIMEOUT_SECONDS",
                defaults.narrative_timeout_seconds,
            ),
            extraction_timeout_seconds=timeout_value(
                "CAMPAIGN_MANAGER_LLM_EXTRACTION_TIMEOUT_SECONDS",
                defaults.extraction_timeout_seconds,
            ),
            mechanics_timeout_seconds=timeout_value(
                "CAMPAIGN_MANAGER_LLM_MECHANICS_TIMEOUT_SECONDS",
                defaults.mechanics_timeout_seconds,
            ),
            extraction_prompt_max_tokens=integer_value(
                "CAMPAIGN_MANAGER_LLM_EXTRACTION_PROMPT_MAX_TOKENS",
                defaults.extraction_prompt_max_tokens,
            ),
            extraction_context_max_tokens=integer_value(
                "CAMPAIGN_MANAGER_LLM_EXTRACTION_CONTEXT_MAX_TOKENS",
                defaults.extraction_context_max_tokens,
            ),
            extraction_max_response_chars=integer_value(
                "CAMPAIGN_MANAGER_LLM_EXTRACTION_MAX_RESPONSE_CHARS",
                defaults.extraction_max_response_chars,
            ),
            extraction_repair_max_tokens=integer_value(
                "CAMPAIGN_MANAGER_LLM_EXTRACTION_REPAIR_MAX_TOKENS",
                defaults.extraction_repair_max_tokens,
            ),
        )

    def create_provider(self, role: LLMRole) -> OllamaProvider:
        """Build an Ollama adapter configured for one model responsibility."""

        configuration = {
            "narrative": (self.narrative_model, self.narrative_timeout_seconds),
            "extraction": (self.extraction_model, self.extraction_timeout_seconds),
            "mechanics": (self.mechanics_model, self.mechanics_timeout_seconds),
        }
        try:
            model, timeout = configuration[role]
        except KeyError as exc:
            raise ValueError(f"unsupported LLM role: {role}") from exc

        return OllamaProvider(
            model=model,
            base_url=self.base_url,
            timeout=timeout,
        )
