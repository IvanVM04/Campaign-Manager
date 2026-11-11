# ruff: noqa: F401, I001

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

import pytest

import services.silly_tavern_integration_service as integration_module
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
from services.silly_tavern_integration_service import (
    SillyTavernIntegrationService,
    SillyTavernIntegrationServiceConflictError,
)
from services.turns import TurnExecutionLock
from services.world import WorldService

def _build_service():
    from repositories.turn_repository import (
        TurnRepository,
    )
    from services.campaign import (
        CampaignStateService,
    )
    from services.context import (
        ContextBuilder,
    )
    from services.llm_world import (
        LLMWorldExtractor,
    )
    from services.llm_world.operation_parser import (
        OperationParser,
    )

    world_service = WorldService()

    campaign_state_service = (
        CampaignStateService(
            campaign_repository=(
                CampaignRepository()
            ),
            character_repository=(
                CharacterRepository()
            ),
            entity_repository=(
                EntityRepository()
            ),
            world_service=world_service,
        )
    )

    context_builder = ContextBuilder()

    extractor = LLMWorldExtractor(
        provider=lambda prompt: (
            '{"operations": []}'
        ),
        operation_parser=OperationParser(),
    )

    _turn_repository = TurnRepository()

    turn_execution_lock = TurnExecutionLock()

    service = (
        SillyTavernIntegrationService(
            campaign_state_service=(
                campaign_state_service
            ),
            context_builder=context_builder,
            extractor=extractor,
            world_service=world_service,
            turn_repository=_turn_repository,
            turn_execution_lock=turn_execution_lock,
        )
    )

    return (
        service,
        context_builder,
        extractor,
        world_service,
        _turn_repository,
    )


# ============================================================
# SERVICE - CONTEXT
# ============================================================
