from __future__ import annotations

from dataclasses import dataclass

from models.campaign_state import CampaignState
from models.turn_context import TurnContext
from models.turn_resolution_result import TurnResolutionResult
from models.world_state import WorldState
from operations.character_operations import (
    CharacterOperation,
)
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import WorldOperation
from services.dm_service import DMService
from services.llm_world_extractor import LLMWorldExtractor
from services.world_service import WorldService


@dataclass(frozen=True)
class TurnResolutionPlan:
    """Immutable result of the non-persistent planning phase."""

    player_input: str
    narrative: str
    world_operations: tuple
    character_operations: tuple
    ordered_operations: tuple


class TurnResolutionServiceError(RuntimeError):
    """
    Error base del servicio de resolución de turnos.
    """


class TurnResolutionService:
    """
    Orquesta la resolución completa de un turno.

    Flujo:

        jugador
           |
           v
        DMService
           |
           v
        narrativa
           |
           v
        LLMWorldExtractor
           |
           v
        WorldOperation[]
           |
           v
        WorldService.apply_operations_and_save()
           |
           v
        resultado atómico

    Responsabilidades:

    - validar WorldState
    - validar entrada del jugador
    - generar narrativa mediante DMService
    - extraer operaciones mediante LLMWorldExtractor
    - aplicar y persistir operaciones de forma consistente
        mediante WorldService
    - devolver TurnResolutionResult

    NO debe:

    - acceder directamente a WorldApplier
    - acceder a SQLite
    - persistir directamente
    - conocer Ollama
    - conocer el modelo LLM
    - construir prompts
    - interpretar JSON
    - implementar reglas de dominio
    - reconstruir el contexto después de resolver el turno
    """

    def __init__(
        self,
        dm_service: DMService,
        extractor: LLMWorldExtractor,
        world_service: WorldService,
    ) -> None:

        if not isinstance(
            dm_service,
            DMService,
        ):
            raise TypeError(
                "dm_service must be a DMService"
            )

        if not isinstance(
            extractor,
            LLMWorldExtractor,
        ):
            raise TypeError(
                "extractor must be a LLMWorldExtractor"
            )

        if not isinstance(
            world_service,
            WorldService,
        ):
            raise TypeError(
                "world_service must be a WorldService"
            )

        self.dm_service = dm_service
        self.extractor = extractor
        self.world_service = world_service

    # ============================================================
    # PUBLIC API
    # ============================================================

    def prepare_turn(
        self,
        turn_context: TurnContext | WorldState,
        player_input: str,
        *,
        recent_turns=None,
    ) -> TurnResolutionPlan:
        """
        Generate narrative and extract a validated operation plan.

        This phase performs no database access or state mutation.
        """
        if isinstance(turn_context, TurnContext):
            context = turn_context
        elif isinstance(turn_context, WorldState):
            context = TurnContext(
                campaign=CampaignState(),
                current_session=None,
                active_character=None,
                world=turn_context,
            )
        else:
            raise TypeError(
                "turn_context must be a TurnContext or WorldState"
            )

        self._validate_world(context.world)
        normalized_input = self._validate_player_input(player_input)
        if not normalized_input:
            raise TurnResolutionServiceError(
                "player_input must not be empty"
            )

        try:
            if recent_turns is None:
                narrative = self.dm_service.generate(
                    context,
                    normalized_input,
                )
            else:
                narrative = self.dm_service.generate(
                    context,
                    normalized_input,
                    recent_turns=recent_turns,
                )
        except Exception as exc:
            raise TurnResolutionServiceError(
                "DMService failed to generate the turn"
            ) from exc

        if not isinstance(narrative, str):
            raise TurnResolutionServiceError(
                "DMService returned a non-string narrative"
            )
        narrative = narrative.strip()
        if not narrative:
            raise TurnResolutionServiceError(
                "DMService returned an empty narrative"
            )

        try:
            operations = self.extractor.extract(narrative, context)
        except Exception as exc:
            raise TurnResolutionServiceError(
                "LLMWorldExtractor failed to extract operations"
            ) from exc

        if not isinstance(operations, list):
            raise TurnResolutionServiceError(
                "LLMWorldExtractor returned an invalid operations list"
            )

        normalized_operations = []
        for operation in operations:
            if isinstance(operation, ReferencedOperation):
                inner_operation = operation.operation
                if not isinstance(
                    inner_operation,
                    (WorldOperation, CharacterOperation),
                ):
                    raise TurnResolutionServiceError(
                        "LLMWorldExtractor returned an invalid referenced operation"
                    )
                normalized_operations.append(operation)
            elif isinstance(operation, (WorldOperation, CharacterOperation)):
                normalized_operations.append(operation)
            else:
                raise TurnResolutionServiceError(
                    "LLMWorldExtractor returned an invalid operation"
                )

        def get_operation(operation):
            if isinstance(operation, ReferencedOperation):
                return operation.operation
            return operation

        ordered_operations = tuple(normalized_operations)
        world_operations = tuple(
            operation
            for operation in ordered_operations
            if isinstance(get_operation(operation), WorldOperation)
        )
        character_operations = tuple(
            operation
            for operation in ordered_operations
            if isinstance(get_operation(operation), CharacterOperation)
        )

        return TurnResolutionPlan(
            player_input=normalized_input,
            narrative=narrative,
            world_operations=world_operations,
            character_operations=character_operations,
            ordered_operations=ordered_operations,
        )

    def apply_plan(
        self,
        turn_context: TurnContext | WorldState,
        plan: TurnResolutionPlan,
        *,
        conn=None,
    ) -> TurnResolutionResult:
        """Apply a previously prepared plan inside the caller's transaction."""
        if isinstance(turn_context, TurnContext):
            context = turn_context
        elif isinstance(turn_context, WorldState):
            context = TurnContext(
                campaign=CampaignState(),
                current_session=None,
                active_character=None,
                world=turn_context,
            )
        else:
            raise TypeError(
                "turn_context must be a TurnContext or WorldState"
            )
        if not isinstance(plan, TurnResolutionPlan):
            raise TypeError("plan must be a TurnResolutionPlan")

        try:
            operation_results = self.world_service.apply_turn_operations(
                plan.world_operations,
                plan.character_operations,
                campaign_id=context.campaign.campaign_id,
                conn=conn,
                ordered_operations=plan.ordered_operations,
            )
        except Exception as exc:
            raise TurnResolutionServiceError(
                "WorldService failed to apply operations"
            ) from exc

        return TurnResolutionResult(
            player_input=plan.player_input,
            narrative=plan.narrative,
            operations=plan.world_operations,
            character_operations=plan.character_operations,
            operation_results=tuple(operation_results),
        )

    def resolve_turn(
        self,
        turn_context: TurnContext | WorldState,
        player_input: str,
        *,
        recent_turns=None,
        conn=None,
    ) -> TurnResolutionResult:
        """Backward-compatible convenience wrapper around prepare/apply."""
        plan = self.prepare_turn(
            turn_context,
            player_input,
            recent_turns=recent_turns,
        )
        return self.apply_plan(turn_context, plan, conn=conn)

    # ============================================================
    # VALIDATION
    # ============================================================

    @staticmethod
    def _validate_world(
        world: WorldState,
    ) -> None:

        if not isinstance(
            world,
            WorldState,
        ):
            raise TypeError(
                "world must be a WorldState"
            )

    @staticmethod
    def _validate_player_input(
        player_input: str,
    ) -> str:

        if not isinstance(
            player_input,
            str,
        ):
            raise TypeError(
                "player_input must be a string"
            )

        return player_input.strip()