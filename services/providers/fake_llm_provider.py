from __future__ import annotations

from .llm_provider import (
    LLMProvider,
    LLMProviderError,
)


class FakeLLMProvider(LLMProvider):
    """
    Proveedor LLM determinista para tests.

    Puede funcionar de dos maneras:

    1. response fija:
        FakeLLMProvider(response='{"operations": []}')

    2. responder según prompt:
        FakeLLMProvider(
            responses={
                "Fungoso": '{"operations": []}',
            }
        )

    También permite registrar los prompts recibidos.
    """

    def __init__(
        self,
        response: str | None = None,
        responses: dict[str, str] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:

        if response is not None and not isinstance(
            response,
            str,
        ):
            raise TypeError(
                "response must be a string or None"
            )

        if responses is not None:

            if not isinstance(
                responses,
                dict,
            ):
                raise TypeError(
                    "responses must be a dict or None"
                )

            for key, value in responses.items():

                if not isinstance(
                    key,
                    str,
                ):
                    raise TypeError(
                        "response keys must be strings"
                    )

                if not isinstance(
                    value,
                    str,
                ):
                    raise TypeError(
                        "response values must be strings"
                    )

        if error is not None and not isinstance(
            error,
            Exception,
        ):
            raise TypeError(
                "error must be an Exception or None"
            )

        if (
            response is None
            and responses is None
            and error is None
        ):
            raise ValueError(
                "FakeLLMProvider requires response, "
                "responses, or error"
            )

        if (
            response is not None
            and responses is not None
        ):
            raise ValueError(
                "response and responses are mutually exclusive"
            )

        self.response = response
        self.responses = responses
        self.error = error

        self.prompts: list[str] = []

    def generate(
        self,
        prompt: str,
    ) -> str:

        if not isinstance(
            prompt,
            str,
        ):
            raise TypeError(
                "prompt must be a string"
            )

        self.prompts.append(prompt)

        if self.error is not None:
            raise LLMProviderError(
                "Fake LLM provider error"
            ) from self.error

        if self.response is not None:
            return self.response

        assert self.responses is not None

        for key, response in self.responses.items():

            if key in prompt:
                return response

        raise LLMProviderError(
            "Fake LLM provider has no response "
            "for the supplied prompt"
        )

    @property
    def call_count(self) -> int:
        """
        Número de llamadas realizadas.
        """

        return len(self.prompts)

    @property
    def last_prompt(self) -> str | None:
        """
        Último prompt recibido.
        """

        if not self.prompts:
            return None

        return self.prompts[-1]

    def reset(self) -> None:
        """
        Limpia el historial de prompts.
        """

        self.prompts.clear()