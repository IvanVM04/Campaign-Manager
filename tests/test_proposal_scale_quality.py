from __future__ import annotations

import json

from models.campaign_state import CampaignState
from models.turn_context import TurnContext
from models.world_state import WorldState
from operations.world_operations import CreateEventOperation
from services.context import ContextBuilder
from services.llm_world import LLMWorldExtractor
from services.llm_world.operation_parser import OperationParser

from services.context import ContextBuilder
from services.llm_world import LLMWorldExtractor
from services.llm_world.operation_parser import OperationParser
from tests.context_scale_test_support import build_large_campaign_world


class SequenceProvider:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def make_turn_context(world: WorldState) -> TurnContext:
    return TurnContext(
        campaign=CampaignState(
            name="La guardia de Puerto Gris",
            current_location_id=2,
            summary="Investigación en una ciudad portuaria.",
        ),
        current_session=None,
        active_character=None,
        active_character_entity=world.entities[1],
        world=world,
    )


def test_large_context_proposal_uses_bounded_public_projection_and_parses_typed_result():
    world = build_large_campaign_world(entity_count=750)
    projection = ContextBuilder().build_proposal_context(
        world,
        "Fungoso",
        max_estimated_tokens=5000,
        mandatory_entity_ids=(1, 2),
    )
    response = json.dumps(
        {
            "operations": [
                {
                    "type": "create_event",
                    "event_id": "guardia-alerta",
                    "event_type": "public_notice",
                    "title": "La guardia anuncia un cierre del muelle",
                    "description": "El muelle permanecerá cerrado hasta el amanecer.",
                    "secret": False,
                    "metadata": {"entity_ids": [2]},
                }
            ]
        },
        ensure_ascii=False,
    )
    provider = SequenceProvider(response)
    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=OperationParser(),
        max_prompt_tokens=8192,
    )

    operations = extractor.propose(
        "Pregunta a la guardia por el cierre del muelle.",
        make_turn_context(world),
        context_projection=projection,
    )

    assert len(provider.prompts) == 1
    assert isinstance(operations[0], CreateEventOperation)
    assert operations[0].event_id == "guardia-alerta"
    assert "Puerto Gris" in provider.prompts[0]
    assert "Fungoso" in provider.prompts[0]
    assert "Fungoso recibe aviso: cambio de turno de la guardia" in provider.prompts[0]
    assert "ruta secreta de contrabando" not in provider.prompts[0]
    assert "Fungoso conoce la ruta secreta de contrabando" not in provider.prompts[0]
    assert "La capitana trabaja para los contrabandistas" not in provider.prompts[0]
    assert "Fungoso conoce la ruta secreta de contrabando" not in provider.prompts[0]
    assert len(provider.prompts[0].encode("utf-8")) <= 8192


def test_invalid_large_campaign_proposal_gets_one_compact_repair_without_world_context():
    world = build_large_campaign_world(entity_count=750)
    projection = ContextBuilder().build_proposal_context(
        world,
        "Fungoso",
        max_estimated_tokens=5000,
        mandatory_entity_ids=(1, 2),
    )
    provider = SequenceProvider(
        '{"operations":[{"type":"unknown_internal_operation"}]}',
        '{"operations":[]}',
    )
    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=OperationParser(),
        max_prompt_tokens=8192,
        max_repair_prompt_tokens=1400,
    )

    operations = extractor.propose(
        "Pregunta a la guardia por el cierre del muelle.",
        make_turn_context(world),
        context_projection=projection,
    )

    from models.world_context_projection import estimate_tokens

    assert operations == []
    assert len(provider.prompts) == 2
    assert "ruta secreta de contrabando" not in provider.prompts[0]
    assert "CONTEXTO ACTUAL DEL MUNDO" not in provider.prompts[1]
    assert "unknown_internal_operation" in provider.prompts[1]
    assert estimate_tokens(provider.prompts[1]) <= 1400
    assert len(provider.prompts[1].encode("utf-8")) <= 1400
