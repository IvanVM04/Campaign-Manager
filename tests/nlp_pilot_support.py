"""Evaluation-only provider wrapper for parser-hint A/B comparisons."""

from __future__ import annotations

from typing import Any

from services.nlp_pilot.contracts import ParserDocument, render_prompt_hint_section
from services.providers.llm_provider import LLMProvider


class ParserHintingProvider(LLMProvider):
    """Append transient parser hints to an inner provider; never used in prod."""

    def __init__(self, inner: LLMProvider) -> None:
        if not callable(getattr(inner, "generate", None)) or not callable(
            getattr(inner, "generate_structured", None)
        ):
            raise TypeError("inner must expose generate and generate_structured")
        self.inner = inner
        self._hint_section = ""

    @property
    def model(self) -> str:
        return str(getattr(self.inner, "model", "unavailable"))

    @property
    def timeout(self) -> float | None:
        value = getattr(self.inner, "timeout", None)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    @property
    def think(self) -> bool | None:
        value = getattr(self.inner, "think", None)
        return value if isinstance(value, bool) else None

    @property
    def hint_bytes(self) -> int:
        return len(self._hint_section.encode("utf-8"))

    def set_parser_hints(self, document: ParserDocument | None) -> None:
        self._hint_section = (
            render_prompt_hint_section(document) if document is not None else ""
        )

    def _augment(self, prompt: str) -> str:
        return prompt + self._hint_section if self._hint_section else prompt

    def generate(self, prompt: str) -> str:
        return self.inner.generate(self._augment(prompt))

    def generate_structured(
        self,
        prompt: str,
        *,
        schema: dict[str, Any],
    ) -> str:
        return self.inner.generate_structured(self._augment(prompt), schema=schema)

    def get_model_digest(self) -> str | None:
        method = getattr(self.inner, "get_model_digest", None)
        value = method() if callable(method) else None
        return value if isinstance(value, str) else None

    def get_server_version(self) -> str | None:
        method = getattr(self.inner, "get_server_version", None)
        value = method() if callable(method) else None
        return value if isinstance(value, str) else None
