from __future__ import annotations

import logging
from collections.abc import Callable

from models.mechanics import MechanicsResult
from models.turn_context import TurnContext
from models.world_context_projection import WorldContextProjection
from operations.turn_operations import TurnOperation

from .llm_world_prompt_builder import LLMWorldPromptBuilder
from .llm_world_proposal_prompt_builder import LLMWorldProposalPromptBuilder
from .llm_world_proposal_validator import LLMWorldProposalValidator
from .llm_extraction_errors import LLMExtractionError
from .llm_world_response_parser import LLMWorldResponseParser


logger = logging.getLogger(__name__)


def __getattr__(name: str):
    if name == "LLMExtractionError":
        from .llm_extraction_errors import LLMExtractionError

        return LLMExtractionError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class LLMWorldExtractor:
    """
    Convierte texto no confiable en operaciones tipadas.

    extract() conserva la compatibilidad narrativa de adaptadores existentes.
    propose() recibe la intención del jugador y crea una propuesta estructurada
    independiente de la narración final. Ambas rutas delegan validación
    estructural en OperationParser; la validación de dominio sigue en WorldService.

    El extractor NO:
        - modifica el mundo
        - persiste datos
        - aplica operaciones de personaje
        - resuelve ni certifica mecánicas de D&D
    """

    def __init__(
        self,
        provider: Callable[[str], str],
        operation_parser,
        *,
        max_prompt_tokens: int = LLMWorldProposalPromptBuilder.DEFAULT_MAX_PROMPT_TOKENS,
        max_response_chars: int = LLMWorldProposalValidator.DEFAULT_MAX_RESPONSE_CHARS,
        max_repair_prompt_tokens: int = LLMWorldProposalValidator.DEFAULT_MAX_REPAIR_PROMPT_TOKENS,
    ) -> None:
        if not callable(provider):
            raise TypeError(
                "provider must be callable"
            )

        if operation_parser is None:
            raise TypeError(
                "operation_parser is required"
            )

        self.provider = provider
        self.operation_parser = operation_parser
        if isinstance(max_prompt_tokens, bool) or not isinstance(max_prompt_tokens, int) or max_prompt_tokens <= 0:
            raise ValueError("max_prompt_tokens must be a positive integer")
        self.max_prompt_tokens = max_prompt_tokens
        self.max_response_chars = max_response_chars
        self.response_parser = LLMWorldResponseParser(operation_parser)
        self.proposal_prompt_builder = LLMWorldProposalPromptBuilder()
        self.proposal_validator = LLMWorldProposalValidator(
            provider=self._provide,
            operation_parser=operation_parser,
            parse_response=self._parse_response,
            parse_operations=self._parse_operations,
            max_response_chars=max_response_chars,
            max_repair_prompt_tokens=max_repair_prompt_tokens,
        )

    def _provide(self, prompt: str) -> str:
        """Resolve the current provider so runtime/test overrides stay in sync."""
        return self.provider(prompt)

    def __call__(
        self,
        text: str,
        context: TurnContext,
    ) -> list[TurnOperation]:
        return self.extract(
            text,
            context,
        )

    def extract(
        self,
        text: str,
        context: TurnContext,
    ) -> list[TurnOperation]:
        if not isinstance(text, str):
            raise TypeError(
                "text must be a string"
            )

        if not isinstance(context, TurnContext):
            raise TypeError(
                "context must be a TurnContext"
            )

        text = text.strip()

        if not text:
            return []

        prompt = self._build_prompt(
            text,
            context,
        )

        raw_response = self.provider(
            prompt
        )

        if len(raw_response) > self.max_response_chars if isinstance(raw_response, str) else len(repr(raw_response)) > self.max_response_chars:
            raise LLMExtractionError("LLM extraction response exceeds the configured size limit")

        payload = self._parse_response(
            raw_response
        )

        return self._parse_operations(
            payload
        )

    def propose(
        self,
        player_intent: str,
        context: TurnContext,
        *,
        mechanics_result: MechanicsResult | None = None,
        context_projection: WorldContextProjection | None = None,
    ) -> list[TurnOperation]:
        """Propose typed state operations from player intent, not DM prose.

        The returned operations are untrusted proposals. WorldService remains
        responsible for validating and atomically applying them.
        """
        if not isinstance(player_intent, str):
            raise TypeError("player_intent must be a string")
        if not isinstance(context, TurnContext):
            raise TypeError("context must be a TurnContext")
        intent = player_intent.strip()
        if not intent:
            return []

        if context_projection is not None and not isinstance(
            context_projection,
            WorldContextProjection,
        ):
            raise TypeError("context_projection must be a WorldContextProjection or None")

        allowed_getter = getattr(
            self.operation_parser,
            "model_proposable_operation_types",
            None,
        )
        allowed_operation_types = (
            allowed_getter()
            if callable(allowed_getter)
            else ()
        )
        prompt = self.proposal_prompt_builder.build_prompt(
            intent,
            context,
            mechanics_result=mechanics_result,
            projection=context_projection,
            allowed_operation_types=allowed_operation_types,
            max_prompt_tokens=self.max_prompt_tokens,
        )
        if context_projection is not None:
            diagnostics = context_projection.diagnostics
            logger.debug(
                "Prepared bounded LLM proposal context",
                extra={
                    "estimated_tokens": diagnostics.estimated_tokens,
                    "budget_tokens": diagnostics.budget_tokens,
                    "available_records": diagnostics.available_records,
                    "candidate_records": diagnostics.candidate_records,
                    "selected_records": diagnostics.selected_records,
                    "excluded_records": diagnostics.excluded_records,
                    "selected_counts": dict(diagnostics.selected_counts),
                },
            )
        raw_response = self.provider(prompt)
        return self.proposal_validator.parse_with_repair(prompt, raw_response)

    # ============================================================
    # PROMPT
    # ============================================================

    @staticmethod
    def _build_prompt(text: str, context: TurnContext) -> str:
        """Compatibility facade for world-extraction prompt construction."""
        return LLMWorldPromptBuilder.build_prompt(text, context)

    # ============================================================
    # RESPONSE PARSING
    # ============================================================

    @staticmethod
    def _parse_response(raw_response):
        """Compatibility facade for response decoding."""
        return LLMWorldResponseParser.parse_response(raw_response)

    def _parse_operations(self, payload: dict) -> list[TurnOperation]:
        """Compatibility facade for typed operation validation."""
        return self.response_parser.parse_operations(payload)
