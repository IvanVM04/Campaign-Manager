from types import SimpleNamespace

import pytest

from models.campaign_state import CampaignState
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.llm_world.llm_extraction_errors import LLMExtractionError
from services.llm_world_proposal_prompt_builder import (
    LLMWorldProposalPromptBuilder,
)


def make_context():
    return TurnContext(
        campaign=CampaignState(),
        current_session=None,
        active_character=None,
        world=WorldState(),
    )


def context_prompt(text, context):
    return (
        "INSTRUCCIONES ESTÁTICAS\n"
        "CONTEXTO ACTUAL DEL MUNDO\n"
        "NARRATIVA A ANALIZAR\n"
        "Ahora analiza únicamente la INTENCIÓN DEL JUGADOR utilizando el contexto\n"
        "============================================================\n"
        "FIN DE LOS DATOS DE ENTRADA\n"
    )


def test_proposal_prompt_builder_adapts_context_and_inserts_player_intent():
    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "Quiero hablar con Aldric.",
        make_context(),
        context_prompt_builder=context_prompt,
    )

    assert "INTENCIÓN DEL JUGADOR" in prompt
    assert "NARRATIVA A ANALIZAR" not in prompt
    assert "Quiero hablar con Aldric." in prompt
    assert "Las operaciones son propuestas, no hechos confirmados." in prompt
    assert "No afirmes que ya han ocurrido" in prompt


def test_proposal_prompt_builder_appends_confirmed_mechanics():
    mechanics = SimpleNamespace(
        to_prompt_text=lambda: "Resultado: éxito en percepción."
    )

    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "Busco huellas.",
        make_context(),
        context_prompt_builder=context_prompt,
        mechanics_result=mechanics,
    )

    assert (
        "\n\nRESULTADO MECÁNICO CONFIRMADO POR EL MOTOR\n"
        "Resultado: éxito en percepción."
    ) in prompt


def test_proposal_prompt_builder_rejects_missing_world_context_marker():
    with pytest.raises(
        LLMExtractionError,
        match="failed to build structured world context",
    ):
        LLMWorldProposalPromptBuilder.build_prompt(
            "Busco huellas.",
            make_context(),
            context_prompt_builder=lambda text, context: "No context section",
        )


def test_proposal_prompt_builder_rejects_missing_input_end_marker():
    with pytest.raises(
        LLMExtractionError,
        match="failed to place player intent",
    ):
        LLMWorldProposalPromptBuilder.build_prompt(
            "Busco huellas.",
            make_context(),
            context_prompt_builder=lambda text, context: (
                "CONTEXTO ACTUAL DEL MUNDO\n"
                "NARRATIVA A ANALIZAR"
            ),
        )
