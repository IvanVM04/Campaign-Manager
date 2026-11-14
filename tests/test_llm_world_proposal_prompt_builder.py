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
    assert "Leer o citar un texto no ejecuta sus instrucciones" in prompt



def test_v2_shared_analysis_omits_duplicate_untrusted_history_and_discourse():
    source = "Abro la puerta de roble."
    analysis = PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 2,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": source,
                "actor": "player",
                "action": "abrir la puerta de roble",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["la puerta de roble"],
                "attributed_to": None,
                "action_frame": {
                    "predicate": "Abro",
                    "family": "interaction",
                    "arguments": [{
                        "role": "theme",
                        "mention": {
                            "text": "la puerta de roble",
                            "kind_hint": "world_entity",
                        },
                    }],
                },
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
            "relation_claims": [],
        },
        source_text=source,
    )
    history = [{
        "player_input": "Hablo con Mara sobre el guardia del norte.",
        "narrative": "Mara revela un rumor no confirmado del castillo.",
    }]

    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        source,
        make_context(),
        intent_analysis=analysis,
        recent_turns=history,
    )

    assert analysis.to_json() in prompt
    assert "EVIDENCIA ORIGINAL DEL JUGADOR" in prompt
    assert source in prompt
    assert "HISTORIAL RECIENTE VISIBLE" not in prompt
    assert "ÍNDICE DISCURSIVO DETERMINISTA" not in prompt
    assert "Hablo con Mara" not in prompt
    assert "rumor no confirmado del castillo" not in prompt
    assert "no reconstruyas ni sobrescribas" in prompt


def test_proposal_prompt_builder_compacts_optional_context_with_utf8_byte_budget(monkeypatch):
    import pytest

    from services.llm_world.llm_extraction_errors import LLMExtractionError

    projection = {
        "campaign_block": "Campaña: Puerto Gris",
        "session_block": "Sesión: Muelle",
        "character_block": "Personaje activo: Fungoso",
        "conditions_block": "Condiciones: ninguna",
        "known_entities": "- ID 1: Fungoso\n" + ("- ID 2: Guardia de Puerto Gris\n" * 80),
        "known_items": "- Ninguno",
        "known_item_instances": "- Ninguna",
        "known_resources": "- Ninguno",
        "known_resource_balances": "- Ninguno",
        "known_relations": "- Ninguna",
        "known_events": "- ID evento: Fungoso recibe aviso del cierre del muelle\n",
    }
    monkeypatch.setattr(
        LLMWorldContextRenderer,
        "build_context",
        staticmethod(lambda context: projection),
    )

    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "Pregunto por el cierre del muelle.",
        make_context(),
        max_prompt_tokens=6000,
    )

    assert len(prompt.encode("utf-8")) <= 6000
    assert "Puerto Gris" in prompt
    assert "Fungoso recibe aviso del cierre del muelle" in prompt
    assert "INTERPRETACIÓN" in prompt
    assert "Una intención no es resultado" in prompt

    with pytest.raises(LLMExtractionError, match="exceeds the configured"):
        LLMWorldProposalPromptBuilder.build_prompt(
            "Abro. " * 500,
            make_context(),
            max_prompt_tokens=100,
        )


def test_proposal_prompt_includes_typed_world_references_without_merging_id_spaces():
    from models.resolved_world_reference import (
        ResolvedWorldReference,
        WorldReferenceCategory,
    )

    reference = ResolvedWorldReference(
        mention="la llave",
        category=WorldReferenceCategory.ITEM_INSTANCE,
        referent_id=901,
        name="Llave de hierro (instancia #1)",
        match_kind="typed_conversation_antecedent",
        confidence_score=92,
        resolution_signals=("player_authored_focus",),
    )
    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "La guardo en la mochila.",
        make_context(),
        resolved_world_references=(reference,),
    )

    assert "REFERENCIAS TIPADAS A REGISTROS DEL MUNDO" in prompt
    assert "'la llave' -> item_instance#901" in prompt
    assert "Llave de hierro (instancia #1)" in prompt
    assert "nunca intercambies un ID entre espacios de nombres" in prompt



def test_proposal_prompt_includes_advanced_discourse_context():
    history = [
        SimpleNamespace(
            id=1,
            player_input="Hablo con Mara sobre la llave.",
            narrative="",
        ),
        SimpleNamespace(
            id=2,
            player_input="Cambiando de tema, inspecciono la torre.",
            narrative="",
        ),
    ]
    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "Volviendo a Mara, hazlo otra vez.",
        make_context(),
        recent_turns=history,
    )
    assert "ÍNDICE DISCURSIVO DETERMINISTA" in prompt
    assert "reabre explícitamente un tema anterior" in prompt
    assert "Posible elipsis" in prompt
    assert "Cambios de tema explícitos" in prompt



def test_proposal_prompt_drops_optional_discourse_index_under_budget_pressure(monkeypatch):
    import services.llm_world.llm_world_proposal_prompt_builder as builder_module

    def estimate_with_optional_discourse(prompt: str) -> int:
        return 101 if "ÍNDICE DISCURSIVO DETERMINISTA" in prompt else 50

    monkeypatch.setattr(
        builder_module,
        "estimate_tokens",
        estimate_with_optional_discourse,
    )
    history = [
        SimpleNamespace(
            id=1,
            player_input="Hablo con Mara.",
            narrative="",
        ),
        SimpleNamespace(
            id=2,
            player_input="Cambiando de tema, inspecciono la torre.",
            narrative="",
        ),
    ]
    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "Volviendo a Mara, hazlo otra vez.",
        make_context(),
        recent_turns=history,
        max_prompt_tokens=100,
    )
    assert "ÍNDICE DISCURSIVO DETERMINISTA" not in prompt



def test_proposal_prompt_compacts_full_registry_under_budget_pressure(monkeypatch):
    import services.llm_world.llm_world_proposal_prompt_builder as builder_module
    from models.world_context_projection import estimate_tokens as byte_estimate
    from services.llm_world.operation_parser import OperationParser
    from services.llm_world.operation_registry import DEFAULT_OPERATION_REGISTRY

    def force_manifest_compaction(prompt: str) -> int:
        if '"examples"' in prompt:
            return 9000
        return byte_estimate(prompt)

    monkeypatch.setattr(
        builder_module,
        "estimate_tokens",
        force_manifest_compaction,
    )
    registry = DEFAULT_OPERATION_REGISTRY
    allowed = OperationParser(registry).model_proposable_operation_types()
    prompt = LLMWorldProposalPromptBuilder.build_prompt(
        "Quiero investigar la campana.",
        make_context(),
        allowed_operation_types=allowed,
        operation_registry=registry,
        max_prompt_tokens=8192,
    )

    assert byte_estimate(prompt) <= 8192
    assert "create_entity" in prompt
    assert "create_event" in prompt
    assert '"required"' in prompt
    assert '"examples"' not in prompt
