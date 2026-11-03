from models.character_state import CharacterState
from rules_engine.dnd5e_2014.core.dice import DiceRoller
from rules_engine.dnd5e_2014.core.skills import Skill
from services.context_builder import ContextBuilder
from services.dm_service import DMService
from services.fake_llm_provider import FakeLLMProvider
from services.llm_world_extractor import LLMWorldExtractor
from services.mechanics_adjudicator import MechanicsAdjudicator
from services.turn_resolution_service import TurnResolutionService
from services.world_applier import WorldApplier
from services.world_service import WorldService


class FixedRandom:
    def __init__(self, *values):
        self.values = iter(values)

    def randint(self, a, b):
        value = next(self.values)
        assert a <= value <= b
        return value


class EmptyExtractor(LLMWorldExtractor):
    def __init__(self):
        self.received = []

    def extract(self, text, context):
        self.received.append(text)
        return []


def make_service(adjudication_json, roll):
    adjudicator = MechanicsAdjudicator(
        FakeLLMProvider(response=adjudication_json)
    )
    narrative_provider = FakeLLMProvider(
        response="La acción se resuelve según el resultado de la prueba."
    )
    dm = DMService(narrative_provider, ContextBuilder())
    extractor = EmptyExtractor()
    resolver = TurnResolutionService(
        dm_service=dm,
        extractor=extractor,
        world_service=WorldService(applier=WorldApplier()),
        mechanics_adjudicator=adjudicator,
        dice_roller=DiceRoller(FixedRandom(roll)),
    )
    return resolver, narrative_provider, extractor


def test_skill_check_is_rolled_by_engine_before_dm_narration():
    character = CharacterState(
        entity_id=20,
        level=1,
        dexterity=16,
        skill_proficiencies=frozenset({Skill.STEALTH}),
    )
    resolver, narrative_provider, extractor = make_service(
        '{"decision":"skill_check","skill":"stealth","ability":null,"dc":15,'
        '"advantage":false,"disadvantage":false,"modifier":0,"reason":"Evitar al guardia"}',
        12,
    )

    plan = resolver.prepare_turn(
        make_turn_context_with_character(character),
        "Me muevo sigilosamente.",
    )

    assert plan.mechanics_result is not None
    assert plan.mechanics_result.check.roll.selected == 12
    assert plan.mechanics_result.check.roll.modifier == 5
    assert plan.mechanics_result.check.total == 17
    assert plan.mechanics_result.check.success is True
    assert "Total: 17" in narrative_provider.last_prompt
    assert "Resultado: success" in narrative_provider.last_prompt
    assert len(extractor.received) == 1



def test_unskilled_ability_check_uses_only_ability_modifier():
    character = CharacterState(
        entity_id=20,
        level=1,
        strength=16,
    )
    resolver, narrative_provider, _extractor = make_service(
        '{"decision":"ability_check","ability":"strength","dc":15,'
        '"advantage":false,"disadvantage":false,"modifier":0,"reason":"Empujar la roca"}',
        12,
    )

    plan = resolver.prepare_turn(
        make_turn_context_with_character(character),
        "Empujo la roca.",
    )

    assert plan.mechanics_result is not None
    assert plan.mechanics_result.check.kind == "ability_check"
    assert plan.mechanics_result.check.roll.modifier == 3
    assert plan.mechanics_result.check.total == 15
    assert plan.mechanics_result.check.success is True
    assert "Total: 15" in narrative_provider.last_prompt


def test_clarification_stops_before_narration_and_extraction():
    resolver, narrative_provider, extractor = make_service(
        '{"decision":"clarification","question":"¿Qué herramienta utilizas?"}',
        10,
    )

    plan = resolver.prepare_turn(
        make_turn_context_with_character(CharacterState(entity_id=20)),
        "Abro la cerradura.",
    )
    assert plan.clarification_question == "¿Qué herramienta utilizas?"
    assert narrative_provider.call_count == 0
    assert extractor.received == []


def make_turn_context_with_character(character):
    from models.campaign_state import CampaignState
    from models.session_state import SessionState
    from models.turn_context import TurnContext
    from models.world_state import WorldState

    return TurnContext(
        campaign=CampaignState(campaign_id=1, name="Test"),
        current_session=SessionState(session_id=1, number=1, title="Test"),
        active_character=character,
        world=WorldState(),
    )
