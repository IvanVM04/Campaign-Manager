# ruff: noqa: F401
import json

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.entity import Entity
from models.event import Event
from models.item import Item, ItemInstance
from models.turn_context import TurnContext
from models.world_state import WorldState
from operations.world_operations import CreateEntityOperation, WorldOperation
from services.llm_world import (
    LLMExtractionError,
    LLMWorldExtractor,
    LLMWorldResponseParser,
)
from services.llm_world.operation_parser import OperationParser


class FakeOperation(WorldOperation):
    pass


class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, prompt):
        self.calls.append(prompt)
        return self.response


class FakeParser:
    def __init__(
        self,
        operations=None,
        exception=None,
    ):
        self.operations = (
            []
            if operations is None
            else operations
        )

        self.exception = exception
        self.calls = []

    def parse(self, payload):
        self.calls.append(payload)

        if self.exception is not None:
            raise self.exception

        return self.operations


def make_extractor(response, operation):
    provider_calls = []

    def provider(prompt):
        provider_calls.append(prompt)
        return response

    parser = FakeParser(
        operations=[operation]
    )

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    return (
        extractor,
        provider_calls,
        parser,
    )

def make_context(
    world=None,
    active_character=None,
    active_character_entity=None,
):
    if world is None:
        world = WorldState()

    return TurnContext(
        campaign=CampaignState(),
        current_session=None,
        active_character=active_character,
        world=world,
        active_character_entity=active_character_entity,
    )

def test_propose_uses_player_intent_not_generated_narrative():
    operation = FakeOperation()
    provider = FakeProvider(
        json.dumps({"operations": [{"type": "create_entity", "name": "Aldric"}]})
    )
    parser = FakeParser(operations=[operation])
    extractor = LLMWorldExtractor(provider=provider, operation_parser=parser)

    result = extractor.propose(
        "Quiero buscar al tabernero llamado Aldric.",
        make_context(),
    )

    assert result == [operation]
    assert len(provider.calls) == 1
    prompt = provider.calls[0]
    assert "Quiero buscar al tabernero llamado Aldric." in prompt
    assert "INTENCIÓN DEL JUGADOR" in prompt
    assert "NARRATIVA A ANALIZAR" not in prompt
    assert "narrativa ya generada" not in prompt
    assert "Las operaciones son propuestas, no hechos confirmados." in prompt

def test_propose_separates_confirmed_mechanics_with_real_newlines():
    from types import SimpleNamespace

    provider = FakeProvider(json.dumps({"operations": []}))
    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FakeParser(),
    )
    mechanics_result = SimpleNamespace(
        to_prompt_text=lambda: "Resultado: éxito en la prueba de percepción."
    )

    extractor.propose(
        "Busco huellas en el barro.",
        make_context(),
        mechanics_result=mechanics_result,
    )

    prompt = provider.calls[0]
    assert (
        "\n\nRESULTADO MECÁNICO CONFIRMADO POR EL MOTOR\n"
        "Resultado: éxito en la prueba de percepción."
    ) in prompt
    assert r"\n\nRESULTADO MECÁNICO CONFIRMADO POR EL MOTOR\n" not in prompt

def test_propose_empty_intent_does_not_call_provider():
    provider = FakeProvider(json.dumps({"operations": []}))
    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FakeParser(),
    )

    assert extractor.propose("   ", make_context()) == []
    assert provider.calls == []

def test_proposal_context_excludes_secret_world_events():
    world = WorldState(events={
        "public-discovery": Event(
            id="public-discovery",
            event_type="discovery",
            title="La campana rota",
            description="Falta la campana del campanario.",
            secret=False,
        ),
        "gm-secret": Event(
            id="gm-secret",
            event_type="secret",
            title="Nilo está retenido en la cantera",
            description="El mensajero está encerrado por los contrabandistas.",
            consequences="El grupo todavía no conoce esta verdad.",
            secret=True,
        ),
    })
    provider = FakeProvider(json.dumps({"operations": []}))
    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FakeParser(),
    )

    from services.context import ContextBuilder

    projection = ContextBuilder().build_proposal_context(
        world,
        "El grupo examina el campanario.",
        max_estimated_tokens=4096,
    )
    extractor.propose(
        "El grupo examina el campanario.",
        make_context(world=world),
        context_projection=projection,
    )

    prompt = provider.calls[0]
    assert "La campana rota" in prompt
    assert "Nilo está retenido en la cantera" not in prompt
    assert "El mensajero está encerrado por los contrabandistas" not in prompt

def test_propose_repairs_an_unsupported_operation_once():
    responses = iter([
        '{"operations": [{"type": "start_interaction", "entity_id": 2}]}',
        '{"operations": []}',
    ])
    prompts = []

    def sequenced_provider(prompt):
        prompts.append(prompt)
        return next(responses)

    extractor = LLMWorldExtractor(
        provider=sequenced_provider,
        operation_parser=OperationParser(),
    )

    result = extractor.propose("Hablo con Mara.", make_context())

    assert result == []
    assert len(prompts) == 2
    assert "start_interaction" in prompts[1]
    assert "create_entity" in prompts[1]
    assert "No inventes operaciones" in prompts[1]

def test_propose_stops_after_one_failed_repair_attempt():
    prompts = []

    def invalid_provider(prompt):
        prompts.append(prompt)
        return '{"operations": [{"type": "start_interaction"}]}'

    extractor = LLMWorldExtractor(
        provider=invalid_provider,
        operation_parser=OperationParser(),
    )

    with pytest.raises(
        LLMExtractionError,
        match="after one repair attempt",
    ):
        extractor.propose("Hablo con Mara.", make_context())

    assert len(prompts) == 2
