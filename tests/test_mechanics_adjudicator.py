import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.mechanics import MechanicsDecisionType
from models.session_state import SessionState
from models.turn_context import TurnContext
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


def test_adjudicator_skips_llm_without_active_character():
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
    assert provider.call_count == 0


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
