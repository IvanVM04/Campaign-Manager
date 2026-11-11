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

def test_silly_tavern_clarification_schema_requires_stable_answer_identity():
    data = SillyTavernClarificationIn(
        pending_clarification_id="42:challenge-token-long-enough",
        answer="La puerta de roble.",
        answer_external_turn_id="stable-answer-message-id",
        query="Estado actual de la campaña.",
    )

    assert data.answer_external_turn_id == "stable-answer-message-id"

def test_silly_tavern_context_schema_accepts_query():
    data = SillyTavernContextIn(
        query="Entro en la taberna."
    )

    assert data.query == (
        "Entro en la taberna."
    )

def test_silly_tavern_context_schema_strips_query():
    data = SillyTavernContextIn(
        query="  Entro en la taberna.  "
    )

    assert data.query == (
        "Entro en la taberna."
    )

def test_silly_tavern_context_schema_rejects_empty_query():
    with pytest.raises(ValueError):
        SillyTavernContextIn(
            query="   "
        )

def test_silly_tavern_turn_schema_accepts_valid_data():
    data = SillyTavernTurnIn(
        player_input="Abro la puerta.",
        narrative=(
            "La puerta se abre con un chirrido "
            "lento y desagradable."
        ),
    )

    assert data.player_input == (
        "Abro la puerta."
    )

    assert data.narrative == (
        "La puerta se abre con un chirrido "
        "lento y desagradable."
    )

def test_silly_tavern_turn_schema_strips_text():
    data = SillyTavernTurnIn(
        player_input="  Abro la puerta.  ",
        narrative="  La puerta se abre.  ",
    )

    assert data.player_input == (
        "Abro la puerta."
    )

    assert data.narrative == (
        "La puerta se abre."
    )

def test_silly_tavern_turn_schema_rejects_empty_player_input():
    with pytest.raises(ValueError):
        SillyTavernTurnIn(
            player_input="   ",
            narrative="Narrativa.",
        )

def test_silly_tavern_turn_schema_rejects_empty_narrative():
    with pytest.raises(ValueError):
        SillyTavernTurnIn(
            player_input="Abro la puerta.",
            narrative="   ",
        )


# ============================================================
# API
# ============================================================
