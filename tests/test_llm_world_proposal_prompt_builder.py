from types import SimpleNamespace

from models.campaign_state import CampaignState
from models.player_intent_analysis import PlayerIntentAnalysis
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
    assert "INTERPRETACIÓN" in prompt
    assert "Una intención no es resultado" in prompt
    for semantic_rule in (
        "plan, futuro condicional o hipótesis no ejecutada",
        "pregunta, deseo, diálogo, cita o relato de terceros",
        "intento en curso sin resultado",
        "negación, cancelación, interrupción o fracaso explícito",
        "resultado explícito y ya ocurrido",
        "Las acciones compuestas se evalúan en orden",
        "resultado mecánico confirmado por el motor",
    ):
        assert semantic_rule in prompt
    assert "Los eventos rumor son afirmaciones atribuidas" in prompt
    assert "Los eventos inference son hipótesis, no canon" in prompt
    assert "no certifica por sí sola su veracidad" in prompt
    assert "no dupliques" in prompt
    assert "Relaciones requieren evidencia" in prompt
    assert "Sin cambio justificado" in prompt


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
        allowed_operation_types=("create_entity", "create_item_instance"),
        operation_registry=DEFAULT_OPERATION_REGISTRY,
    )

    assert "TIPOS DE OPERACIÓN PERMITIDOS" in prompt
    assert '"create_item_instance"' in prompt
    assert '"required":"item_id:int|$ref"' in prompt
    assert "ID de la definición del objeto." in prompt
    assert "Usa npc para una persona identificada" in prompt
    assert '"type":"create_item_instance"' in prompt
    assert "change_character_hp" not in prompt


def test_ambiguous_entity_reference_is_spelled_out_in_proposal_prompt():
    from models.world_context_projection import (
        ContextProjectionDiagnostics,
        WorldContextProjection,
    )

    context = make_context()
    diagnostics = ContextProjectionDiagnostics(
        estimated_tokens=0,
        budget_tokens=500,
        available_counts=(),
        candidate_counts=(),
        selected_counts=(),
        reference_status="ambiguous",
        reference_match_kind="alias",
        reference_candidate_count=2,
    )
    projection = WorldContextProjection(world=WorldState(), diagnostics=diagnostics)
    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "Hablo con el guardia.",
        context,
        projection=projection,
    )

    assert "coincide con varios registros" in prompt
    assert "no elijas uno al azar" in prompt.casefold()


def test_proposal_prompt_uses_shared_analysis_and_bounded_conversation_history():
    source = "Abro la misma puerta."
    analysis = PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 1,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": "Abro la misma puerta",
                "actor": "player",
                "action": "abrir la misma puerta",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["la misma puerta"],
                "attributed_to": None,
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
        source_text=source,
    )

    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        source,
        make_context(),
        intent_analysis=analysis,
        recent_turns=[{
            "player_input": "Aldric señala una puerta de roble al fondo.",
            "narrative": "La puerta de roble está junto a una lámpara.",
        }],
    )

    assert analysis.to_json() in prompt
    assert "Aldric señala una puerta de roble" in prompt
    assert "La puerta de roble está junto a una lámpara" in prompt
    assert "no vuelvas a inferir por separado" in prompt
    assert "preguntas, citas, negaciones y condicionales" in prompt
