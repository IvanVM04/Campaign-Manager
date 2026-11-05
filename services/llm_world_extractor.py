from __future__ import annotations

from collections.abc import Callable

from models.mechanics import MechanicsResult
from models.turn_context import TurnContext
from operations.turn_operations import TurnOperation
from services.llm_extraction_errors import LLMExtractionError as _LLMExtractionError
from services.llm_world_prompt_builder import LLMWorldPromptBuilder
from services.llm_world_proposal_prompt_builder import LLMWorldProposalPromptBuilder
from services.llm_world_proposal_validator import LLMWorldProposalValidator
from services.llm_world_response_parser import LLMWorldResponseParser


LLMExtractionError = _LLMExtractionError


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
        self.response_parser = LLMWorldResponseParser(operation_parser)
        self.proposal_prompt_builder = LLMWorldProposalPromptBuilder()
        self.proposal_validator = LLMWorldProposalValidator(
            provider=self._provide,
            operation_parser=operation_parser,
            parse_response=self._parse_response,
            parse_operations=self._parse_operations,
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

        prompt = self.proposal_prompt_builder.build_prompt(
            intent,
            context,
            context_prompt_builder=self._build_prompt,
            mechanics_result=mechanics_result,
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
