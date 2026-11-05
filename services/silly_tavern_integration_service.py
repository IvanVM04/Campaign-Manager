from __future__ import annotations

from database import get_conn
from models.campaign_scope import CampaignScope
from models.turn_context import TurnContext
from models.turn_resolution_result import TurnResolutionResult
from repositories.campaign_state_version_repository import (
    CampaignStateVersionRepository,
)
from repositories.turn_repository import TurnRepository
from repositories.world_snapshot_repository import WorldSnapshotRepository
from services.campaign_state_service import (
    CampaignStateService,
    CampaignStateServiceError,
)
from services.context_builder import ContextBuilder
from services.legacy_silly_tavern_turn_service import LegacySillyTavernTurnService
from services.llm_world_extractor import LLMWorldExtractor
from services.turn_execution_lock import TurnExecutionLock
from services.world_service import WorldService


class SillyTavernIntegrationServiceError(RuntimeError):
    """
    Error base de la integración con SillyTavern.
    """


class SillyTavernIntegrationServiceConflictError(
    SillyTavernIntegrationServiceError
):
    """
    Conflicto de idempotencia.

    Ocurre cuando un external_turn_id ya existe pero
    pertenece a un payload diferente.
    """


class SillyTavernIntegrationService:
    """
    Compatibility adapter and shared context provider for SillyTavern.

    The active extension uses DurableNativeTurnService for turn resolution
    and this service for context/history and legacy transcript-state reads.
    process_turn() remains
    solely for pre-PR31 clients and retains the older narrative-first,
    snapshot-reconciliation contract. Do not add new gameplay behavior to
    that legacy method.

    SillyTavern es responsable de generar la narrativa.

    Campaign Manager es responsable de:

        - proporcionar contexto persistente
        - proporcionar el estado actual de la campaña
        - extraer cambios persistentes de la narrativa
        - aplicar las operaciones al mundo
        - persistir el turno

    Flujo:

        SillyTavern
             |
             | contexto
             v
        ContextBuilder
             |
             | contexto
             v
        SillyTavern
             |
             | player_input + narrative
             v
        LLMWorldExtractor
             |
             v
        WorldService
             |
             v
        TurnRepository

    Este servicio NO:

        - genera narrativa
        - conoce Ollama
        - construye prompts narrativos
        - modifica directamente SQLite
        - implementa reglas de dominio
    """

    def __init__(
        self,
        *,
        campaign_state_service: CampaignStateService,
        context_builder: ContextBuilder,
        extractor: LLMWorldExtractor,
        world_service: WorldService,
        turn_repository: TurnRepository,
        turn_execution_lock: TurnExecutionLock,
    ) -> None:

        if not isinstance(
            campaign_state_service,
            CampaignStateService,
        ):
            raise TypeError(
                "campaign_state_service must be a "
                "CampaignStateService"
            )

        if not isinstance(
            context_builder,
            ContextBuilder,
        ):
            raise TypeError(
                "context_builder must be a ContextBuilder"
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

        if not isinstance(
            turn_repository,
            TurnRepository,
        ):
            raise TypeError(
                "turn_repository must be a TurnRepository"
            )

        if not isinstance(
            turn_execution_lock,
            TurnExecutionLock,
        ):
            raise TypeError(
                "turn_execution_lock must be a TurnExecutionLock"
            )

        self.turn_execution_lock = turn_execution_lock

        self.campaign_state_service = (
            campaign_state_service
        )

        self.context_builder = context_builder

        self.extractor = extractor

        self.world_service = world_service

        self.turn_repository = turn_repository
        self.state_version_repository = CampaignStateVersionRepository()

        self.world_snapshot_repository = WorldSnapshotRepository()
        self.campaign_scope = CampaignScope(world_service.campaign_id)
        self.legacy_turn_service = LegacySillyTavernTurnService(
            campaign_scope=self.campaign_scope,
            campaign_state_service=self.campaign_state_service,
            extractor=self.extractor,
            world_service=self.world_service,
            turn_repository=self.turn_repository,
            turn_execution_lock=self.turn_execution_lock,
            state_version_repository=self.state_version_repository,
            world_snapshot_repository=self.world_snapshot_repository,
            error_type=SillyTavernIntegrationServiceError,
            conflict_error_type=SillyTavernIntegrationServiceConflictError,
        )


    # ============================================================
    # CONTEXT
    # ============================================================

    def get_context(
        self,
        query: str,
        *,
        exclude_external_turn_id: str | None = None,
    ) -> dict:
        """
        Construye el contexto que SillyTavern debe proporcionar
        al modelo antes de generar la narrativa.

        El contexto utiliza exactamente el mismo ContextBuilder
        empleado por el pipeline interno de Campaign Manager.
        """

        normalized_query = self._validate_text(
            query,
            "query",
        )

        try:
            turn_context = (
                self.campaign_state_service
                .get_turn_context(campaign_id=self.campaign_scope.campaign_id)
            )

        except CampaignStateServiceError as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to obtain campaign context"
            ) from exc

        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "CampaignStateService failed to obtain "
                "campaign context"
            ) from exc

        if not isinstance(
            turn_context,
            TurnContext,
        ):
            raise SillyTavernIntegrationServiceError(
                "CampaignStateService returned an invalid "
                "TurnContext"
            )

        session_id = None

        if turn_context.current_session is not None:
            session_id = (
                turn_context.current_session.session_id
            )

        try:
            recent_turns = (
                self.turn_repository.list_recent_active_turns(
                    session_id=session_id,
                    limit=10,
                    scope=self.campaign_scope,
                )
            )
            if exclude_external_turn_id is not None:
                recent_turns = [
                    turn
                    for turn in recent_turns
                    if turn.external_turn_id != exclude_external_turn_id
                ]

        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to load recent active turn history"
            ) from exc

        try:
            context = self.context_builder.build(
                turn_context.world,
                normalized_query,
                recent_turns=recent_turns,
            )

        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "ContextBuilder failed to build context"
            ) from exc

        return {
            "campaign": {
                "id": turn_context.campaign.campaign_id,
                "name": turn_context.campaign.name,
                "system": turn_context.campaign.system,
                "tone": turn_context.campaign.tone,
                "summary": turn_context.campaign.summary,
            },
            "session": self._serialize_session(
                turn_context
            ),
            "active_character": (
                self._serialize_active_character(
                    turn_context
                )
            ),
            "query": normalized_query,
            "context": context,
        }

    def get_external_turn_state(
        self,
        external_turn_id: str,
    ) -> dict:
        """
        Devuelve el estado persistido de un turno externo.

        Este método permite que clientes como la extensión de
        SillyTavern reconstruyan su caché local de versionado
        después de una recarga o cambio de chat.

        El backend sigue siendo la fuente de verdad.
        """

        if not isinstance(
            external_turn_id,
            str,
        ):
            raise TypeError(
                "external_turn_id must be a string"
            )

        normalized_external_turn_id = (
            external_turn_id.strip()
        )

        if not normalized_external_turn_id:
            raise ValueError(
                "external_turn_id must not be empty"
            )

        if len(normalized_external_turn_id) > 500:
            raise ValueError(
                "external_turn_id must not be longer than 500 characters"
            )

        try:
            with get_conn() as conn:
                active_turn = (
                    self.turn_repository
                    .get_active_by_external_turn_id(
                        normalized_external_turn_id,
                        scope=self.campaign_scope,
                        conn=conn,
                    )
                )

        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to obtain external turn state"
            ) from exc

        try:
            versions = self.turn_repository.get_versions_by_external_turn_id(
                normalized_external_turn_id,
                scope=self.campaign_scope,
            )
        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to obtain external turn version history"
            ) from exc

        next_version = max(
            (turn.version for turn in versions),
            default=0,
        ) + 1

        if active_turn is None:
            return {
                "external_turn_id": normalized_external_turn_id,
                "exists": False,
                "active_version": 0,
                "next_version": next_version,
                "narrative": None,
            }

        return {
            "external_turn_id": normalized_external_turn_id,
            "exists": True,
            "active_version": active_turn.version,
            "next_version": next_version,
            "narrative": active_turn.narrative,
        }

    # ============================================================
    # EXTERNAL TURN
    # ============================================================

    def process_turn(
        self,
        player_input: str,
        narrative: str,
        external_turn_id: str | None = None,
        turn_version: int = 1,
    ) -> TurnResolutionResult:
        """Process a deprecated narrative-first turn for legacy clients."""
        return self.legacy_turn_service.process_turn(
            player_input=player_input,
            narrative=narrative,
            external_turn_id=external_turn_id,
            turn_version=turn_version,
        )

    def _process_turn_locked(
        self,
        player_input: str,
        narrative: str,
        external_turn_id: str | None = None,
        turn_version: int = 1,
    ) -> TurnResolutionResult:
        """Compatibility delegate for callers of the former private method."""
        return self.legacy_turn_service._process_turn_locked(
            player_input=player_input,
            narrative=narrative,
            external_turn_id=external_turn_id,
            turn_version=turn_version,
        )

    @staticmethod
    def _restore_world_state(target, snapshot) -> None:
        """Compatibility delegate for the legacy rollback helper."""
        LegacySillyTavernTurnService._restore_world_state(target, snapshot)

    # ============================================================
    # SERIALIZATION
    # ============================================================

    @staticmethod
    def _serialize_session(
        context: TurnContext,
    ) -> dict | None:

        session = context.current_session

        if session is None:
            return None

        return {
            "id": session.session_id,
            "number": session.number,
            "title": session.title,
            "summary": session.summary,
            "start_location": session.start_location,
            "end_location": session.end_location,
            "notes": session.notes,
        }

    @staticmethod
    def _serialize_active_character(
        context: TurnContext,
    ) -> dict | None:

        character = context.active_character

        if character is None:
            return None

        return {
            "entity_id": character.entity_id,
            "level": character.level,
            "class_name": character.class_name,
            "current_hp": character.current_hp,
            "max_hp": character.max_hp,
            "armor_class": character.armor_class,
            "strength": character.strength,
            "dexterity": character.dexterity,
            "constitution": character.constitution,
            "intelligence": character.intelligence,
            "wisdom": character.wisdom,
            "charisma": character.charisma,
            "proficiency_bonus": (
                character.proficiency_bonus
            ),
        }

    # ============================================================
    # VALIDATION
    # ============================================================

    @staticmethod
    def _validate_text(
        value: str,
        field_name: str,
    ) -> str:

        if not isinstance(
            value,
            str,
        ):
            raise TypeError(
                f"{field_name} must be a string"
            )

        value = value.strip()

        if not value:
            raise ValueError(
                f"{field_name} must not be empty"
            )

        return value