"""Multi-turn reference resolution tests over visibility-filtered worlds."""

from types import SimpleNamespace

from models.entity import Entity
from models.player_intent_analysis import PlayerIntentAnalysis
from models.resolved_conversation_reference import ResolvedConversationGroupReference
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
    category: str = "action",
    actor: str = "player",
    modality: str = "attempted",
    polarity: str = "positive",
    active_step_index: int | None = 0,
    predicate: str | None = None,
) -> PlayerIntentAnalysis:
    version = 2 if kind_hint is not SemanticObjectKind.UNKNOWN else 1
    step = {
        "index": 0,
        "source_excerpt": utterance,
        "actor": actor,
        "action": "interactuar con el referente",
        "modality": modality,
        "polarity": polarity,
        "reported_outcome": "not_claimed",
        "target_mentions": [mention],
        "attributed_to": None,
    }
    if version == 2:
        step["action_frame"] = {
            "predicate": predicate or utterance.split()[0],
            "family": "other",
            "arguments": [{
                "role": "theme",
                "mention": {"text": mention, "kind_hint": kind_hint.value},
            }],
        }
    payload = {
        "schema_version": version,
        "category": category,
        "steps": [step],
        "active_step_index": active_step_index,
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
        make_analysis("Le pregunto por la carta.", "Le", kind_hint=SemanticObjectKind.CHARACTER),
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


def test_antecedents_older_than_twelve_turns_are_not_considered():
    world = WorldState(entities={1: Entity(id=1, name="Mara", entity_type="npc")})
    history = [turn(100, "Hablo con Mara.")]
    history.extend(turn(index, "No menciono a nadie.") for index in range(101, 114))
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


def test_entity_and_world_kinds_for_same_mention_abstain_instead_of_double_resolving():
    utterance = "La guardo."
    payload = {
        "schema_version": 2,
        "category": "action",
        "steps": [{
            "index": 0,
            "source_excerpt": utterance,
            "actor": "player",
            "action": "guardar el referente",
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
                        "role": "recipient",
                        "mention": {"text": "La", "kind_hint": "character"},
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
    world = WorldState(
        entities={
            1: Entity(id=1, name="La llave", entity_type="npc"),
        }
    )
    result = ConversationReferenceResolver().resolve(
        world,
        interpretation,
        recent_turns=[turn(82, "Encuentro la llave bajo la mesa.")],
    )

    assert result.references == ()
    assert result.clarification_question is not None
    assert result.abstention_reason == "semantic_kind_conflict"

    
def test_antecedents_between_turns_seven_and_twelve_remain_available():
    world = WorldState(entities={1: Entity(id=1, name="Mara", entity_type="npc")})
    history = [turn(100, "Hablo con Mara.")]
    history.extend(turn(index, "No menciono a nadie.") for index in range(101, 108))
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto por la carta.", "Le"),
        recent_turns=history,
    )
    assert result.clarification_question is None
    assert result.references[0].entity_id == 1
    assert result.references[0].antecedent_turn_id == 100


def test_explicit_topic_shift_prevents_old_topic_antecedent_leakage():
    world = WorldState(entities={1: Entity(id=1, name="Mara", entity_type="npc")})
    history = [
        turn(110, "Hablo con Mara."),
        turn(111, "Cambiando de tema, inspecciono la torre."),
    ]
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Ella me responde.", "Ella"),
        recent_turns=history,
    )
    assert result.references == ()
    assert result.clarification_question is not None


def test_explicit_callback_can_reopen_prior_topic_with_same_ambiguity_checks():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })
    history = [
        turn(112, "Hablo con Mara sobre la llave."),
        turn(113, "Cambiando de tema, busco una salida."),
    ]
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Volviendo a Mara, ella me responde.", "ella"),
        recent_turns=history,
    )
    assert result.references
    assert result.references[0].entity_id == 1


def test_explicit_local_grammatical_agreement_filters_incompatible_candidate():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Ella me responde.", "Ella", kind_hint=SemanticObjectKind.CHARACTER),
        recent_turns=[
            turn(114, "La guardia Mara espera. El capitán Aldric observa.")
        ],
    )
    assert result.clarification_question is None
    assert result.references[0].entity_id == 1


def test_unknown_name_gender_is_not_used_as_grammatical_evidence():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Ella me responde.", "Ella", kind_hint=SemanticObjectKind.CHARACTER),
        recent_turns=[turn(115, "Mara y Aldric esperan junto a la puerta.")],
    )
    assert result.references == ()
    assert result.clarification_question is not None


def test_plural_pronoun_does_not_collapse_to_one_individual():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Ellos se acercan.", "Ellos", kind_hint=SemanticObjectKind.CHARACTER),
        recent_turns=[turn(116, "Mara y Aldric esperan junto a la puerta.")],
    )
    assert result.references == ()
    assert result.clarification_question is not None


def test_explicit_npc_quote_is_attributed_only_to_its_visible_speaker():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto qué ocurrió.", "Le"),
        recent_turns=[
            turn(117, "No hago referencia al nombre en mi entrada.",
                 "Mara dice: «Aldric está en la torre».")
        ],
    )
    assert result.clarification_question is None
    assert result.references[0].entity_id == 1
    assert any(
        evidence.speaker.value == "npc" and evidence.speaker_entity_id == 1
        for evidence in result.references[0].evidence
    )


def test_ambiguous_npc_alias_does_not_create_speaker_identity():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Mara", entity_type="npc"),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto qué ocurrió.", "Le"),
        recent_turns=[
            turn(118, "¿Qué opinas?",
                 "Mara dice: «No lo sé».")
        ],
    )
    assert result.references == ()
    assert result.clarification_question is not None



def test_antecedent_at_the_twelfth_visible_turn_can_still_resolve():
    world = WorldState(entities={1: Entity(id=1, name="Mara", entity_type="npc")})
    history = [turn(200, "Hablo con Mara.")]
    history.extend(turn(index, "No menciono a nadie.") for index in range(201, 212))
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Le pregunto por la carta.", "Le"),
        recent_turns=history,
    )
    assert result.clarification_question is None
    assert result.references[0].entity_id == 1
    assert result.references[0].antecedent_turn_id == 200



def _non_write_analysis(
    utterance: str,
    mention: str,
    *,
    category: str,
    actor: str,
    modality: str,
    predicate: str,
    family: str,
) -> PlayerIntentAnalysis:
    """Build a validated v2 utterance that must not authorize a world proposal."""
    payload = {
        "schema_version": 2,
        "category": category,
        "steps": [{
            "index": 0,
            "source_excerpt": utterance,
            "actor": actor,
            "action": "referirse a un personaje",
            "modality": modality,
            "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": [mention],
            "attributed_to": None,
            "action_frame": {
                "predicate": predicate,
                "family": family,
                "arguments": [{
                    "role": "agent",
                    "mention": {
                        "text": mention,
                        "kind_hint": "character",
                    },
                }],
            },
        }],
        "active_step_index": None,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }
    return PlayerIntentAnalysis.from_payload(payload, source_text=utterance)


def test_npc_report_reference_resolves_without_world_proposal_authorization():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })
    utterance = "Ella entra en la sala."
    analysis = _non_write_analysis(
        utterance,
        "Ella",
        category="report",
        actor="npc",
        modality="reported",
        predicate="entra",
        family="movement",
    )
    assert not analysis.allows_world_proposal

    result = ConversationReferenceResolver().resolve(
        world,
        analysis,
        recent_turns=[
            turn(130, "La guardia Mara espera junto a la puerta. "
                      "El capitán Aldric observa el pasillo.")
        ],
        current_input=utterance,
    )

    assert result.clarification_question is None
    assert len(result.references) == 1
    assert result.references[0].entity_id == 1


def test_npc_dialogue_reference_resolves_without_world_proposal_authorization():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })
    utterance = "Ella responde a mi pregunta."
    analysis = _non_write_analysis(
        utterance,
        "Ella",
        category="dialogue",
        actor="npc",
        modality="dialogue",
        predicate="responde",
        family="communication",
    )
    assert not analysis.allows_world_proposal

    result = ConversationReferenceResolver().resolve(
        world,
        analysis,
        recent_turns=[
            turn(131, "La guardia Mara espera junto a la puerta. "
                      "El capitán Aldric observa el pasillo.")
        ],
        current_input=utterance,
    )

    assert result.clarification_question is None
    assert len(result.references) == 1
    assert result.references[0].entity_id == 1


def test_dm_question_can_resolve_a_referent_without_world_proposal_authorization():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })
    utterance = "¿Qué le ocurrió a ella?"
    analysis = _non_write_analysis(
        utterance,
        "ella",
        category="question",
        actor="player",
        modality="question",
        predicate="ocurrió",
        family="other",
    )
    assert not analysis.allows_world_proposal

    result = ConversationReferenceResolver().resolve(
        world,
        analysis,
        recent_turns=[
            turn(132, "La guardia Mara espera junto a la puerta. "
                      "El capitán Aldric observa el pasillo.")
        ],
        current_input=utterance,
    )

    assert result.clarification_question is None
    assert len(result.references) == 1
    assert result.references[0].entity_id == 1



def test_literal_npc_attribution_is_resolved_even_without_target_mentions():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
    })
    utterance = "Mara susurra que ha visto a Aldric."
    analysis = PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 2,
            "category": "dialogue",
            "steps": [{
                "index": 0,
                "source_excerpt": utterance,
                "actor": "npc",
                "action": "Mara susurra que ha visto a Aldric",
                "modality": "dialogue",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": [],
                "attributed_to": "Mara",
                "action_frame": {
                    "predicate": "susurra",
                    "family": "communication",
                    "arguments": [],
                },
            }],
            "active_step_index": None,
            "requires_clarification": False,
            "clarification_question": None,
            "relation_claims": [],
        },
        source_text=utterance,
    )
    assert not analysis.allows_world_proposal

    result = ConversationReferenceResolver().resolve(
        world,
        analysis,
        recent_turns=(),
        current_input=utterance,
    )

    assert result.clarification_question is None
    assert len(result.references) == 1
    assert result.references[0].entity_id == 1
    assert result.references[0].mention == "Mara"


def test_negated_npc_report_still_resolves_pronouns_read_only():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
    })
    interpretation = make_analysis(
        "Ella no entra en la sala.",
        "Ella",
        kind_hint=SemanticObjectKind.CHARACTER,
        category="report",
        actor="npc",
        modality="negated",
        polarity="negative",
        active_step_index=None,
        predicate="entra",
    )

    assert interpretation.allows_world_proposal is False
    result = ConversationReferenceResolver().resolve(
        world,
        interpretation,
        recent_turns=[turn(40, "La guardia Mara espera junto a la puerta.")],
        current_input="Ella no entra en la sala.",
    )

    assert result.clarification_question is None
    assert len(result.references) == 1
    assert result.references[0].entity_id == 1


def test_negative_relation_endpoints_remain_resolvable_without_write_authority():
    utterance = "Mara no protege a Aldric."
    payload = {
        "schema_version": 2,
        "category": "report",
        "steps": [{
            "index": 0,
            "source_excerpt": utterance,
            "actor": "npc",
            "action": "informar de una protección negada",
            "modality": "reported",
            "polarity": "negative",
            "reported_outcome": "not_claimed",
            "target_mentions": [],
            "attributed_to": None,
            "action_frame": {
                "predicate": "protege",
                "family": "social",
                "arguments": [],
            },
        }],
        "active_step_index": None,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [{
            "step_index": 0,
            "subject": {"text": "Mara", "kind_hint": "character"},
            "predicate": "protege",
            "object": {"text": "Aldric", "kind_hint": "character"},
            "relation_family": "protection",
            "polarity": "negative",
            "modality": "negated",
            "source_excerpt": utterance,
            "attributed_to": None,
            "temporal_expression": None,
        }],
    }
    interpretation = PlayerIntentAnalysis.from_payload(
        payload,
        source_text=utterance,
    )
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Aldric", entity_type="npc"),
    })

    assert interpretation.allows_world_proposal is False
    result = ConversationReferenceResolver().resolve(
        world,
        interpretation,
        current_input=utterance,
    )

    assert result.clarification_question is None
    assert {reference.entity_id for reference in result.references} == {1, 2}



def test_surface_pronoun_is_resolved_when_the_model_omits_it_from_its_frame():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
    })
    utterance = "Ella responde en voz alta."
    # The model only emits an unrelated literal mention; the independent
    # surface scanner still offers "Ella" to the deterministic resolver.
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis(utterance, "voz alta"),
        recent_turns=[
            turn(200, "La guardia Mara espera junto a la puerta."),
        ],
        current_input=utterance,
    )
    assert result.clarification_question is None
    assert len(result.references) == 1
    assert result.references[0].mention == "Ella"
    assert result.references[0].entity_id == 1
    assert result.references[0].antecedent_turn_id == 200


def test_plural_pronoun_resolves_only_to_a_co_mentioned_grammatical_group():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Lía", entity_type="npc"),
    })
    utterance = "Ellas contestan en voz alta desde el balcón."
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis(
            utterance,
            "balcón",
            category="report",
            actor="npc",
            modality="reported",
            active_step_index=None,
        ),
        recent_turns=[
            turn(201, "La guardia Mara y la mercadera Lía esperan junto al balcón."),
        ],
        current_input=utterance,
    )
    assert result.clarification_question is None
    assert len(result.references) == 1
    group = result.references[0]
    assert isinstance(group, ResolvedConversationGroupReference)
    assert group.mention == "Ellas"
    assert group.entity_ids == (1, 2)
    assert group.entity_names == ("Mara", "Lía")
    assert group.antecedent_turn_id == 201


def test_plural_pronoun_does_not_form_a_group_from_separate_unconnected_turns():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
        2: Entity(id=2, name="Lía", entity_type="npc"),
    })
    utterance = "Ellas contestan."
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis(
            utterance,
            "contestan",
            category="report",
            actor="npc",
            modality="reported",
            active_step_index=None,
        ),
        recent_turns=[
            turn(202, "La guardia Mara espera junto a la puerta."),
            turn(203, "La mercadera Lía llega desde el mercado."),
        ],
        current_input=utterance,
    )
    assert result.references == ()
    assert result.clarification_question is not None
    assert result.abstention_reason == "plural_group_not_proven"



def test_singular_pronoun_keeps_unique_antecedent_when_history_has_no_gender_cue():
    world = WorldState(entities={
        1: Entity(id=1, name="Mara", entity_type="npc"),
    })
    result = ConversationReferenceResolver().resolve(
        world,
        make_analysis("Ella me responde.", "Ella"),
        recent_turns=[turn(204, "Hablo con Mara junto a la puerta.")],
    )
    assert result.clarification_question is None
    assert len(result.references) == 1
    assert result.references[0].entity_id == 1
