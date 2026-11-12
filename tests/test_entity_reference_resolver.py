"""Contract tests for deterministic, conservative entity reference matching."""

from models.entity import Entity
from models.world_state import WorldState
from services.context.entity_reference_resolver import EntityReferenceResolver


def test_resolver_prefers_explicit_alias_over_description_match():
    world = WorldState(
        entities={
            1: Entity(id=1, name="Aldric", description="Un guardia del puerto.", aliases=["el tabernero"]),
            2: Entity(id=2, name="Mara", description="Una posadera."),
        }
    )
    result = EntityReferenceResolver().resolve(world, "Hablo con el tabernero.")
    assert result.status == "resolved"
    assert result.entity_ids == (1,)
    assert result.candidates[0].match_kind == "alias"


def test_resolver_returns_each_distinct_explicitly_named_entity():
    world = WorldState(
        entities={
            1: Entity(id=1, name="Aldric"),
            2: Entity(id=2, name="Mara"),
        }
    )
    result = EntityReferenceResolver().resolve(world, "Aldric habla con Mara")
    assert result.status == "resolved"
    assert result.entity_ids == (1, 2)


def test_resolver_abstains_on_shared_aliases_and_role_collisions():
    world = WorldState(
        entities={
            1: Entity(id=1, name="Aldric", aliases=["el guardia"]),
            2: Entity(id=2, name="Mara", aliases=["el guardia"]),
        }
    )
    result = EntityReferenceResolver().resolve(world, "Quiero hablar con el guardia")
    assert result.status == "ambiguous"
    assert result.entity_ids == ()
    assert result.candidate_count == 2


def test_resolver_normalizes_diacritics_case_and_punctuation():
    world = WorldState(entities={3: Entity(id=3, name="Doña Cárdena")})
    result = EntityReferenceResolver().resolve(world, "DONA, CARDENA!")
    assert result.status == "resolved"
    assert result.entity_ids == (3,)


def test_resolver_ignores_inactive_entities():
    world = WorldState(
        entities={
            1: Entity(
                id=1,
                name="Aldric",
                description="Un tabernero veterano de la ciudad.",
                active=False,
            )
        }
    )
    assert EntityReferenceResolver().resolve(world, "el tabernero").status == "unresolved"
