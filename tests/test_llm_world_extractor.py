import json

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.entity import Entity
from models.item import Item, ItemInstance
from models.turn_context import TurnContext
from models.world_state import WorldState
from operations.character_operations import ChangeCharacterHpOperation
from operations.world_operations import CreateEntityOperation, WorldOperation
from services.llm_world_extractor import (
    LLMExtractionError,
    LLMWorldExtractor,
)
from services.operation_parser import OperationParser


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


def test_valid_response_returns_operations():
    operation = FakeOperation()

    response = json.dumps(
        {
            "operations": [
                {
                    "type": "create_entity",
                    "name": "Aldric",
                }
            ]
        }
    )

    extractor, provider_calls, parser = (
        make_extractor(
            response,
            operation,
        )
    )

    result = extractor.extract(
        "Aldric entra en la taberna.",
        make_context(),
    )

    assert result == [operation]

    assert len(provider_calls) == 1

    assert parser.calls == [
        {
            "operations": [
                {
                    "type": "create_entity",
                    "name": "Aldric",
                }
            ]
        }
    ]


def test_empty_text_does_not_call_provider():
    called = False

    def provider(prompt):
        nonlocal called
        called = True
        return "{}"

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FakeParser(
            FakeOperation()
        ),
    )

    result = extractor.extract(
        "   ",
        make_context(),
    )

    assert result == []
    assert called is False


def test_invalid_provider_response_type_fails():
    def provider(prompt):
        return None

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FakeParser(
            FakeOperation()
        ),
    )

    with pytest.raises(
        LLMExtractionError,
        match="must be a string",
    ):
        extractor.extract(
            "algo ocurrió",
            make_context(),
        )


def test_empty_provider_response_fails():
    def provider(prompt):
        return "   "

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FakeParser(
            FakeOperation()
        ),
    )

    with pytest.raises(
        LLMExtractionError,
        match="empty response",
    ):
        extractor.extract(
            "algo ocurrió",
            make_context(),
        )


def test_invalid_json_fails():
    def provider(prompt):
        return "esto no es json"

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FakeParser(
            FakeOperation()
        ),
    )

    with pytest.raises(
        LLMExtractionError,
        match="valid JSON",
    ):
        extractor.extract(
            "algo ocurrió",
            make_context(),
        )


def test_json_array_fails():
    def provider(prompt):
        return "[]"

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FakeParser(
            FakeOperation()
        ),
    )

    with pytest.raises(
        LLMExtractionError,
        match="JSON object",
    ):
        extractor.extract(
            "algo ocurrió",
            make_context(),
        )


def test_missing_operations_fails():
    def provider(prompt):
        return json.dumps(
            {
                "something": []
            }
        )

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FakeParser(
            FakeOperation()
        ),
    )

    with pytest.raises(
        LLMExtractionError,
        match="Missing",
    ):
        extractor.extract(
            "algo ocurrió",
            make_context(),
        )


def test_operations_must_be_list():
    def provider(prompt):
        return json.dumps(
            {
                "operations": {}
            }
        )

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FakeParser(
            FakeOperation()
        ),
    )

    with pytest.raises(
        LLMExtractionError,
        match="must be a list",
    ):
        extractor.extract(
            "algo ocurrió",
            make_context(),
        )


def test_parser_rejects_invalid_operation():
    class FailingParser:
        def parse(self, data):
            raise ValueError(
                "Operation must be an object"
            )

    def provider(prompt):
        return json.dumps(
            {
                "operations": [
                    "invalid"
                ]
            }
        )

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FailingParser(),
    )

    with pytest.raises(
        LLMExtractionError,
        match="Failed to parse operations",
    ):
        extractor.extract(
            "algo ocurrió",
            make_context(),
        )


def test_parser_failure_becomes_extraction_error():
    class FailingParser:
        def parse(self, data):
            raise ValueError(
                "invalid operation"
            )

    def provider(prompt):
        return json.dumps(
            {
                "operations": [
                    {
                        "type": "invalid"
                    }
                ]
            }
        )

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FailingParser(),
    )

    with pytest.raises(
        LLMExtractionError,
        match="Failed to parse operations",
    ):
        extractor.extract(
            "algo ocurrió",
            make_context(),
        )


def test_parser_result_must_be_world_operation():
    class BadParser:
        def parse(self, data):
            return "not an operation"

    def provider(prompt):
        return json.dumps(
            {
                "operations": [
                    {
                        "type": "something"
                    }
                ]
            }
        )

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=BadParser(),
    )

    with pytest.raises(
        LLMExtractionError,
        match="invalid result",
    ):
        extractor.extract(
            "algo ocurrió",
            make_context(),
        )


def test_extractor_does_not_modify_world():
    operation = FakeOperation()

    response = json.dumps(
        {
            "operations": [
                {
                    "type": "create_entity"
                }
            ]
        }
    )

    extractor, _, _ = make_extractor(
        response,
        operation,
    )

    world = WorldState()

    before = repr(world)

    extractor.extract(
        "Aldric aparece.",
        make_context(world=world),
    )

    after = repr(world)

    assert after == before


def test_callable_interface_matches_extractor():
    operation = FakeOperation()

    response = json.dumps(
        {
            "operations": [
                {
                    "type": "create_entity"
                }
            ]
        }
    )

    extractor, _, _ = make_extractor(
        response,
        operation,
    )

    result = extractor(
        "Aldric aparece.",
        make_context(),
    )

    assert result == [operation]

def test_parser_receives_complete_payload():
    operation = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Un guerrero.",
        notes="",
        active=True,
    )

    parser = FakeParser(
        operations=[operation]
    )

    provider = FakeProvider(
        json.dumps(
            {
                "operations": [
                    {
                        "type": "create_entity",
                        "name": "Aldric",
                        "entity_type": "npc",
                        "description": "Un guerrero.",
                        "notes": "",
                        "active": True,
                    }
                ]
            }
        )
    )

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    extractor.extract(
        "Aldric aparece en la taberna.",
        make_context(),
    )

    assert len(parser.calls) == 1

    assert parser.calls[0] == {
        "operations": [
            {
                "type": "create_entity",
                "name": "Aldric",
                "entity_type": "npc",
                "description": "Un guerrero.",
                "notes": "",
                "active": True,
            }
        ]
    }

def test_parser_failure_is_wrapped():
    parser = FakeParser(
        exception=ValueError("invalid operation")
    )

    provider = FakeProvider(
        '{"operations": []}'
    )

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    with pytest.raises(
        LLMExtractionError,
        match="Failed to parse operations",
    ):
        extractor.extract(
            "Algo ocurre.",
            make_context(),
        )

def test_multiple_operations_are_returned():
    operation_1 = CreateEntityOperation(
        name="Aldric",
        entity_type="npc",
        description="Guerrero.",
        notes="",
        active=True,
    )

    operation_2 = CreateEntityOperation(
        name="Mara",
        entity_type="npc",
        description="Mercader.",
        notes="",
        active=True,
    )

    parser = FakeParser(
        operations=[
            operation_1,
            operation_2,
        ]
    )

    provider = FakeProvider(
        '{"operations": ['
        '{"type": "create_entity"},'
        '{"type": "create_entity"}'
        ']}'
    )

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    result = extractor.extract(
        "Aldric y Mara aparecen.",
        make_context(),
    )

    assert result == [
        operation_1,
        operation_2,
    ]

def test_prompt_includes_known_entity_ids():
    provider = FakeProvider(
        '{"operations": []}'
    )

    parser = FakeParser()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    world = WorldState()

    world.entities[1] = Entity(
        id=1,
        name="Aldric",
        entity_type="npc",
    )

    extractor.extract(
        "Aldric aparece.",
        make_context(world=world),
    )

    assert len(provider.calls) == 1

    assert "ID 1" in provider.calls[0]
    assert "Aldric" in provider.calls[0]
    assert "npc" in provider.calls[0]

def test_prompt_does_not_include_unrelated_world_state():
    provider = FakeProvider(
        '{"operations": []}'
    )

    parser = FakeParser()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    world = WorldState()

    world.entities[1] = Entity(
        id=1,
        name="Aldric",
        entity_type="npc",
        description="Mercader de Vorder's Hold.",
    )

    extractor.extract(
        "Aldric aparece.",
        make_context(world=world),
    )

    prompt = provider.calls[0]

    assert "Aldric" in prompt
    assert "Mercader de Vorder's Hold" not in prompt

def test_extractor_prompt_includes_active_character():
    provider = FakeProvider(
        '{"operations": []}'
    )

    parser = FakeParser()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    entity = Entity(
        id=1,
        name="Fungoso",
        entity_type="character",
    )

    character = CharacterState(
        entity_id=1,
        level=3,
        class_name="fighter",
        current_hp=12,
        max_hp=20,
        armor_class=16,
    )

    world = WorldState()

    world.entities[1] = entity

    context = make_context(
        world=world,
        active_character=character,
        active_character_entity=entity,
    )

    extractor.extract(
        "Fungoso recibe un golpe.",
        context,
    )

    prompt = provider.calls[0]

    assert "PERSONAJE ACTIVO" in prompt
    assert "Fungoso" in prompt
    assert "ID de entidad: 1" in prompt
    assert "Nivel: 3" in prompt
    assert "Clase: fighter" in prompt
    assert "HP actual: 12" in prompt
    assert "HP máximo: 20" in prompt
    assert "CA: 16" in prompt


def test_extractor_prompt_handles_missing_active_character():
    provider = FakeProvider(
        '{"operations": []}'
    )

    parser = FakeParser()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    context = make_context()

    extractor.extract(
        "La puerta se abre.",
        context,
    )

    prompt = provider.calls[0]

    assert "PERSONAJE ACTIVO" in prompt
    assert "No hay personaje activo." in prompt

def test_prompt_includes_known_items_and_item_instances():
    provider = FakeProvider(
        '{"operations": []}'
    )

    parser = FakeParser()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    world = WorldState()

    world.items[10] = Item(
        id=10,
        name="Espada de hierro",
        description="Una espada sencilla.",
    )

    world.item_instances[25] = ItemInstance(
        id=25,
        item_id=10,
        instance_number=1,
        owner_id=1,
        location_id=2,
        condition="intacto",
        notes="Tiene una runa.",
        active=True,
    )

    extractor.extract(
        "La espada tiene una runa.",
        make_context(world=world),
    )

    prompt = provider.calls[0]

    assert "ITEMS CONOCIDOS" in prompt
    assert "Espada de hierro" in prompt
    assert "ID 10" in prompt

    assert "INSTANCIAS DE OBJETOS CONOCIDAS" in prompt
    assert "ID 25" in prompt
    assert "owner_id=1" in prompt
    assert "location_id=2" in prompt
    assert "condition=intacto" in prompt

def test_prompt_explains_existing_item_instance_pickup():
    provider = FakeProvider(
        '{"operations": []}'
    )

    parser = FakeParser()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    world = WorldState()

    world.entities[1] = Entity(
        id=1,
        name="Darian",
        entity_type="character",
    )

    world.items[10] = Item(
        id=10,
        name="Espada de hierro",
        description="Una espada sencilla.",
    )

    world.item_instances[25] = ItemInstance(
        id=25,
        item_id=10,
        instance_number=1,
        owner_id=None,
        location_id=None,
        condition="intacto",
        notes="",
        active=True,
    )

    extractor.extract(
        "Darian recoge la espada y se la guarda.",
        make_context(world=world),
    )

    prompt = provider.calls[0]

    assert "INSTANCIAS DE OBJETOS CONOCIDAS" in prompt

    # Reglas de recogida
    assert "RECOGER OBJETOS" in prompt
    assert "si la instancia no tiene propietario" in prompt
    assert "actualizar su propietario" in prompt

    # Identidad de la entidad conocida
    assert "- ID 1: Darian (character)" in prompt

    # Estado de la instancia existente
    assert "- ID 25: Espada de hierro" in prompt
    assert "owner_id=None" in prompt
    assert "location_id=None" in prompt


def test_prompt_requires_existing_instance_to_be_updated_instead_of_created():
    provider = FakeProvider(
        '{"operations": []}'
    )

    parser = FakeParser()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    world = WorldState()

    world.items[10] = Item(
        id=10,
        name="Jarra de cerveza",
        description="Una jarra.",
    )

    world.item_instances[25] = ItemInstance(
        id=25,
        item_id=10,
        instance_number=1,
        owner_id=None,
        location_id=None,
        condition="llena",
        notes="",
        active=True,
    )

    extractor.extract(
        "Darian recoge la jarra de cerveza y se la guarda.",
        make_context(world=world),
    )

    prompt = provider.calls[0]

    assert "NO crees otra instancia porque vuelva a aparecer" in prompt

    assert (
        "solo crea una instancia nueva si la narrativa confirma "
        "una copia física nueva"
    ) in prompt

    assert "instancia física EXISTENTE" in prompt

    assert "update_item_instance" in prompt

def test_prompt_documents_update_item_instance():
    provider = FakeProvider(
        '{"operations": []}'
    )

    parser = FakeParser()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    extractor.extract(
        "La espada está dañada.",
        make_context(),
    )

    prompt = provider.calls[0]

    assert "update_item_instance" in prompt
    assert "instance_id" in prompt
    assert "condition" in prompt

def test_prompt_documents_all_supported_operations():
    provider = FakeProvider(
        '{"operations": []}'
    )

    parser = FakeParser()

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=parser,
    )

    extractor.extract(
        "Algo ocurre.",
        make_context(),
    )

    prompt = provider.calls[0]

    expected_operations = [
        "create_entity",
        "update_entity",
        "create_item",
        "create_item_instance",
        "transfer_item",
        "update_item_instance",
        "create_resource",
        "gain_resource",
        "spend_resource",
        "transfer_resource",
        "create_relation",
        "update_relation",
        "remove_relation",
        "create_event",
    ]

    for operation_type in expected_operations:
        assert operation_type in prompt


def test_extractor_rejects_character_hp_operations_from_narrative():
    provider = FakeProvider(
        json.dumps(
            {
                "operations": [
                    {
                        "type": "change_character_hp",
                        "entity_id": 1,
                        "amount": -7,
                    }
                ]
            }
        )
    )
    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=OperationParser(),
    )

    with pytest.raises(
        LLMExtractionError,
        match="require verified rules-engine resolution",
    ):
        extractor.extract(
            "El guardia causa 7 puntos de daño.",
            make_context(),
        )


def test_extractor_prompt_disallows_mechanical_character_updates():
    provider = FakeProvider('{"operations": []}')
    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=FakeParser(),
    )

    extractor.extract(
        "El guardia causa 7 puntos de daño.",
        make_context(),
    )

    prompt = provider.calls[0]
    assert "La operación change_character_hp NO está habilitada" in prompt
    assert "NO generes operaciones para modificar" in prompt
    assert "No hay operaciones de personaje habilitadas" in prompt
