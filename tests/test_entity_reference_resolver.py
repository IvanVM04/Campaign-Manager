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


def test_resolver_finds_a_role_reference_inside_a_long_natural_language_action():
    world = WorldState(
        entities={
            1: Entity(
                id=1,
                name="Aldric",
                entity_type="npc",
                description="Tabernero de la posada del Dragón.",
            ),
            2: Entity(
                id=2,
                name="Mara",
                entity_type="npc",
                description="Comerciante del mercado.",
            ),
        }
    )

    result = EntityReferenceResolver().resolve(
        world,
        "Me acerco al tabernero y le pregunto por los rumores del pueblo.",
    )

    assert result.status == "resolved"
    assert result.entity_ids == (1,)
    assert result.candidates[0].match_kind == "description"
    assert result.candidates[0].matched_reference == "tabernero"


def test_resolver_abstains_when_a_long_action_matches_two_role_candidates():
    world = WorldState(
        entities={
            1: Entity(id=1, name="Rurik", description="Guardia del puerto."),
            2: Entity(id=2, name="Tomas", description="Guardia del palacio."),
        }
    )

    result = EntityReferenceResolver().resolve(
        world,
        "Me acerco al guardia y le pregunto qué ha visto esta noche.",
    )

    assert result.status == "ambiguous"
    assert result.entity_ids == ()
    assert {candidate.entity_id for candidate in result.candidates} == {1, 2}


def test_resolver_uses_distinguishing_description_terms_to_break_a_role_tie():
    world = WorldState(
        entities={
            1: Entity(id=1, name="Rurik", description="Guardia del puerto."),
            2: Entity(id=2, name="Tomas", description="Guardia del palacio."),
        }
    )

    result = EntityReferenceResolver().resolve(
        world,
        "Pregunto al guardia del puerto por el barco que llegó.",
    )

    assert result.status == "resolved"
    assert result.entity_ids == (1,)
