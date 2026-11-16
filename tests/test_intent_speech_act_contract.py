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
        "step_index",
        "slot",
        "previous_value",
        "replacement",
        "source_excerpt",
    ]
    assert set(correction_item["properties"]) == set(correction_item["required"])
    assert "argument_role" not in correction_item["properties"]
    assert "relation_claim_index" not in correction_item["properties"]
    assert "el servidor resuelve el rol" in prompt
    assert 'status="needs_clarification"' in prompt
