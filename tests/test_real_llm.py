import pytest

from models.campaign_state import CampaignState
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.llm_world import LLMWorldExtractor
from services.llm_world.operation_parser import OperationParser
from services.providers import OllamaProvider

pytestmark = pytest.mark.real_llm


def make_context() -> TurnContext:
    return TurnContext(
        campaign=CampaignState(),
        current_session=None,
        active_character=None,
        world=WorldState(),
    )


def make_extractor() -> LLMWorldExtractor:
    return LLMWorldExtractor(
        provider=OllamaProvider(),
        operation_parser=OperationParser(),
    )


def test_real_ollama_structured_proposal_returns_operations():
    operations = make_extractor().propose(
        "Quiero encontrar al tabernero Aldric y preguntarle por los rumores del pueblo.",
        make_context(),
    )
    assert isinstance(operations, list)
    assert all(operation is not None for operation in operations)


def test_real_ollama_proposal_avoids_ephemeral_scene_changes():
    operations = make_extractor().propose(
        "Me siento en una mesa, observo la chimenea y espero tranquilamente.",
        make_context(),
    )
    assert operations == []


def test_real_ollama_proposal_records_an_explicitly_introduced_npc():
    from operations.world_operations import CreateEntityOperation

    operations = make_extractor().propose(
        "Conozco al tabernero Aldric; se presenta por su nombre y habla conmigo.",
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


def test_real_ollama_proposal_does_not_turn_failed_attempt_into_success():
    operations = make_extractor().propose(
        "Intento abrir una antigua puerta de piedra cerrada con llave, pero no consigo abrirla y permanece cerrada.",
        make_context(),
    )
    assert operations == []
