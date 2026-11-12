"""Deterministic synthetic campaign builders for scale-oriented context tests."""

from __future__ import annotations

from models.entity import Entity
from models.event import Event
from models.item import Item, ItemInstance
from models.relation import Relation
from models.resource import Resource, ResourceBalance
from models.world_context_projection import WorldContextProjection
from models.world_state import WorldState


def build_large_campaign_world(
    *,
    entity_count: int = 800,
    reverse_insertion: bool = False,
) -> WorldState:
    """Build a representative graph with many searchable and dependent records."""
    if isinstance(entity_count, bool) or not isinstance(entity_count, int) or entity_count < 10:
        raise ValueError("entity_count must be an integer >= 10")

    world = WorldState()
    records = [
        Entity(
            id=1,
            name="Fungoso",
            entity_type="character",
            description="Personaje protagonista de la campaña.",
        ),
        Entity(
            id=2,
            name="Puerto Gris",
            entity_type="location",
            description="Ubicación actual del grupo.",
        ),
    ]
    records.extend(
        Entity(
            id=entity_id,
            name=f"Guardia del puerto {entity_id:04d}",
            entity_type="npc",
            description=(
                "Guardia del puerto asignado a una zona diferente. "
                f"Registro sintético número {entity_id}."
            ),
        )
        for entity_id in range(3, entity_count + 3)
    )
    if reverse_insertion:
        records.reverse()
    world.entities = {record.id: record for record in records if record.id is not None}

    world.items = {
        10: Item(
            id=10,
            name="Insignia de la guardia",
            description="Insignia oficial de Fungoso y de la guardia del puerto.",
        )
    }
    world.item_instances = {
        100: ItemInstance(
            id=100,
            item_id=10,
            instance_number=1,
            owner_id=1,
            condition="Bueno",
            notes="Pertenece a Fungoso.",
        )
    }
    world.resources = {
        20: Resource(id=20, name="Crédito portuario", unit="fichas", notes="Recurso de Fungoso.")
    }
    world.resource_balances = {
        200: ResourceBalance(
            id=200,
            resource_id=20,
            owner_id=1,
            amount=75,
            notes="Saldo de Fungoso.",
        )
    }
    world.relations = {
        "player-location": Relation(
            id="player-location",
            subject_id=1,
            relation_type="Fungoso se encuentra en",
            target_id=2,
            active=True,
        ),
        "player-guard": Relation(
            id="player-guard",
            subject_id=1,
            relation_type="Fungoso aliado de",
            target_id=3,
            active=True,
        ),
        "guard-location": Relation(
            id="guard-location",
            subject_id=3,
            relation_type="vigila",
            target_id=2,
            active=True,
        ),
    }
    world.events = {
        "public-guard-shift": Event(
            id="public-guard-shift",
            event_type="public_notice",
            title="Fungoso recibe aviso: cambio de turno de la guardia",
            description="La guardia ha cambiado de turno.",
            metadata={"entity_ids": [2, 3]},
        ),
        "secret-smuggling-route": Event(
            id="secret-smuggling-route",
            event_type="secret",
            title="Fungoso conoce la ruta secreta de contrabando",
            description="La capitana trabaja para los contrabandistas.",
            consequences="Los guardias protegen la ruta oculta.",
            secret=True,
            metadata={"entity_ids": [2, 3]},
        ),
    }
    return world


def projection_fingerprint(
    projection: WorldContextProjection,
) -> tuple[object, ...]:
    """Return stable, public projection identity and diagnostic values."""
    world = projection.world
    diagnostics = projection.diagnostics
    return (
        tuple(world.entities),
        tuple(world.items),
        tuple(world.item_instances),
        tuple(world.resources),
        tuple(world.resource_balances),
        tuple(world.relations),
        tuple(world.events),
        diagnostics.estimated_tokens,
        diagnostics.budget_tokens,
        diagnostics.available_counts,
        diagnostics.candidate_counts,
        diagnostics.selected_counts,
    )
