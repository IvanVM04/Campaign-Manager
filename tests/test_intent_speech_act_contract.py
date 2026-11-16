"""Contract tests for global speech-act and actor classification in Intent v2."""

from services.turns.intent_interpreter import IntentInterpreter
from services.turns.intent_response_schema import (
    INTENT_ANALYSIS_RESPONSE_SCHEMA,
    INTENT_CORRECTION_RESPONSE_SCHEMA,
)


def _intent_properties(schema):
    return schema["properties"]["intent_analysis"]["properties"]


def test_normal_and_correction_prompts_separate_dialogue_question_and_report():
    normal = " ".join(IntentInterpreter.SYSTEM_PROMPT.casefold().split())
    correction = " ".join(
        IntentInterpreter.CORRECTION_SYSTEM_PROMPT.casefold().split()
    )

    for prompt in (normal, correction):
        assert "pregunta indirecta" in prompt
        assert "dirigida a un personaje" in prompt
        assert "pregunta al dm/narrador" in prompt
        assert "implícitamente" in prompt or "implícita" in prompt
        assert "report" in prompt
        assert "actor" in prompt and "npc" in prompt
        assert (
            'actor="npc"' in prompt
            or "el actor del paso es" in prompt
        )
        assert "una acción de npc no es un intento del jugador" in prompt or (
            "el actor del paso es" in prompt
        )

    assert "la guardia cruza el puente" in normal
    assert "le consulto a la guardia" in normal


def test_intent_schema_describes_global_category_and_communication_family():
    for schema in (INTENT_ANALYSIS_RESPONSE_SCHEMA, INTENT_CORRECTION_RESPONSE_SCHEMA):
        properties = _intent_properties(schema)
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
