from __future__ import annotations

import pytest

from models.entity import Entity
from models.event import Event
from models.item import Item, ItemInstance
from models.relation import Relation
from models.resource import Resource, ResourceBalance
from models.world_state import WorldState
from services.context import ContextBuilder, ProposalContextBudgetError


def build_world() -> WorldState:
    return WorldState(
        entities={
            1: Entity(
                id=1,
                name="Fungoso",
                entity_type="character",
                description="El personaje activo.",
            ),
            2: Entity(
                id=2,
                name="Mara",
                entity_type="npc",
                description="Una comerciante de la ciudad.",
            ),
            3: Entity(
                id=3,
                name="Aldric",
                entity_type="npc",
                description="Un minero que no aparece en la intención.",
            ),
        },
        items={
            10: Item(
                id=10,
                name="Espada de hierro",
                description="Una espada sencilla.",
            ),
        },
        item_instances={
            100: ItemInstance(
                id=100,
                item_id=10,
                instance_number=1,
                owner_id=1,
                condition="Bueno",
            ),
        },
        resources={
            20: Resource(
                id=20,
                name="Oro",
                unit="mo",
            ),
        },
        resource_balances={
            200: ResourceBalance(
                id=200,
                resource_id=20,
                owner_id=1,
                amount=75,
            ),
        },
        relations={
            "fungoso-mara": Relation(
                id="fungoso-mara",
                subject_id=1,
                relation_type="ally",
                target_id=2,
                active=True,
            ),
        },
        events={
            "public-market": Event(
                id="public-market",
                event_type="discovery",
                title="Mara llegó al mercado",
                description="La comerciante abrió su puesto.",
                metadata={"entity_ids": [2]},
            ),
            "gm-secret": Event(
                id="gm-secret",
                event_type="secret",
                title="Mara trabaja para el culto",
                description="La información todavía es secreta.",
                secret=True,
                metadata={"entity_ids": [2]},
            ),
        },
    )


def test_proposal_context_selects_relevant_records_and_required_dependencies():
    world = build_world()
    before = repr(world)

    projection = ContextBuilder().build_proposal_context(
        world,
        "Quiero hablar con Mara en el mercado.",
        max_estimated_tokens=2000,
        mandatory_entity_ids=(1,),
    )

    selected = projection.world
    assert set(selected.entities) == {1, 2}
    assert set(selected.relations) == {"fungoso-mara"}
    assert set(selected.events) == {"public-market"}
    assert set(selected.items) == {10}
    assert set(selected.item_instances) == {100}
    assert set(selected.resources) == {20}
    assert set(selected.resource_balances) == {200}
    assert "gm-secret" not in selected.events
    assert selected.entities[1] is not world.entities[1]
    assert repr(world) == before

    diagnostics = projection.diagnostics
    assert diagnostics.estimated_tokens <= diagnostics.budget_tokens
    assert diagnostics.available_records > diagnostics.selected_records
    assert diagnostics.excluded_records > 0
    assert dict(diagnostics.selected_counts)["entities"] == 2


def test_proposal_context_keeps_active_character_when_query_has_no_match():
    world = build_world()

    projection = ContextBuilder().build_proposal_context(
        world,
        "Un nombre que no existe en la campaña",
        max_estimated_tokens=2000,
        mandatory_entity_ids=(1,),
    )

    assert set(projection.world.entities) == {1, 2}
    assert projection.world.item_instances[100].item_id == 10
    assert projection.world.resource_balances[200].amount == 75


def test_proposal_context_skips_optional_records_that_do_not_fit_budget():
    world = WorldState(
        entities={
            1: Entity(id=1, name="Fungoso", entity_type="character"),
            2: Entity(
                id=2,
                name="Aldric",
                entity_type="npc",
                description="Una historia extensa. " * 300,
            ),
        }
    )

    projection = ContextBuilder().build_proposal_context(
        world,
        "Aldric",
        max_estimated_tokens=200,
        mandatory_entity_ids=(1,),
    )

    assert set(projection.world.entities) == {1}
    assert projection.diagnostics.estimated_tokens <= 200
    assert projection.diagnostics.excluded_records >= 1


def test_proposal_context_rejects_budget_too_small_for_mandatory_facts():
    world = WorldState(
        entities={
            1: Entity(
                id=1,
                name="Fungoso",
                entity_type="character",
                description="Dato obligatorio. " * 100,
            )
        }
    )

    with pytest.raises(ProposalContextBudgetError, match="mandatory player context"):
        ContextBuilder().build_proposal_context(
            world,
            "Quiero descansar.",
            max_estimated_tokens=10,
            mandatory_entity_ids=(1,),
        )


def test_proposal_context_is_deterministic_for_same_world_and_query():
    world = build_world()
    builder = ContextBuilder()

    first = builder.build_proposal_context(
        world,
        "Mara",
        max_estimated_tokens=400,
        mandatory_entity_ids=(1,),
    )
    second = builder.build_proposal_context(
        world,
        "Mara",
        max_estimated_tokens=400,
        mandatory_entity_ids=(1,),
    )

    assert list(first.world.entities) == list(second.world.entities)
    assert list(first.world.events) == list(second.world.events)
    assert first.diagnostics == second.diagnostics


def test_estimated_token_budget_uses_a_conservative_utf8_byte_upper_bound():
    from models.world_context_projection import estimate_tokens

    assert estimate_tokens("abc") == 3
    assert estimate_tokens("áé") == len("áé".encode())
    assert estimate_tokens("") == 0


def test_proposal_context_keeps_direct_event_and_relation_search_hits():
    world = WorldState(
        entities={
            40: Entity(id=40, name="Reina", entity_type="npc"),
            41: Entity(id=41, name="Embajador", entity_type="npc"),
        },
        relations={
            "crown-treaty": Relation(
                id="crown-treaty",
                subject_id=40,
                relation_type="Tratado de la Corona",
                target_id=41,
                active=True,
            )
        },
        events={
            "glass-festival": Event(
                id="glass-festival",
                event_type="festival",
                title="Festival del Cristal",
                description="Una celebración en la ciudad.",
                metadata={},
            )
        },
    )

    projection = ContextBuilder().build_proposal_context(
        world,
        "Festival del Cristal y Tratado de la Corona",
        max_estimated_tokens=2000,
    )

    assert "glass-festival" in projection.world.events
    assert "crown-treaty" in projection.world.relations
    assert set(projection.world.entities) == {40, 41}


def test_proposal_context_never_selects_secret_events_from_search_hits():
    world = WorldState(
        events={
            "public": Event(
                id="public",
                event_type="rumor",
                title="Rumor del puerto",
                description="Se habla de barcos.",
            ),
            "secret": Event(
                id="secret",
                event_type="secret",
                title="Rumor del puerto",
                description="La flota está aliada con el culto.",
                secret=True,
            ),
        }
    )

    projection = ContextBuilder().build_proposal_context(
        world,
        "Rumor del puerto",
        max_estimated_tokens=2000,
    )

    assert set(projection.world.events) == {"public"}


def test_proposal_context_orders_selected_records_numerically_and_stably():
    world = WorldState(
        entities={
            10: Entity(id=10, name="Entidad diez", entity_type="npc"),
            2: Entity(id=2, name="Entidad dos", entity_type="npc"),
            1: Entity(id=1, name="Entidad uno", entity_type="npc"),
        }
    )

    projection = ContextBuilder().build_proposal_context(
        world,
        "Entidad",
        max_estimated_tokens=2000,
    )

    assert list(projection.world.entities) == [1, 2, 10]
