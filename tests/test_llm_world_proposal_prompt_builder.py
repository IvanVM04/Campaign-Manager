from types import SimpleNamespace

from models.campaign_state import CampaignState
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.llm_world.llm_world_context_renderer import LLMWorldContextRenderer
from services.llm_world.llm_world_proposal_prompt_builder import (
    LLMWorldProposalPromptBuilder,
)


def make_context():
    return TurnContext(
        campaign=CampaignState(),
        current_session=None,
        active_character=None,
        world=WorldState(),
    )


def test_proposal_prompt_builder_renders_shared_world_projection(monkeypatch):
    projection = {
        "campaign_block": "Campaña: La mina",
        "session_block": "Sesión: Entrada al mercado",
        "character_block": "Personaje activo: Fungoso",
        "conditions_block": "Condiciones: poisoned",
        "known_entities": "- ID 7: Aldric (npc)",
        "known_items": "- ID 3: Espada",
        "known_item_instances": "- ID 9: Espada (owner_id=1)",
        "known_resources": "- ID 2: Oro",
        "known_resource_balances": "- ID 10: 80 mo de Oro",
        "known_relations": "- Aldric pertenece a la guardia",
        "known_events": "- ID 4: Llegada a la ciudad",
    }
    monkeypatch.setattr(
        LLMWorldContextRenderer,
        "build_context",
        staticmethod(lambda context: projection),
    )

    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "Quiero hablar con Aldric.",
        make_context(),
    )

    assert "CONTEXTO ACTUAL DEL MUNDO" in prompt
    assert "Campaña: La mina" in prompt
    assert "Sesión: Entrada al mercado" in prompt
    assert "Condiciones: poisoned" in prompt
    assert "INTENCIÓN DEL JUGADOR:\nQuiero hablar con Aldric." in prompt
    for section in projection.values():
        assert section in prompt
    assert "NARRATIVA A ANALIZAR" not in prompt
    assert "Ahora analiza únicamente" not in prompt
    assert "Las operaciones son propuestas, no hechos confirmados." in prompt
    assert "No afirmes que las acciones ya han ocurrido" in prompt


def test_proposal_prompt_builder_appends_confirmed_mechanics():
    mechanics = SimpleNamespace(
        to_prompt_text=lambda: "Resultado: éxito en percepción."
    )

    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "Busco huellas.",
        make_context(),
        mechanics_result=mechanics,
    )

    assert (
        "\n\nRESULTADO MECÁNICO CONFIRMADO POR EL MOTOR\n"
        "Resultado: éxito en percepción."
    ) in prompt


def test_proposal_prompt_builder_lists_only_model_proposable_operations():
    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "Busco una bolsa.",
        make_context(),
        allowed_operation_types=("create_entity", "create_item_instance"),
    )

    assert "TIPOS DE OPERACIÓN PERMITIDOS" in prompt
    assert "create_entity" in prompt
    assert "create_item_instance" in prompt
    assert "change_character_hp" not in prompt


def test_proposal_prompt_builder_rejects_prompts_over_estimated_token_budget():
    import pytest

    from services.llm_world.llm_extraction_errors import LLMExtractionError

    with pytest.raises(LLMExtractionError, match="exceeds the configured"):
        LLMWorldProposalPromptBuilder.build_prompt(
            "Quiero explorar. " * 1000,
            make_context(),
            max_prompt_tokens=100,
        )


def test_proposal_prompt_builder_renders_the_shared_operation_schema():
    from services.llm_world.operation_registry import DEFAULT_OPERATION_REGISTRY

    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "Quiero recoger la llave.",
        make_context(),
        allowed_operation_types=("create_item_instance",),
        operation_registry=DEFAULT_OPERATION_REGISTRY,
    )

    assert "TIPOS DE OPERACIÓN PERMITIDOS" in prompt
    assert '"const":"create_item_instance"' in prompt
    assert '"required":["type","item_id"]' in prompt
    assert "ID de la definición del objeto." in prompt
    assert '"type":"create_item_instance"' in prompt
    assert "change_character_hp" not in prompt
