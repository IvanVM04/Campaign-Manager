from __future__ import annotations

import logging
from collections.abc import Callable
from time import perf_counter

from models.mechanics import MechanicsResult
from models.player_intent_analysis import PlayerIntentAnalysis
from models.resolved_conversation_reference import ResolvedConversationReference
from models.resolved_world_reference import ResolvedWorldReference
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.world_context_projection import WorldContextProjection, estimate_tokens
from operations.turn_operations import TurnOperation

from .llm_extraction_errors import LLMExtractionError
from .llm_world_proposal_prompt_builder import LLMWorldProposalPromptBuilder
from .llm_world_proposal_validator import LLMWorldProposalValidator
from .llm_world_response_parser import LLMWorldResponseParser

logger = logging.getLogger(__name__)


class LLMWorldExtractor:
    """
    Convierte texto no confiable en operaciones tipadas.

    propose() recibe la intención del jugador y crea una propuesta estructurada
    independiente de la narración final. La validación estructural pasa por
    OperationParser; la validación de dominio sigue en WorldService.

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
        max_prompt_bytes: int | None = None,
        max_repair_prompt_bytes: int | None = None,
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
        self.operation_registry = getattr(operation_parser, "registry", None)
        if max_prompt_bytes is not None:
            max_prompt_tokens = max_prompt_bytes
        if max_repair_prompt_bytes is not None:
            max_repair_prompt_tokens = max_repair_prompt_bytes
        if isinstance(max_prompt_tokens, bool) or not isinstance(max_prompt_tokens, int) or max_prompt_tokens <= 0:
            raise ValueError("max_prompt_bytes must be a positive integer")
        if (
            isinstance(max_repair_prompt_tokens, bool)
            or not isinstance(max_repair_prompt_tokens, int)
            or max_repair_prompt_tokens <= 0
        ):
            raise ValueError("max_repair_prompt_bytes must be a positive integer")
        self.max_prompt_bytes = max_prompt_tokens
        self.max_prompt_tokens = max_prompt_tokens
        self.max_repair_prompt_bytes = max_repair_prompt_tokens
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
            operation_registry=self.operation_registry,
        )

    def _provide(self, prompt: str) -> str:
        """Call the provider with timing and safe, correlation-aware diagnostics."""
        provider_started = perf_counter()
        try:
            response = self.provider(prompt)
        except Exception as exc:
            logger.warning(
                "llm.provider.failed",
                extra={
                    "provider_role": "extraction",
                    "provider_model": getattr(self.provider, "model", None),
                    "duration_ms": round((perf_counter() - provider_started) * 1000, 3),
                    "error_type": type(exc).__name__,
                },
            )
            raise
        logger.info(
            "llm.provider.completed",
            extra={
                "provider_role": "extraction",
                "provider_model": getattr(self.provider, "model", None),
                "duration_ms": round((perf_counter() - provider_started) * 1000, 3),
                "response_chars": len(response) if isinstance(response, str) else None,
            },
        )
        return response

    def propose(
        self,
        player_intent: str,
        context: TurnContext,
        *,
        mechanics_result: MechanicsResult | None = None,
        intent_analysis: PlayerIntentAnalysis | None = None,
        recent_turns: list[TurnRecord] | None = None,
        context_projection: WorldContextProjection | None = None,
        resolved_references: tuple[ResolvedConversationReference, ...] = (),
        resolved_world_references: tuple[ResolvedWorldReference, ...] = (),
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

        if intent_analysis is not None and not isinstance(intent_analysis, PlayerIntentAnalysis):
            raise TypeError("intent_analysis must be a PlayerIntentAnalysis or None")
        if recent_turns is not None and not isinstance(recent_turns, list):
            raise TypeError("recent_turns must be a list of TurnRecord values or None")

        if not isinstance(resolved_references, tuple) or any(
            not isinstance(item, ResolvedConversationReference) for item in resolved_references
        ):
            raise TypeError("resolved_references must be a tuple of trusted references")

        if not isinstance(resolved_world_references, tuple) or any(
            not isinstance(item, ResolvedWorldReference)
            for item in resolved_world_references
        ):
            raise TypeError("resolved_world_references must be a tuple of trusted typed references")

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
        allowed_operation_types: tuple[str, ...] = ()
        if callable(allowed_getter):
            raw_operation_types = allowed_getter()
            if not isinstance(raw_operation_types, (tuple, list)):
                raise LLMExtractionError(
                    "operation parser returned an invalid model operation allowlist"
                )
            if any(not isinstance(value, str) for value in raw_operation_types):
                raise LLMExtractionError(
                    "operation parser returned a non-string model operation type"
                )
            allowed_operation_types = tuple(
                value
                for value in raw_operation_types
                if isinstance(value, str)
            )
        prompt = self.proposal_prompt_builder.build_prompt(
            intent,
            context,
            mechanics_result=mechanics_result,
            intent_analysis=intent_analysis,
            recent_turns=recent_turns,
            projection=context_projection,
            resolved_references=resolved_references,
            resolved_world_references=resolved_world_references,
            allowed_operation_types=allowed_operation_types,
            operation_registry=self.operation_registry,
            max_prompt_bytes=self.max_prompt_bytes,
        )
        prompt_estimated_bytes = estimate_tokens(prompt)
        log_fields = {
            "prompt_chars": len(prompt),
            "prompt_estimated_bytes": prompt_estimated_bytes,
            "prompt_budget_bytes": self.max_prompt_bytes,
            "prompt_budget_utilization": (
                prompt_estimated_bytes / self.max_prompt_bytes
            ),
        }
        if context_projection is not None:
            diagnostics = context_projection.diagnostics
            log_fields.update({
                "context_estimated_bytes": diagnostics.estimated_bytes,
                "context_budget_bytes": diagnostics.budget_bytes,
                "available_records": diagnostics.available_records,
                "candidate_records": diagnostics.candidate_records,
                "selected_records": diagnostics.selected_records,
                "excluded_records": diagnostics.excluded_records,
                "selected_counts": dict(diagnostics.selected_counts),
            })
        logger.info(
            "llm.proposal.context_prepared",
            extra=log_fields,
        )
        raw_response = self._provide(prompt)
        return self.proposal_validator.parse_with_repair(prompt, raw_response)

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
