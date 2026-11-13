"""Multi-turn reference resolution tests over visibility-filtered worlds."""

from types import SimpleNamespace

from models.entity import Entity
from models.player_intent_analysis import PlayerIntentAnalysis
from models.semantic_frames import SemanticObjectKind
from models.world_state import WorldState
from services.context.conversation_reference_resolver import (
    ConversationReferenceResolver,
)


def make_analysis(
    utterance: str,
    mention: str,
    *,
    kind_hint: SemanticObjectKind = SemanticObjectKind.UNKNOWN,
) -> PlayerIntentAnalysis:
    version = 2 if kind_hint is not SemanticObjectKind.UNKNOWN else 1
    step = {
        "index": 0,
        "source_excerpt": utterance,
        "actor": "player",
        "action": "interactuar con el referente",
        "modality": "attempted",
        "polarity": "positive",
        "reported_outcome": "not_claimed",
        "target_mentions": [mention],
        "attributed_to": None,
    }
    if version == 2:
        step["action_frame"] = {
            "predicate": utterance.split()[0],
            "family": "other",
            "arguments": [{
                "role": "theme",
                "mention": {"text": mention, "kind_hint": kind_hint.value},
            }],
        }
    payload = {
        "schema_version": version,
        "category": "action",
        "steps": [step],
        "active_step_index": 0,
        "requires_clarification": False,
        "clarification_question": None,
    }
    if version == 2:
        payload["relation_claims"] = []
    return PlayerIntentAnalysis.from_payload(payload, source_text=utterance)


def turn(turn_id: int, text: str, narrative: str = ""):
    return SimpleNamespace(
        id=turn_id,
        player_input=text,
        narrative=narrative,
    )


def test_resolves_pronoun_to_unique_visible_entity_with_auditable_evidence():
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
    reference = result.references[0]
    assert reference.entity_id == 1
    assert reference.entity_name == "Mara"
    assert reference.match_kind == "conversation_antecedent"
    assert reference.antecedent_turn_id == 14
    assert reference.confidence_score >= 35
    assert "player_authored_focus" in reference.resolution_signals
    assert len(reference.evidence) == 1
    assert reference.evidence[0].source.value == "player_input"
    assert reference.evidence[0].speaker.value == "player"
    assert reference.evidence[0].mention == "Mara"


def test_same_turn_competing_referents_abstain_and_return_ranked_candidates():
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
    assert result.abstention_reason == "discourse_candidates_ambiguous"
    assert {candidate.entity_id for candidate in result.candidates} == {1, 2}


def test_player_authored_focus_outweighs_unattributed_narrator_mention():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto por la llave.", "Le"),
        recent_turns=[
            turn(
                16,
                "Hablo con Mara sobre la llave.",
                "Aldric se aleja hacia la plaza.",
            )
        ],
    )
    assert result.clarification_question is None
    assert result.references[0].entity_id == 1
    assert result.references[0].evidence[0].speaker.value == "player"
    assert result.references[0].confidence_score > 0


def test_semantic_kind_hint_filters_incompatible_antecedents():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="La puerta", entity_type="location"),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis(
            "Le pregunto por la llave.",
            "Le",
            kind_hint=SemanticObjectKind.CHARACTER,
        ),
        recent_turns=[turn(17, "Mara y la puerta aparecen en la escena.")],
    )
    assert result.clarification_question is None
    assert result.references[0].entity_id == 1
    assert "semantic_kind_match" in result.references[0].resolution_signals


def test_conflicting_semantic_kind_hints_do_not_pick_one_arbitrarily():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="La puerta", entity_type="location"),
    })
    utterance = "Le pregunto por eso."
    payload = {
        "schema_version": 2,
        "category": "action",
        "steps": [{
            "index": 0,
            "source_excerpt": utterance,
            "actor": "player",
            "action": "preguntar al referente",
            "modality": "attempted",
            "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": ["Le"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "pregunto",
                "family": "communication",
                "arguments": [
                    {
                        "role": "recipient",
                        "mention": {"text": "Le", "kind_hint": "character"},
                    },
                    {
                        "role": "location",
                        "mention": {"text": "Le", "kind_hint": "location"},
                    },
                ],
            },
        }],
        "active_step_index": 0,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }
    analysis = PlayerIntentAnalysis.from_payload(
        payload,
        source_text=utterance,
    )
    result = ConversationReferenceResolver().resolve(
        world,
        analysis,
        recent_turns=[turn(22, "Mara y la puerta aparecen en la escena.")],
    )
    assert result.references == ()
    assert result.clarification_question is not None
    assert result.abstention_reason == "discourse_candidates_ambiguous"
    assert {candidate.entity_id for candidate in result.candidates} == {1, 2}


def test_ambiguous_recent_turn_requests_clarification_instead_of_guessing():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto qué ocurrió.", "Le"),
        recent_turns=[turn(18, "Mara y Aldric llegan juntos a la posada.")],
    )
    assert result.references == ()
    assert result.clarification_question is not None


def test_other_guard_resolves_only_when_one_other_visible_role_matches():
    world = WorldState(entities={
        1: Entity(id=1, name="Bram", entity_type="npc", description="Guardia del puente."),
        2: Entity(id=2, name="Doran", entity_type="npc", description="Guardia de la puerta norte."),
        3: Entity(id=3, name="Mara", entity_type="npc", description="Cartógrafa."),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto al otro guardia.", "otro guardia"),
        recent_turns=[turn(19, "Hablo con Bram, el guardia del puente.")],
    )
    assert result.clarification_question is None
    assert len(result.references) == 1
    assert result.references[0].entity_id == 2
    assert result.references[0].match_kind == "other_role_in_conversation"
    assert result.references[0].antecedent_turn_id == 19


def test_other_guard_abstains_when_contrast_antecedent_is_ambiguous():
    world = WorldState(entities={
        1: Entity(id=1, name="Bram", entity_type="npc", description="Guardia del puente."),
        2: Entity(id=2, name="Eron", entity_type="npc", description="Guardia de la torre."),
        3: Entity(id=3, name="Doran", entity_type="npc", description="Guardia de la puerta norte."),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto al otro guardia.", "otro guardia"),
        recent_turns=[turn(21, "Bram y Eron discuten frente a la puerta.")],
    )
    assert result.references == ()
    assert result.clarification_question is not None
    assert result.abstention_reason == "other_role_antecedent_ambiguous"


def test_hidden_entity_cannot_be_used_as_conversation_antecedent():
    visible_world = WorldState(entities={1: Entity(id=1, name="Mara", entity_type="npc")})
    result = ConversationReferenceResolver().resolve(
        visible_world,
        make_analysis("Le pregunto por la carta.", "Le"),
        recent_turns=[turn(20, "Hablo con el espía secreto.")],
    )
    assert result.references == ()
    assert result.clarification_question is not None
    assert result.abstention_reason == "no_visible_antecedent_evidence"


def test_unresolved_proper_name_is_left_available_for_new_entity_creation():
    result = ConversationReferenceResolver().resolve(
        WorldState(),
        make_analysis("Hablo con Tilda.", "Tilda"),
        recent_turns=(),
    )
    assert result.references == ()
    assert result.clarification_question is None


def test_antecedents_older_than_six_turns_are_not_considered():
    world = WorldState(entities={1: Entity(id=1, name="Mara", entity_type="npc")})
    history = [turn(100, "Hablo con Mara.")]
    history.extend(turn(index, "No menciono a nadie.") for index in range(101, 107))
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto por la carta.", "Le"),
        recent_turns=history,
    )
    assert result.references == ()
    assert result.clarification_question is not None


def test_typed_item_pronoun_is_not_stolen_by_a_same_named_entity_candidate():
    world = WorldState(
        entities={
            1: Entity(id=1, name="La llave", entity_type="npc"),
        }
    )
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis(
            "La guardo en la mochila.",
            "La",
            kind_hint=SemanticObjectKind.ITEM_INSTANCE,
        ),
        recent_turns=[turn(81, "Encuentro la llave bajo la mesa.")],
    )

    assert result.references == ()
    assert result.clarification_question is None
