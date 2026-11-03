from models.character_state import CharacterState
from rules_engine.dnd5e_2014.core.abilities import Ability
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
        dice_roller=DiceRoller(FixedRandom(roll, roll)),
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



def test_saving_throw_uses_character_save_proficiency():
    character = CharacterState(
        entity_id=20,
        level=1,
        wisdom=16,
        saving_throw_proficiencies=frozenset({Ability.WISDOM}),
    )
    resolver, narrative_provider, _extractor = make_service(
        '{"decision":"saving_throw","ability":"wisdom","dc":14,'
        '"advantage":false,"disadvantage":false,"modifier":0,"reason":"Resistir el miedo"}',
        10,
    )

    plan = resolver.prepare_turn(
        make_turn_context_with_character(character),
        "Resisto el miedo.",
    )

    assert plan.mechanics_result is not None
    assert plan.mechanics_result.check.kind == "saving_throw"
    assert plan.mechanics_result.check.roll.modifier == 5
    assert plan.mechanics_result.check.total == 15
    assert plan.mechanics_result.check.success is True
    assert "Total: 15" in narrative_provider.last_prompt



def test_manual_roll_pauses_then_resolves_without_second_adjudication():
    character = CharacterState(
        entity_id=20,
        level=1,
        dexterity=16,
        skill_proficiencies=frozenset({Skill.STEALTH}),
    )
    resolver, narrative_provider, _extractor = make_service(
        '{"decision":"skill_check","skill":"stealth","ability":null,"dc":15,'
        '"advantage":false,"disadvantage":false,"modifier":0,"reason":"Evitar al guardia"}',
        2,
    )
    context = make_turn_context_with_character(character)

    pending = resolver.prepare_turn(
        context,
        "Me muevo sigilosamente.",
        manual_mode=True,
    )

    assert pending.awaiting_manual_roll is True
    assert pending.mechanics_decision is not None
    assert narrative_provider.call_count == 0
    adjudicator_calls = resolver.mechanics_adjudicator.provider.call_count

    completed = resolver.prepare_turn(
        context,
        "Me muevo sigilosamente.",
        decision_override=pending.mechanics_decision,
        manual_rolls=(12,),
    )

    assert resolver.mechanics_adjudicator.provider.call_count == adjudicator_calls
    assert completed.mechanics_result is not None
    assert completed.mechanics_result.check.roll.rolls == (12,)
    assert completed.mechanics_result.check.total == 17
    assert completed.mechanics_result.check.success is True
    assert "Total: 17" in narrative_provider.last_prompt


def test_manual_advantage_request_asks_for_two_d20_results():
    character = CharacterState(entity_id=20, level=1, dexterity=16)
    resolver, _narrative_provider, _extractor = make_service(
        '{"decision":"skill_check","skill":"stealth","ability":null,"dc":15,'
        '"advantage":true,"disadvantage":false,"modifier":0,"reason":"Ocultarse"}',
        2,
    )

    pending = resolver.prepare_turn(
        make_turn_context_with_character(character),
        "Me escondo.",
        manual_mode=True,
    )

    assert pending.awaiting_manual_roll is True
    assert pending.mechanics_decision.advantage is True


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


def test_persistent_poisoned_condition_imposes_disadvantage_on_skill_check():
    from dataclasses import replace
    from rules_engine.dnd5e_2014.combat.conditions import Condition, ConditionSet

    character = CharacterState(entity_id=20, level=1, dexterity=16)
    resolver, _narrative_provider, _extractor = make_service(
        '{"decision":"skill_check","skill":"stealth","ability":null,"dc":15,'
        '"advantage":false,"disadvantage":false,"modifier":0,"reason":"Evitar al guardia"}',
        5,
    )
    context = replace(
        make_turn_context_with_character(character),
        active_character_conditions=ConditionSet(frozenset({Condition.POISONED})),
    )
    plan = resolver.prepare_turn(context, "Me muevo sigilosamente.")
    assert plan.mechanics_result is not None
    assert plan.mechanics_decision.disadvantage is True
    assert plan.mechanics_result.check.roll.rolls == (5, 5)


def test_persistent_exhaustion_imposes_disadvantage_on_saving_throw():
    from dataclasses import replace
    from rules_engine.dnd5e_2014.combat.conditions import ConditionSet

    character = CharacterState(entity_id=20, level=1, wisdom=16)
    resolver, _narrative_provider, _extractor = make_service(
        '{"decision":"saving_throw","ability":"wisdom","dc":14,'
        '"advantage":false,"disadvantage":false,"modifier":0,"reason":"Resistir el miedo"}',
        15,
    )
    context = replace(
        make_turn_context_with_character(character),
        active_character_conditions=ConditionSet(exhaustion_level=3),
    )
    pending = resolver.prepare_turn(context, "Resisto el miedo.", manual_mode=True)
    assert pending.awaiting_manual_roll is True
    assert pending.mechanics_decision.disadvantage is True
    assert pending.mechanics_decision is not None
