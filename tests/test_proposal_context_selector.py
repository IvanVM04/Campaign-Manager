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
        max_estimated_tokens=80,
        mandatory_entity_ids=(1,),
    )

    assert set(projection.world.entities) == {1}
    assert projection.diagnostics.estimated_tokens <= 80
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
