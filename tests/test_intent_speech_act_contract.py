"""Contract tests for global speech-act and actor classification in Intent v2."""

from services.turns.intent_interpreter import IntentInterpreter
from services.turns.intent_response_schema import (
    INTENT_ANALYSIS_RESPONSE_SCHEMA,
    INTENT_CORRECTION_RESPONSE_SCHEMA,
)


def _intent_properties(schema):
    return schema["properties"]["intent_analysis"]["properties"]


def test_normal_intent_prompt_separates_dialogue_question_and_report():
    normal = " ".join(IntentInterpreter.SYSTEM_PROMPT.casefold().split())

    assert "pregunta indirecta" in normal
    assert "dirigida a un personaje" in normal
    assert "pregunta al dm/narrador" in normal
    assert "implícitamente" in normal or "implícita" in normal
    assert "report" in normal
    assert "actor" in normal and "npc" in normal
    assert 'actor="npc"' in normal or "el actor del paso es" in normal
    assert "una acción de npc no es un intento del jugador" in normal or (
        "el actor del paso es" in normal
    )
    assert "la guardia cruza el puente" in normal
    assert "le consulto a la guardia" in normal


def test_normal_intent_schema_describes_global_category_and_communication_family():
    properties = _intent_properties(INTENT_ANALYSIS_RESPONSE_SCHEMA)
    category_description = properties["category"]["description"].casefold()
    frame_properties = properties["steps"]["items"]["properties"][
        "action_frame"
    ]["properties"]
    family_description = frame_properties["family"]["description"].casefold()

    assert "speech act" in category_description
    assert "indirect question" in category_description
    assert "dm/narrator" in category_description
    assert "implicit request" in category_description
    assert "non-speech npc action" in category_description
    assert "communication" in family_description
    assert "interaction" in family_description
    assert "non-linguistic" in family_description


def test_pending_correction_contract_is_edit_only_and_does_not_reinterpret():
    prompt = " ".join(
        IntentInterpreter.CORRECTION_SYSTEM_PROMPT.casefold().split()
    )
    schema = INTENT_CORRECTION_RESPONSE_SCHEMA

    assert "no devuelvas intent_analysis" in prompt
    assert "última respuesta del jugador" in prompt
    assert "pendingintentcorrection.apply()" in prompt
    assert schema["required"] == [
        "status", "pending_corrections", "clarification_question"
    ]
    assert set(schema["properties"]) == {
        "status", "pending_corrections", "clarification_question"
    }
    assert schema["properties"]["status"]["enum"] == [
        "corrected", "needs_clarification", "no_change"
    ]
    assert schema["properties"]["pending_corrections"]["maxItems"] == 4
    correction_item = schema["properties"]["pending_corrections"]["items"]
    assert correction_item["required"] == [
        "slot_id",
        "previous_value",
        "replacement",
        "source_excerpt",
    ]
    assert set(correction_item["properties"]) == set(correction_item["required"])
    assert correction_item["properties"]["slot_id"]["type"] == "integer"
    assert correction_item["properties"]["slot_id"]["minimum"] == 0
    assert correction_item["properties"]["slot_id"]["maximum"] == 159
    assert "relation endpoint" in (
        correction_item["properties"]["slot_id"]["description"]
    )
    assert "correction_slots" in prompt
    assert "current_value" in prompt
    assert "slot_id" in prompt
    assert "no devuelvas step_index" in prompt
    assert "correction_slots.target_mentions" in prompt
    assert "correction_slots.action_arguments" in prompt
    assert 'status="needs_clarification"' in prompt



def test_normal_intent_prompt_covers_callbacks_ellipsis_actor_and_evidence_boundaries():
    prompt = " ".join(IntentInterpreter.SYSTEM_PROMPT.casefold().split())

    assert "continuidad, actor y clasificación del habla" in prompt
    assert "segmento histórico seleccionado" in prompt
    assert "antecedente de jugador más reciente" in prompt
    assert "actor identifica quién realiza el acto" in prompt
    assert "predicado lingüístico" in prompt
    assert "no lo sustituyas por el nombre" in prompt
    assert "etiqueta histórica de npc" in prompt
    assert "no copies de ellos nombres propios" in prompt



def test_explicit_positive_npc_speech_report_is_normalized_to_dialogue_without_rewriting_evidence():
    from models.player_intent_analysis import PlayerIntentAnalysis, UtteranceCategory
    from models.semantic_frames import SemanticActionFamily
    from services.turns.intent_interpreter import _normalize_explicit_npc_speech_report

    utterance = "Ellas contestan en voz alta."
    analysis = PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 2,
            "category": "report",
            "steps": [{
                "index": 0,
                "source_excerpt": utterance,
                "actor": "npc",
                "action": "responder en voz alta",
                "modality": "reported",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": [],
                "attributed_to": None,
                "action_frame": {
                    "predicate": "contestan",
                    "family": "social",
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

    corrected = _normalize_explicit_npc_speech_report(analysis)
    assert corrected is not None
    assert corrected.category is UtteranceCategory.DIALOGUE
    assert corrected.steps[0].actor.value == "npc"
    assert corrected.steps[0].modality.value == "dialogue"
    assert corrected.steps[0].source_excerpt == utterance
    assert corrected.steps[0].action_frame.family is SemanticActionFamily.COMMUNICATION


def test_explicit_npc_speech_normalization_does_not_rewrite_negation_or_quotes():
    from models.player_intent_analysis import PlayerIntentAnalysis
    from services.turns.intent_interpreter import _normalize_explicit_npc_speech_report

    for utterance in (
        "Ellas no contestan.",
        'Mara repite: «Ellas contestan» y se marcha.',
    ):
        analysis = PlayerIntentAnalysis.from_payload(
            {
                "schema_version": 2,
                "category": "report",
                "steps": [{
                    "index": 0,
                    "source_excerpt": utterance,
                    "actor": "npc",
                    "action": "relatar una intervención",
                    "modality": "reported",
                    "polarity": "positive",
                    "reported_outcome": "not_claimed",
                    "target_mentions": [],
                    "attributed_to": None,
                    "action_frame": {
                        "predicate": "contestan" if "contestan" in utterance else "repite",
                        "family": "social",
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
        assert _normalize_explicit_npc_speech_report(analysis) is None

def test_normal_intent_prompt_defines_action_and_relation_semantic_taxonomies():
    prompt = " ".join(IntentInterpreter.SYSTEM_PROMPT.casefold().split())

    for required in (
        "taxonomía de action frame",
        "transfer",
        "item_use",
        "combat",
        "movement",
        "perception",
        "interaction",
        "no uses interaction como cajón de sastre",
        "patient es el ser/objetivo afectado",
        "instrument es la herramienta",
        "taxonomía de relation claims",
        "ownership",
        "possession",
        "membership",
        "allegiance",
        "límites del predicado relacional",
        "pertenece y no pertenece a",
        "jura lealtad",
        "polarity es negative",
        "modality es negated",
    ):
        assert required in prompt


def test_semantic_frame_schema_explains_roles_predicate_boundaries_and_relations():
    properties = _intent_properties(INTENT_ANALYSIS_RESPONSE_SCHEMA)
    frame_properties = properties["steps"]["items"]["properties"][
        "action_frame"
    ]["properties"]
    relation_properties = properties["relation_claims"]["items"]["properties"]

    family_description = frame_properties["family"]["description"].casefold()
    role_description = frame_properties["arguments"]["items"]["properties"][
        "role"
    ]["description"].casefold()
    predicate_description = relation_properties["predicate"]["description"].casefold()
    relation_family_description = relation_properties[
        "relation_family"
    ]["description"].casefold()
    modality_description = relation_properties["modality"]["description"].casefold()

    assert "transfer" in family_description
    assert "item_use" in family_description
    assert "combat" in family_description
    assert "interaction" in family_description
    assert "patient" in role_description
    assert "instrument" in role_description
    assert "container" in role_description
    assert "pertenece a" in predicate_description
    assert "negation markers" in predicate_description
    assert "ownership" in relation_family_description
    assert "possession" in relation_family_description
    assert "membership" in relation_family_description
    assert "reported" in modality_description
    assert "negated" in modality_description

