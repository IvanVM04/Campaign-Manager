"""Typed resolution of item, resource and event references."""

from types import SimpleNamespace

import pytest

from models.event import Event
from models.item import Item, ItemInstance
from models.player_intent_analysis import PlayerIntentAnalysis
from models.resolved_world_reference import WorldReferenceCategory
from models.resource import Resource
from models.semantic_frames import SemanticObjectKind
from models.world_state import WorldState
from services.context.world_reference_resolver import WorldReferenceResolver


def analysis(
    utterance: str,
    mention: str,
    kind: SemanticObjectKind,
) -> PlayerIntentAnalysis:
    return PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 2,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": utterance,
                "actor": "player",
                "action": "interactuar con el referente",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": [mention],
                "attributed_to": None,
                "action_frame": {
                    "predicate": utterance.split()[0],
                    "family": "interaction",
                    "arguments": [{
                        "role": "theme",
                        "mention": {"text": mention, "kind_hint": kind.value},
                    }],
                },
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
            "relation_claims": [],
        },
        source_text=utterance,
    )


def turn(turn_id: int, player_input: str, narrative: str = ""):
    return SimpleNamespace(
        id=turn_id,
        player_input=player_input,
        narrative=narrative,
    )


def sword_world(instance_ids=(901,)):
    return WorldState(
        items={
            50: Item(
                id=50,
                name="Espada de plata",
                description="Una espada ligera.",
            )
        },
        item_instances={
            instance_id: ItemInstance(
                id=instance_id,
                item_id=50,
                instance_number=index,
                condition="intacta",
            )
            for index, instance_id in enumerate(instance_ids, start=1)
        },
    )


def test_resolves_physical_item_instance_without_confusing_definition_id():
    world = sword_world()
    result = WorldReferenceResolver().resolve(
        world,
        analysis(
            "Recojo la espada de plata.",
            "la espada de plata",
            SemanticObjectKind.ITEM_INSTANCE,
        ),
    )

    assert result.clarification_question is None
    assert len(result.references) == 1
    reference = result.references[0]
    assert reference.category is WorldReferenceCategory.ITEM_INSTANCE
    assert reference.referent_id == 901
    assert reference.referent_id != 50
    assert reference.name == "Espada de plata (instancia #1)"


def test_item_definition_and_physical_instance_use_separate_namespaces():
    world = sword_world()

    definition = WorldReferenceResolver().resolve(
        world,
        analysis(
            "Consulto la espada de plata.",
            "la espada de plata",
            SemanticObjectKind.ITEM_DEFINITION,
        ),
    )
    instance = WorldReferenceResolver().resolve(
        world,
        analysis(
            "Recojo la espada de plata.",
            "la espada de plata",
            SemanticObjectKind.ITEM_INSTANCE,
        ),
    )

    assert definition.references[0].category is WorldReferenceCategory.ITEM_DEFINITION
    assert definition.references[0].referent_id == 50
    assert instance.references[0].category is WorldReferenceCategory.ITEM_INSTANCE
    assert instance.references[0].referent_id == 901


def test_two_physical_copies_with_same_name_require_clarification():
    world = sword_world(instance_ids=(901, 902))
    result = WorldReferenceResolver().resolve(
        world,
        analysis(
            "Recojo la espada de plata.",
            "la espada de plata",
            SemanticObjectKind.ITEM_INSTANCE,
        ),
    )

    assert result.references == ()
    assert result.clarification_question is not None
    assert result.abstention_reason == "explicit_world_reference_ambiguous"
    assert len(result.candidates) == 2


def test_anaphoric_item_reference_resolves_from_recent_player_authored_evidence():
    world = sword_world()
    result = WorldReferenceResolver().resolve(
        world,
        analysis("La guardo en la mochila.", "La", SemanticObjectKind.ITEM_INSTANCE),
        recent_turns=[turn(12, "Encuentro la Espada de plata junto al pozo.")],
    )

    assert result.clarification_question is None
    assert result.references[0].referent_id == 901
    assert result.references[0].match_kind == "typed_conversation_antecedent"
    assert result.references[0].antecedent_turn_id == 12
    assert result.references[0].evidence[0].source.value == "player_input"
    assert "player_authored_focus" in result.references[0].resolution_signals


def test_anaphoric_item_reference_keeps_multiple_instances_ambiguous():
    world = sword_world(instance_ids=(901, 902))
    result = WorldReferenceResolver().resolve(
        world,
        analysis("La guardo.", "La", SemanticObjectKind.ITEM_INSTANCE),
        recent_turns=[turn(13, "Encuentro la Espada de plata.")],
    )

    assert result.references == ()
    assert result.clarification_question is not None
    assert result.abstention_reason == "typed_discourse_candidates_ambiguous"


def test_inactive_physical_instances_are_never_resolved():
    world = sword_world()
    world.item_instances[901].active = False
    result = WorldReferenceResolver().resolve(
        world,
        analysis("Recojo la espada de plata.", "la espada de plata", SemanticObjectKind.ITEM_INSTANCE),
    )
    assert result.references == ()
    assert result.clarification_question is None


def test_resource_reference_does_not_resolve_to_a_same_named_item():
    world = WorldState(
        items={1: Item(id=1, name="Oro")},
        resources={2: Resource(id=2, name="Oro", resource_type="currency")},
    )
    result = WorldReferenceResolver().resolve(
        world,
        analysis("Consulto el oro.", "el oro", SemanticObjectKind.RESOURCE),
    )

    assert len(result.references) == 1
    assert result.references[0].category is WorldReferenceCategory.RESOURCE
    assert result.references[0].referent_id == 2


def test_visible_event_reference_is_resolved_but_gm_only_event_is_not():
    world = WorldState(
        events={
            "public-event": Event(
                id="public-event",
                event_type="discovery",
                title="Ataque del dragón",
                description="El dragón atacó la torre.",
            ),
            "secret-event": Event(
                id="secret-event",
                event_type="secret",
                title="Traición del consejero",
                secret=True,
            ),
        }
    )
    visible = WorldReferenceResolver().resolve(
        world,
        analysis(
            "Recuerdo el Ataque del dragón.",
            "Ataque del dragón",
            SemanticObjectKind.EVENT,
        ),
    )
    hidden = WorldReferenceResolver().resolve(
        world,
        analysis(
            "Recuerdo la Traición del consejero.",
            "Traición del consejero",
            SemanticObjectKind.EVENT,
        ),
    )

    assert visible.references[0].referent_id == "public-event"
    assert visible.references[0].category is WorldReferenceCategory.EVENT
    assert hidden.references == ()


def test_character_scoped_events_require_active_character_visibility():
    world = WorldState(
        events={
            "character-event": Event(
                id="character-event",
                event_type="clue",
                title="Mensaje secreto para Mara",
                visibility_scope="character",
                known_by_entity_ids=[5],
            )
        }
    )
    query = analysis(
        "Recuerdo el Mensaje secreto para Mara.",
        "Mensaje secreto para Mara",
        SemanticObjectKind.EVENT,
    )

    hidden = WorldReferenceResolver().resolve(
        world,
        query,
        character_entity_id=6,
    )
    visible = WorldReferenceResolver().resolve(
        world,
        query,
        character_entity_id=5,
    )

    assert hidden.references == ()
    assert visible.references[0].referent_id == "character-event"


def test_narrator_only_object_evidence_is_recorded_as_narrator_not_player():
    world = sword_world()
    result = WorldReferenceResolver().resolve(
        world,
        analysis("La examino.", "La", SemanticObjectKind.ITEM_INSTANCE),
        recent_turns=[turn(18, "Espero en silencio.", "La Espada de plata descansa sobre la mesa.")],
    )

    assert result.references[0].referent_id == 901
    assert result.references[0].evidence[0].source.value == "narrative"
    assert "narrator_context" in result.references[0].resolution_signals


def test_unknown_and_entity_kinds_are_left_to_the_entity_resolver():
    world = sword_world()
    unknown = WorldReferenceResolver().resolve(
        world,
        analysis("Recojo la espada.", "la espada", SemanticObjectKind.UNKNOWN),
    )
    character = WorldReferenceResolver().resolve(
        world,
        analysis("Hablo con Mara.", "Mara", SemanticObjectKind.CHARACTER),
    )
    assert unknown.references == ()
    assert character.references == ()


def test_invalid_character_identity_is_rejected():
    with pytest.raises(ValueError, match="character_entity_id"):
        WorldReferenceResolver().resolve(
            sword_world(),
            analysis("Recojo la espada.", "la espada", SemanticObjectKind.ITEM_INSTANCE),
            character_entity_id=True,
        )


def test_non_actionable_interpretation_does_not_resolve_world_references():
    payload = {
        "schema_version": 2,
        "category": "question",
        "steps": [{
            "index": 0,
            "source_excerpt": "¿Dónde está la espada?",
            "actor": "player",
            "action": "preguntar por la espada",
            "modality": "question",
            "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": ["la espada"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "está",
                "family": "other",
                "arguments": [{
                    "role": "theme",
                    "mention": {"text": "la espada", "kind_hint": "item_instance"},
                }],
            },
        }],
        "active_step_index": None,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }
    query = PlayerIntentAnalysis.from_payload(
        payload,
        source_text="¿Dónde está la espada?",
    )
    assert WorldReferenceResolver().resolve(sword_world(), query).references == ()


def test_conflicting_world_reference_kinds_require_clarification():
    utterance = "La guardo."
    payload = {
        "schema_version": 2,
        "category": "action",
        "steps": [{
            "index": 0,
            "source_excerpt": utterance,
            "actor": "player",
            "action": "guardar el objeto",
            "modality": "attempted",
            "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": ["La"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "guardo",
                "family": "interaction",
                "arguments": [
                    {
                        "role": "theme",
                        "mention": {"text": "La", "kind_hint": "item_instance"},
                    },
                    {
                        "role": "instrument",
                        "mention": {"text": "La", "kind_hint": "resource"},
                    },
                ],
            },
        }],
        "active_step_index": 0,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }
    interpretation = PlayerIntentAnalysis.from_payload(
        payload,
        source_text=utterance,
    )
    result = WorldReferenceResolver().resolve(
        sword_world(),
        interpretation,
    )

    assert result.references == ()
    assert result.clarification_question is not None
    assert result.abstention_reason == "semantic_kind_conflict"



def test_typed_reference_uses_explicit_local_grammatical_agreement():
    world = WorldState(
        items={
            1: Item(id=1, name="Amuleto"),
            2: Item(id=2, name="Llave"),
        },
        item_instances={
            901: ItemInstance(id=901, item_id=1, instance_number=1, condition="intacto"),
            902: ItemInstance(id=902, item_id=2, instance_number=1, condition="intacta"),
        },
    )
    result = WorldReferenceResolver().resolve(
        world,
        analysis("La guardo en la mochila.", "La", SemanticObjectKind.ITEM_INSTANCE),
        recent_turns=[
            turn(19, "Encuentro el amuleto y la llave junto a la puerta.")
        ],
    )
    assert result.clarification_question is None
    assert len(result.references) == 1
    assert result.references[0].referent_id == 902


def test_typed_plural_pronoun_does_not_resolve_to_one_item_instance():
    world = sword_world()
    result = WorldReferenceResolver().resolve(
        world,
        analysis("Las guardo.", "Las", SemanticObjectKind.ITEM_INSTANCE),
        recent_turns=[turn(20, "Encuentro la Espada de plata.")],
    )
    assert result.references == ()
    assert result.clarification_question is not None



def test_typed_reference_explicit_callback_reopens_prior_topic():
    world = sword_world()
    history = [
        turn(21, "Encuentro la Espada de plata junto al pozo."),
        turn(22, "Cambiando de tema, busco una salida."),
    ]
    result = WorldReferenceResolver().resolve(
        world,
        analysis("La guardo.", "La", SemanticObjectKind.ITEM_INSTANCE),
        recent_turns=history,
        current_input="Volviendo a la espada, la guardo.",
    )
    assert result.clarification_question is None
    assert result.references[0].referent_id == 901


def test_typed_reference_does_not_reuse_antecedent_after_topic_shift():
    world = sword_world()
    history = [
        turn(23, "Encuentro la Espada de plata junto al pozo."),
        turn(24, "Cambiando de tema, busco una salida."),
    ]
    result = WorldReferenceResolver().resolve(
        world,
        analysis("La guardo.", "La", SemanticObjectKind.ITEM_INSTANCE),
        recent_turns=history,
        current_input="Cambiando de tema, la guardo.",
    )
    assert result.references == ()
    assert result.clarification_question is not None
