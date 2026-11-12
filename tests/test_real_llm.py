import os

import pytest

from models.campaign_state import CampaignState
from models.entity import Entity
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.llm_world import LLMWorldExtractor
from operations.world_operations import (
    CreateEntityOperation,
    UpdateEntityOperation,
)
from services.llm_world.operation_parser import OperationParser
from services.providers import OllamaProvider

pytestmark = pytest.mark.real_llm


def make_context(world: WorldState | None = None) -> TurnContext:
    return TurnContext(
        campaign=CampaignState(),
        current_session=None,
        active_character=None,
        world=world or WorldState(),
    )


def make_extractor() -> LLMWorldExtractor:
    provider = OllamaProvider(
        model=os.getenv("CAMPAIGN_MANAGER_REAL_LLM_MODEL", "gemma4:26b"),
        base_url=os.getenv(
            "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL",
            OllamaProvider.DEFAULT_BASE_URL,
        ),
        timeout=float(os.getenv("CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT", "120")),
    )
    return LLMWorldExtractor(
        provider=provider,
        operation_parser=OperationParser(),
    )


def test_real_ollama_updates_a_known_npc_only_with_a_new_explicit_fact():
    world = WorldState(
        entities={
            1: Entity(
                id=1,
                name="Aldric",
                entity_type="npc",
                description="Tabernero de la posada del Dragón.",
                notes="Conoce los rumores del pueblo.",
            )
        }
    )
    operations = make_extractor().propose(
        "Aldric me muestra una cicatriz con forma de dragón en el antebrazo; "
        "es un detalle visible que no conocíamos.",
        make_context(world),
    )
    updates = [
        operation
        for operation in operations
        if isinstance(operation, UpdateEntityOperation)
    ]
    assert len(updates) == 1
    assert updates[0].entity_id == 1
    assert not any(
        isinstance(operation, CreateEntityOperation)
        for operation in operations
    )
    new_facts = (
        f"{updates[0].description or ''} {updates[0].notes or ''}"
    ).casefold()
    assert "cicatriz" in new_facts
    assert "dragón" in new_facts
    if updates[0].description is not None:
        assert "tabernero" in updates[0].description.casefold()
    if updates[0].notes is not None:
        assert "rumores" in updates[0].notes.casefold()


def test_real_ollama_proposal_avoids_ephemeral_scene_changes():
    operations = make_extractor().propose(
        "Me siento en una mesa, observo la chimenea y espero tranquilamente.",
        make_context(),
    )
    assert operations == []


def test_real_ollama_proposal_records_an_explicitly_introduced_npc():
    operations = make_extractor().propose(
        "En la posada conozco al tabernero Aldric. Se presenta por su nombre, "
        "me atiende detrás de la barra y explica que trabaja allí.",
        make_context(),
    )
    created = [
        operation
        for operation in operations
        if isinstance(operation, CreateEntityOperation)
    ]
    assert len(created) == 1
    assert created[0].name == "Aldric"
    assert created[0].entity_type == "npc"
    description = created[0].description.casefold()
    assert "tabernero" in description or "posada" in description


def test_real_ollama_proposal_does_not_change_an_existing_locked_door_after_failure():
    world = WorldState(
        entities={
            7: Entity(
                id=7,
                name="Puerta de piedra",
                entity_type="door",
                description="Antigua puerta de piedra cerrada con llave.",
                notes="El mecanismo de cierre sigue intacto.",
            )
        }
    )
    operations = make_extractor().propose(
        "Intento abrir la puerta de piedra con la llave que llevo, pero no encaja. "
        "No consigo abrirla y la puerta permanece cerrada con llave.",
        make_context(world),
    )
    assert operations == []
