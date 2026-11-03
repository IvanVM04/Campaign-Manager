from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from database import init_db
from models.campaign_scope import CampaignScope
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from repositories.turn_repository import TurnRepository
from services.campaign_state_service import CampaignStateService
from services.campaign_turn_service import CampaignTurnService
from services.character_creation_service import CharacterCreationService
from services.context_builder import ContextBuilder
from services.dm_service import DMService
from services.llm_world_extractor import LLMWorldExtractor
from services.mechanics_adjudicator import MechanicsAdjudicator
from services.memory_search_service import MemorySearchService
from services.ollama_provider import OllamaProvider
from services.operation_parser import OperationParser
from services.silly_tavern_integration_service import (
    SillyTavernIntegrationService,
)
from services.turn_execution_lock import TurnExecutionLock
from services.turn_resolution_service import TurnResolutionService
from services.world_service import WorldService


@dataclass(slots=True)
class CampaignRuntime:
    """Conjunto de servicios y estado en memoria de una única campaña."""

    scope: CampaignScope
    campaign_repository: CampaignRepository
    character_repository: CharacterRepository
    entity_repository: EntityRepository
    turn_repository: TurnRepository
    world_service: WorldService
    campaign_state_service: CampaignStateService
    memory_search_service: MemorySearchService
    context_builder: ContextBuilder
    turn_execution_lock: TurnExecutionLock
    character_creation_service: CharacterCreationService
    campaign_turn_service: CampaignTurnService
    silly_tavern_integration_service: SillyTavernIntegrationService

    @property
    def campaign_id(self) -> int:
        return self.scope.campaign_id


class CampaignRuntimeFactory:
    """Crea y cachea runtimes independientes, uno por campaña."""

    def __init__(self) -> None:
        init_db()
        self._runtimes: dict[int, CampaignRuntime] = {}
        self._lock = RLock()
        self._campaign_repository = CampaignRepository()

    def get_runtime(self, campaign_id: int) -> CampaignRuntime:
        scope = CampaignScope(campaign_id)
        with self._lock:
            runtime = self._runtimes.get(scope.campaign_id)
            if runtime is not None:
                return runtime

            campaign = self._campaign_repository.get_campaign(
                scope.campaign_id
            )
            if campaign is None:
                raise LookupError(
                    f"campaign {scope.campaign_id} does not exist"
                )

            runtime = self._build_runtime(scope)
            self._runtimes[scope.campaign_id] = runtime
            return runtime

    def invalidate(self, campaign_id: int) -> None:
        """Descarta el estado en memoria para forzar una recarga posterior."""
        scope = CampaignScope(campaign_id)
        with self._lock:
            self._runtimes.pop(scope.campaign_id, None)

    def _build_runtime(self, scope: CampaignScope) -> CampaignRuntime:
        campaign_repository = CampaignRepository()
        character_repository = CharacterRepository()
        entity_repository = EntityRepository()
        turn_repository = TurnRepository()

        world_service = WorldService(campaign_id=scope.campaign_id)
        world_service.load()

        campaign_state_service = CampaignStateService(
            campaign_repository=campaign_repository,
            character_repository=character_repository,
            entity_repository=entity_repository,
            world_service=world_service,
            campaign_id=scope.campaign_id,
        )

        memory_search_service = MemorySearchService()
        context_builder = ContextBuilder(
            memory_search_service=memory_search_service,
        )
        turn_execution_lock = TurnExecutionLock()

        provider = OllamaProvider()
        operation_parser = OperationParser()
        dm_service = DMService(
            provider=provider,
            context_builder=context_builder,
        )
        extractor = LLMWorldExtractor(
            provider=provider,
            operation_parser=operation_parser,
        )
        mechanics_adjudicator = MechanicsAdjudicator(provider)
        turn_resolution_service = TurnResolutionService(
            dm_service=dm_service,
            world_service=world_service,
            extractor=extractor,
            mechanics_adjudicator=mechanics_adjudicator,
        )

        campaign_turn_service = CampaignTurnService(
            turn_resolution_service=turn_resolution_service,
            world_service=world_service,
            campaign_state_service=campaign_state_service,
            turn_repository=turn_repository,
            turn_execution_lock=turn_execution_lock,
        )

        silly_tavern_integration_service = SillyTavernIntegrationService(
            campaign_state_service=campaign_state_service,
            context_builder=context_builder,
            extractor=extractor,
            world_service=world_service,
            turn_repository=turn_repository,
            turn_execution_lock=turn_execution_lock,
        )

        character_creation_service = CharacterCreationService(
            campaign_repository=campaign_repository,
            entity_repository=entity_repository,
            character_repository=character_repository,
        )

        return CampaignRuntime(
            scope=scope,
            campaign_repository=campaign_repository,
            character_repository=character_repository,
            entity_repository=entity_repository,
            turn_repository=turn_repository,
            world_service=world_service,
            campaign_state_service=campaign_state_service,
            memory_search_service=memory_search_service,
            context_builder=context_builder,
            turn_execution_lock=turn_execution_lock,
            character_creation_service=character_creation_service,
            campaign_turn_service=campaign_turn_service,
            silly_tavern_integration_service=silly_tavern_integration_service,
        )
