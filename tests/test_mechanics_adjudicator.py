import json

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.mechanics import MechanicsDecisionType
from models.session_state import SessionState
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.world_state import WorldState
from rules_engine.dnd5e_2014.core.abilities import Ability
from rules_engine.dnd5e_2014.core.skills import Skill
from services.providers import FakeLLMProvider
from services.turns import (
    MechanicsAdjudicator,
    MechanicsAdjudicatorError,
)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ('{"decision":"none"}', MechanicsDecisionType.NONE),
        (
            (
                '{"decision":"ability_check","ability":"strength","dc":15,'
                '"advantage":false,"disadvantage":false,"modifier":0,"reason":"Empujar una roca"}'
            ),
            MechanicsDecisionType.ABILITY_CHECK,
        ),
        (
            (
                '{"decision":"skill_check","skill":"stealth","ability":null,"dc":15,'
                '"advantage":false,"disadvantage":false,"modifier":0,"reason":"Cruzar sin ser visto"}'
            ),
            MechanicsDecisionType.SKILL_CHECK,
        ),
        (
            (
                '{"decision":"saving_throw","ability":"wisdom","dc":14,'
                '"advantage":false,"disadvantage":false,"modifier":0,"reason":"Resistir el miedo"}'
            ),
            MechanicsDecisionType.SAVING_THROW,
        ),
        (
            '{"decision":"clarification","question":"¿Qué puerta intentas abrir?"}',
            MechanicsDecisionType.CLARIFICATION,
        ),
    ],
)
def test_adjudicator_parses_supported_decisions(payload, expected):
    adjudicator = MechanicsAdjudicator(FakeLLMProvider(response=payload))
    decision = adjudicator.adjudicate(make_turn_context(), "Intento algo.")

    assert decision.decision is expected


def test_skill_check_is_typed():
    provider = FakeLLMProvider(
        response='{"decision":"skill_check","skill":"stealth","ability":"strength","dc":15,'
        '"advantage":false,"disadvantage":false,"modifier":0,"reason":"Escalar sin ruido"}'
    )
    decision = MechanicsAdjudicator(provider).adjudicate(
        make_turn_context(), "Escalo."
    )

    assert decision.skill is Skill.STEALTH
    assert decision.ability is Ability.STRENGTH


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        (
            '{"decision":"skill_check","skill":"acrobatics","dc":99,"advantage":false,'
            '"disadvantage":false,"modifier":0,"reason":"invalid"}'
        ),
        (
            '{"decision":"skill_check","skill":"made_up","ability":null,"dc":10,'
            '"advantage":false,"disadvantage":false,"modifier":0,"reason":"invalid"}'
        ),
        '{"decision":"none","dc":10}',
        (
            '{"decision":"saving_throw","ability":"wisdom","dc":14,'
            '"advantage":true,"disadvantage":false,"modifier":0,"reason":"x","extra":1}'
        ),
    ],
)
def test_adjudicator_rejects_invalid_or_unexpected_output(payload):
    adjudicator = MechanicsAdjudicator(FakeLLMProvider(response=payload))

    with pytest.raises(MechanicsAdjudicatorError):
        adjudicator.adjudicate(make_turn_context(), "Intento algo.")


def test_adjudicator_still_extracts_intent_without_active_character():
    context = make_turn_context()
    context = TurnContext(
        campaign=context.campaign,
        current_session=context.current_session,
        active_character=None,
        world=context.world,
    )
    provider = FakeLLMProvider(response='{"decision":"none"}')

    decision = MechanicsAdjudicator(provider).adjudicate(context, "Miro.")

    assert decision.decision is MechanicsDecisionType.NONE
    assert provider.call_count == 1


def make_turn_context():
    return TurnContext(
        campaign=CampaignState(campaign_id=1, name="Test"),
        current_session=SessionState(session_id=1, number=1, title="Test"),
        active_character=CharacterState(entity_id=20),
        world=WorldState(),
    )



def test_system_prompt_classifies_player_action_modality_before_checking():
    prompt = MechanicsAdjudicator.SYSTEM_PROMPT.casefold()

    assert "hipótesis condicional" in prompt
    assert "pregunta" in prompt
    assert "acción cancelada" in prompt
    assert "diálogo citado" in prompt
    assert "paso activo" in prompt
    assert "no elijas un objetivo al azar" in prompt


def test_adjudicator_retrieves_context_for_the_active_character():
    from services.context import ContextBuilder

    class RecordingContextBuilder(ContextBuilder):
        def __init__(self):
            super().__init__()
            self.character_entity_id = None

        def build(
            self,
            world,
            query,
            recent_turns=None,
            *,
            supplemental_queries=(),
            character_entity_id=None,
        ):
            self.character_entity_id = character_entity_id
            return {"context": "Only this character's known facts."}

    context_builder = RecordingContextBuilder()
    adjudicator = MechanicsAdjudicator(
        FakeLLMProvider(response='{"decision":"none"}'),
        context_builder,
    )

    decision = adjudicator.adjudicate(make_turn_context(), "Miro alrededor.")

    assert decision.decision is MechanicsDecisionType.NONE
    assert context_builder.character_entity_id == 20



def test_system_prompt_does_not_treat_rumors_or_inferences_as_confirmed_facts():
    prompt = MechanicsAdjudicator.SYSTEM_PROMPT.casefold()

    assert "un rumor es una afirmación atribuida" in prompt
    assert "una inferencia es una posibilidad" in prompt
    assert "no bases una cd" in prompt
    assert "pide aclaración" in prompt


def test_adjudicator_returns_one_shared_analysis_and_mechanics_response(monkeypatch):
    player_input = "Cruzo la plaza."
    provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": {
            "schema_version": 1,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": "Cruzo la plaza",
                "actor": "player",
                "action": "cruzar la plaza",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["la plaza"],
                "attributed_to": None,
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
        "mechanics_decision": {"decision": "none"},
    }))
    structured_call = {}
    original_generate = provider.generate

    def generate_structured(prompt, *, schema):
        structured_call["schema"] = schema
        return original_generate(prompt)

    monkeypatch.setattr(provider, "generate_structured", generate_structured)
    analysis, decision = MechanicsAdjudicator(provider).understand(
        make_turn_context(),
        player_input,
        recent_turns=[TurnRecord(
            player_input="He visto a Aldric en la entrada.",
            narrative="Aldric se aparta para dejarte pasar.",
        )],
    )

    assert analysis.steps[0].source_excerpt == "Cruzo la plaza"
    assert analysis.steps[0].target_mentions == ("la plaza",)
    assert analysis.is_actionable is True
    assert decision.decision is MechanicsDecisionType.NONE
    assert provider.call_count == 1
    assert structured_call["schema"]["required"] == [
        "intent_analysis",
        "mechanics_decision",
    ]
    intent_schema = structured_call["schema"]["properties"]["intent_analysis"]
    assert intent_schema["properties"]["schema_version"]["const"] == 2
    assert "relation_claims" in intent_schema["required"]
    step_schema = intent_schema["properties"]["steps"]["items"]
    assert "action_frame" in step_schema["required"]


def test_clarification_questions_are_context_but_not_player_source_evidence():
    conversation = (
        "Abro la puerta.\\n\\nAclaración del DM: ¿Qué puerta? "
        "\\nRespuesta del jugador: la puerta de roble."
    )
    evidence = "Abro la puerta.\\nla puerta de roble."
    response = json.dumps({
        "intent_analysis": {
            "schema_version": 1,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": "la puerta de roble",
                "actor": "player",
                "action": "abrir la puerta de roble",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["la puerta de roble"],
                "attributed_to": None,
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
        "mechanics_decision": {"decision": "none"},
    })
    provider = FakeLLMProvider(response=response)

    analysis, _decision = MechanicsAdjudicator(provider).understand(
        make_turn_context(),
        conversation,
        evidence_text=evidence,
    )

    assert analysis.steps[0].source_excerpt == "la puerta de roble"
    assert "¿Qué puerta?" in provider.prompts[0]
    assert "¿Qué puerta?" in provider.prompts[0].split(
        "EVIDENCIA ESCRITA POR EL JUGADOR", maxsplit=1
    )[0]
    evidence_section = provider.prompts[0].split(
        "=== EVIDENCIA ESCRITA POR EL JUGADOR", maxsplit=1
    )[1]
    assert "¿Qué puerta?" not in evidence_section
    assert "la puerta de roble" in evidence_section


def test_production_understand_fails_closed_when_provider_omits_intent_v1():
    provider = FakeLLMProvider(
        response=(
            '{"decision":"skill_check","skill":"stealth","ability":null,'
            '"dc":15,"advantage":false,"disadvantage":false,'
            '"modifier":0,"reason":"legacy response"}'
        )
    )

    analysis, decision = MechanicsAdjudicator(provider).understand(
        make_turn_context(),
        "Me escondo tras la columna.",
    )

    assert analysis.requires_clarification is True
    assert analysis.category.value == "unknown"
    assert analysis.steps == ()
    assert decision.decision is MechanicsDecisionType.NONE


def test_invalid_combined_analysis_is_rejected_before_mechanics_use():
    response = json.dumps({
        "intent_analysis": {
            "schema_version": 1,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": "El personaje abre la puerta",
                "actor": "player",
                "action": "abrir la puerta",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["la puerta"],
                "attributed_to": None,
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
        "mechanics_decision": {"decision": "none"},
    })
    adjudicator = MechanicsAdjudicator(FakeLLMProvider(response=response))

    with pytest.raises(MechanicsAdjudicatorError, match="source_excerpt"):
        adjudicator.understand(make_turn_context(), "Abro la puerta.")





def test_mechanics_adjudicator_bounds_context_without_truncating_player_evidence(monkeypatch):
    from services.context import ContextBuilder

    context_builder = ContextBuilder()
    monkeypatch.setattr(
        context_builder,
        "build",
        lambda *args, **kwargs: {"context": "HECHO VISIBLE " * 2000},
    )
    response = json.dumps({
        "intent_analysis": {
            "schema_version": 1,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": "Abro la puerta.",
                "actor": "player",
                "action": "abrir la puerta",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": ["la puerta"],
                "attributed_to": None,
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
        "mechanics_decision": {"decision": "none"},
    })
    provider = FakeLLMProvider(response=response)
    adjudicator = MechanicsAdjudicator(
        provider,
        context_builder,
        max_prompt_tokens=8192,
        max_context_tokens=3000,
    )

    adjudicator.understand(
        make_turn_context(),
        "Abro la puerta.",
        evidence_text="Abro la puerta.",
    )

    prompt = provider.prompts[0]
    from models.world_context_projection import estimate_tokens

    assert estimate_tokens(prompt) <= 8192
    assert "Abro la puerta." in prompt
    assert "=== EVIDENCIA ESCRITA POR EL JUGADOR" in prompt
    assert len(prompt.encode("utf-8")) < 12000


def test_mechanics_adjudicator_rejects_fixed_evidence_that_cannot_fit_prompt_budget():
    provider = FakeLLMProvider(response='{"decision":"none"}')
    adjudicator = MechanicsAdjudicator(
        provider,
        max_prompt_tokens=128,
        max_context_tokens=64,
    )
    huge_player_input = "Abro la puerta. " * 100

    with pytest.raises(MechanicsAdjudicatorError, match="mechanics prompt exceeds"):
        adjudicator.understand(
            make_turn_context(),
            huge_player_input,
            evidence_text=huge_player_input,
        )
