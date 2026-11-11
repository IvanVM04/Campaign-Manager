from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from database import init_db
from models.campaign_scope import CampaignScope
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.combat_encounter_repository import CombatEncounterRepository
from repositories.creature_repository import CreatureRepository
from repositories.entity_repository import EntityRepository
from repositories.persistent_effect_repository import PersistentEffectRepository
from repositories.turn_repository import TurnRepository
from repositories.weapon_equipment_repository import WeaponEquipmentRepository
from services.campaign import (
    CampaignStateService,
    EffectiveConditionService,
    PersistentEffectService,
)
from services.characters import (
    CharacterApplier,
    CharacterCreationService,
    CharacterService,
)
from services.combat import (
    CombatAttackService,
    CombatEncounterService,
    WeaponEquipmentService,
)
from services.context import ContextBuilder, MemorySearchService
from services.llm_world import LLMWorldExtractor, OperationParser
from services.providers import LLMSettings
from services.silly_tavern_integration_service import (
    SillyTavernIntegrationService,
)
from services.turns import DMService, MechanicsAdjudicator, TurnExecutionLock
from services.turns.durable_native_turn_service import DurableNativeTurnService
from services.turns.turn_resolution_service import TurnResolutionService
from services.world import WorldService


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
    combat_encounter_service: CombatEncounterService
    combat_attack_service: CombatAttackService
    weapon_equipment_service: WeaponEquipmentService
    persistent_effect_service: PersistentEffectService
    durable_native_turn_service: DurableNativeTurnService
    silly_tavern_integration_service: SillyTavernIntegrationService

    @property
    def campaign_id(self) -> int:
        return self.scope.campaign_id


class CampaignRuntimeFactory:
    """Crea y cachea runtimes independientes, uno por campaña."""

    def __init__(self, llm_settings: LLMSettings | None = None) -> None:
        if llm_settings is not None and not isinstance(llm_settings, LLMSettings):
            raise TypeError("llm_settings must be an LLMSettings instance or None")
        init_db()
        self._llm_settings = llm_settings or LLMSettings.from_env()
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

        character_applier = CharacterApplier(
            CharacterService(character_repository)
        )
        world_service = WorldService(
            campaign_id=scope.campaign_id,
            character_applier=character_applier,
        )
        world_service.load()

        persistent_effect_repository = PersistentEffectRepository()
        effective_condition_service = EffectiveConditionService(persistent_effect_repository)

        campaign_state_service = CampaignStateService(
            campaign_repository=campaign_repository,
            character_repository=character_repository,
            entity_repository=entity_repository,
            world_service=world_service,
            campaign_id=scope.campaign_id,
            effective_condition_service=effective_condition_service,
        )

        memory_search_service = MemorySearchService()
        context_builder = ContextBuilder(
            memory_search_service=memory_search_service,
        )
        turn_execution_lock = TurnExecutionLock()

        narrative_provider = self._llm_settings.create_provider("narrative")
        extraction_provider = self._llm_settings.create_provider("extraction")
        mechanics_provider = self._llm_settings.create_provider("mechanics")
        operation_parser = OperationParser()
        dm_service = DMService(
            provider=narrative_provider,
            context_builder=context_builder,
        )
        extractor = LLMWorldExtractor(
            provider=extraction_provider,
            operation_parser=operation_parser,
        )
        mechanics_adjudicator = MechanicsAdjudicator(mechanics_provider, context_builder)
        turn_resolution_service = TurnResolutionService(
            dm_service=dm_service,
            world_service=world_service,
            extractor=extractor,
            mechanics_adjudicator=mechanics_adjudicator,
        )

        durable_native_turn_service = DurableNativeTurnService(
            scope=scope,
            resolver=turn_resolution_service,
            world_service=world_service,
            context_service=campaign_state_service,
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
        encounter_repository = CombatEncounterRepository()
        creature_repository = CreatureRepository()
        weapon_equipment_repository = WeaponEquipmentRepository()
        weapon_equipment_service = WeaponEquipmentService(weapon_equipment_repository)
        combat_encounter_service = CombatEncounterService(
            repository=encounter_repository,
            character_repository=character_repository,
            entity_repository=entity_repository,
            creature_repository=creature_repository,
            world_service=world_service,
            persistent_effect_repository=persistent_effect_repository,
            equipment_service=weapon_equipment_service,
        )
        combat_attack_service = CombatAttackService(
            encounter_repository=encounter_repository,
            character_repository=character_repository,
            weapon_repository=weapon_equipment_repository,
            effective_condition_service=effective_condition_service,
            creature_repository=creature_repository,
            equipment_service=weapon_equipment_service,
        )
        persistent_effect_service = PersistentEffectService(
            repository=persistent_effect_repository,
            entity_repository=entity_repository,
            campaign_id=scope.campaign_id,
            encounter_repository=encounter_repository,
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
            combat_encounter_service=combat_encounter_service,
            combat_attack_service=combat_attack_service,
            weapon_equipment_service=weapon_equipment_service,
            persistent_effect_service=persistent_effect_service,
            durable_native_turn_service=durable_native_turn_service,
            silly_tavern_integration_service=silly_tavern_integration_service,
        )
