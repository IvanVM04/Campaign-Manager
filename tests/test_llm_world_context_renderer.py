from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.entity import Entity
from models.event import Event
from models.item import Item, ItemInstance
from models.relation import Relation
from models.resource import Resource
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.llm_world_context_renderer import LLMWorldContextRenderer


def make_context(world=None, active_character=None):
    return TurnContext(
        campaign=CampaignState(),
        current_session=None,
        active_character=active_character,
        world=world or WorldState(),
    )


def test_context_renderer_returns_empty_section_fallbacks():
    rendered = LLMWorldContextRenderer.build_context(make_context())

    assert rendered == {
        "character_block": "No hay personaje activo.",
        "known_entities": "- Ninguna",
        "known_items": "- Ninguno",
        "known_item_instances": "- Ninguna",
        "known_resources": "- Ninguno",
        "known_relations": "- Ninguna",
        "known_events": "- Ninguno",
    }


def test_context_renderer_formats_world_snapshot_and_hides_secret_events():
    world = WorldState(
        entities={
            1: Entity(id=1, name="Aldric", entity_type="npc"),
            2: Entity(id=2, name="Guardia", entity_type="npc"),
        },
        items={
            10: Item(id=10, name="Espada", weapon_key="longsword"),
        },
        item_instances={
            25: ItemInstance(
                id=25,
                item_id=10,
                instance_number=1,
                owner_id=1,
            ),
        },
        resources={
            5: Resource(
                id=5,
                name="Oro",
                resource_type="currency",
                unit="moedas",
            ),
        },
        relations={
            "r1": Relation(
                id="r1",
                subject_id=1,
                relation_type="aliado_de",
                target_id=2,
                metadata={"since": "ayer"},
            ),
        },
        events={
            "public": Event(
                id="public",
                event_type="discovery",
                title="Puerta abierta",
            ),
            "secret": Event(
                id="secret",
                event_type="secret",
                title="Identidad oculta",
                secret=True,
            ),
        },
    )
    character = CharacterState(
        entity_id=1,
        level=3,
        class_name="Guerrero",
        current_hp=20,
        max_hp=24,
    )

    before = repr(world)
    rendered = LLMWorldContextRenderer.build_context(
        make_context(world, character)
    )

    assert "ID de entidad: 1" in rendered["character_block"]
    assert "Aldric (npc) [PERSONAJE ACTIVO]" in rendered["known_entities"]
    assert "Espada" in rendered["known_items"]
    assert "instance_number=1" in rendered["known_item_instances"]
    assert "Oro" in rendered["known_resources"]
    assert "aliado_de" in rendered["known_relations"]
    assert "Puerta abierta" in rendered["known_events"]
    assert "Identidad oculta" not in rendered["known_events"]
    assert repr(world) == before
