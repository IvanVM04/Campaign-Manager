"""Multi-turn reference resolution tests over visibility-filtered worlds."""

from types import SimpleNamespace

from models.entity import Entity
from models.player_intent_analysis import PlayerIntentAnalysis
from models.world_state import WorldState
from services.context.conversation_reference_resolver import ConversationReferenceResolver


def make_analysis(utterance: str, mention: str) -> PlayerIntentAnalysis:
    return PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 1,
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
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
        source_text=utterance,
    )


def turn(turn_id: int, text: str):
    return SimpleNamespace(id=turn_id, player_input=text, narrative="")


def test_resolves_pronoun_to_unique_visible_entity_in_previous_turn():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc", description="Cartógrafa."),
        2: Entity(id=2, name="Aldric", entity_type="npc", description="Tabernero."),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto por la llave.", "Le"),
        recent_turns=[turn(14, "Hablo con Mara sobre el mapa.")],
    )
    assert result.clarification_question is None
    assert len(result.references) == 1
    assert result.references[0].entity_id == 1
    assert result.references[0].entity_name == "Mara"
    assert result.references[0].match_kind == "conversation_antecedent"
    assert result.references[0].antecedent_turn_id == 14


def test_ambiguous_recent_turn_requests_clarification_instead_of_guessing():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto qué ocurrió.", "Le"),
        recent_turns=[turn(15, "Mara y Aldric llegan juntos a la posada.")],
    )
    assert result.references == ()
    assert result.clarification_question is not None
    assert "Mara" in result.clarification_question
    assert "Aldric" in result.clarification_question


def test_other_guard_resolves_only_when_one_other_visible_role_matches():
    world = WorldState(entities={
        1: Entity(id=1, name="Bram", entity_type="npc", description="Guardia del puente."),
        2: Entity(id=2, name="Doran", entity_type="npc", description="Guardia de la puerta norte."),
        3: Entity(id=3, name="Mara", entity_type="npc", description="Cartógrafa."),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto al otro guardia.", "el otro guardia"),
        recent_turns=[turn(16, "Hablo con Bram, el guardia del puente.")],
    )
    assert result.clarification_question is None
    assert len(result.references) == 1
    assert result.references[0].entity_id == 2
    assert result.references[0].match_kind == "other_role_in_conversation"


def test_hidden_entity_cannot_be_used_as_conversation_antecedent():
    visible_world = WorldState(entities={1: Entity(id=1, name="Mara", entity_type="npc")})
    result = ConversationReferenceResolver().resolve(
        visible_world,
        make_analysis("Le pregunto por la carta.", "Le"),
        recent_turns=[turn(17, "Hablo con el espía secreto.")],
    )
    assert result.references == ()
    assert result.clarification_question is not None


def test_unresolved_proper_name_is_left_available_for_new_entity_creation():
    result = ConversationReferenceResolver().resolve(
        WorldState(),
        make_analysis("Hablo con Tilda.", "Tilda"),
        recent_turns=(),
    )
    assert result.references == ()
    assert result.clarification_question is None
