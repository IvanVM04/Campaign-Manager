# ruff: noqa: F401, I001

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

import pytest

from models.campaign_scope import CampaignScope
from models.character_state import CharacterState
from models.entity import Entity
from models.schemas import (
    SillyTavernClarificationIn,
    SillyTavernContextIn,
    SillyTavernTurnIn,
)
from operations.world_operations import CreateEntityOperation
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from repositories.campaign_state_version_repository import (
    CampaignStateVersionRepository,
)
from repositories.world_snapshot_repository import WorldSnapshotRepository
from integrations.adapters.silly_tavern import (
    SillyTavernContextAdapter,
    SillyTavernIntegrationService,
    SillyTavernIntegrationServiceConflictError,
    SillyTavernIntegrationServiceError,
)
from services.turns import LegacySillyTavernTurnService, TurnExecutionLock
from services.world import WorldService

def _compose_service(
    *,
    campaign_state_service,
    context_builder,
    extractor,
    world_service,
    turn_repository,
    turn_execution_lock,
):
    campaign_scope = CampaignScope(world_service.campaign_id)
    context_adapter = SillyTavernContextAdapter(
        campaign_scope=campaign_scope,
        campaign_state_service=campaign_state_service,
        context_builder=context_builder,
        turn_repository=turn_repository,
    )
    legacy_turn_service = LegacySillyTavernTurnService(
        campaign_scope=campaign_scope,
        campaign_state_service=campaign_state_service,
        extractor=extractor,
        world_service=world_service,
        turn_repository=turn_repository,
        turn_execution_lock=turn_execution_lock,
        state_version_repository=CampaignStateVersionRepository(),
        world_snapshot_repository=WorldSnapshotRepository(),
        error_type=SillyTavernIntegrationServiceError,
        conflict_error_type=SillyTavernIntegrationServiceConflictError,
    )
    return SillyTavernIntegrationService(
        context_adapter=context_adapter,
        legacy_turn_service=legacy_turn_service,
    )


def _build_service():
    from repositories.turn_repository import TurnRepository
    from services.campaign import CampaignStateService
    from services.context import ContextBuilder
    from services.llm_world import LLMWorldExtractor
    from services.llm_world.operation_parser import OperationParser

    world_service = WorldService()
    campaign_state_service = CampaignStateService(
        campaign_repository=CampaignRepository(),
        character_repository=CharacterRepository(),
        entity_repository=EntityRepository(),
        world_service=world_service,
    )
    context_builder = ContextBuilder()
    extractor = LLMWorldExtractor(
        provider=lambda prompt: '{"operations": []}',
        operation_parser=OperationParser(),
    )
    turn_repository = TurnRepository()
    turn_execution_lock = TurnExecutionLock()
    service = _compose_service(
        campaign_state_service=campaign_state_service,
        context_builder=context_builder,
        extractor=extractor,
        world_service=world_service,
        turn_repository=turn_repository,
        turn_execution_lock=turn_execution_lock,
    )
    return (
        service,
        context_builder,
        extractor,
        world_service,
        turn_repository,
    )

# ============================================================
# SERVICE - CONTEXT
# ============================================================
