import json

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.mechanics import MechanicsDecisionType
from models.session_state import SessionState
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.providers import FakeLLMProvider
from services.turns import IntentInterpreter, MechanicsAdjudicator
from services.turns.intent_response_schema import MECHANICS_ONLY_RESPONSE_SCHEMA
from services.turns.intent_response_schema import INTENT_ANALYSIS_RESPONSE_SCHEMA


def _context(*, active_character=True):
    return TurnContext(
        campaign=CampaignState(campaign_id=1, name="Test"),
        current_session=SessionState(session_id=1, number=1, title="Test"),
        active_character=(
            CharacterState(entity_id=20) if active_character else None
        ),
        world=WorldState(),
    )


def _analysis_payload(
    *,
    modality="attempted",
    polarity="positive",
    reported_outcome="not_claimed",
    active_step_index=0,
    category="action",
):
    return {
        "schema_version": 2,
        "category": category,
        "steps": [{
            "index": 0,
            "source_excerpt": "Abro la puerta.",
            "actor": "player",
            "action": "abrir la puerta",
            "modality": modality,
            "polarity": polarity,
            "reported_outcome": reported_outcome,
            "target_mentions": ["la puerta"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "Abro",
                "family": "interaction",
                "arguments": [{
                    "role": "theme",
                    "mention": {
                        "text": "la puerta",
                        "kind_hint": "world_entity",
                    },
                }],
            },
        }],
        "active_step_index": active_step_index,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }


def test_intent_interpreter_emits_only_shared_semantic_analysis():
    provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": _analysis_payload(),
    }))
    interpreter = IntentInterpreter(provider)

    analysis = interpreter.interpret(_context(), "Abro la puerta.")

    assert analysis.schema_version == 2
    assert analysis.is_actionable is True
    assert analysis.steps[0].action_frame.arguments[0].role.value == "theme"
    assert provider.call_count == 1
    assert INTENT_ANALYSIS_RESPONSE_SCHEMA["required"] == ["intent_analysis"]
    assert set(INTENT_ANALYSIS_RESPONSE_SCHEMA["properties"]) == {"intent_analysis"}
    assert "mechanics_decision" not in INTENT_ANALYSIS_RESPONSE_SCHEMA["properties"]
    assert "HISTORIAL VISIBLE DEL MISMO CHAT" in provider.prompts[0]
    assert "EVIDENCIA ESCRITA POR EL JUGADOR" in provider.prompts[0]


def test_intent_interpreter_prompt_does_not_include_mechanics_or_character_stat_block():
    provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": _analysis_payload(),
    }))
    interpreter = IntentInterpreter(provider)

    interpreter.interpret(_context(), "Abro la puerta.")

    prompt = provider.prompts[0].casefold()
    assert "cd:" not in prompt
    assert "salvaciones competentes" not in prompt
    assert "ventaja" not in prompt
    assert prompt.count("Abro la puerta.") == 1


def test_intent_interpreter_keeps_player_evidence_and_reports_byte_budget_failure():
    provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": _analysis_payload(),
    }))
    interpreter = IntentInterpreter(
        provider,
        max_prompt_bytes=5000,
        max_context_bytes=512,
    )
    evidence = "Abro la puerta. " + ("evidencia " * 700)

    with pytest.raises(Exception, match="intent prompt exceeds byte budget"):
        interpreter.interpret(
            _context(),
            evidence,
            evidence_text=evidence,
        )

    assert provider.call_count == 0


def test_mechanics_adjudicator_uses_only_active_validated_step_and_mechanics_schema():
    provider = FakeLLMProvider(response=json.dumps({
        "decision": "skill_check",
        "skill": "athletics",
        "ability": "strength",
        "dc": 15,
        "advantage": False,
        "disadvantage": False,
        "modifier": 0,
        "reason": "Forzar una puerta bloqueada.",
    }))
    analysis_provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": _analysis_payload(),
    }))
    analysis = IntentInterpreter(analysis_provider).interpret(
        _context(),
        "Abro la puerta.",
    )
    adjudicator = MechanicsAdjudicator(provider)

    decision = adjudicator.adjudicate_analysis(_context(), analysis)

    assert decision.decision is MechanicsDecisionType.SKILL_CHECK
    assert decision.skill.value == "athletics"
    assert provider.call_count == 1
    assert MECHANICS_ONLY_RESPONSE_SCHEMA["required"] == ["decision"]
    assert "intent_analysis" not in MECHANICS_ONLY_RESPONSE_SCHEMA.get("properties", {})
    prompt = provider.prompts[0]
    assert "PASO ACTIVO VALIDADO" in prompt
    assert "Abro la puerta." in prompt
    assert "HISTORIAL RECIENTE" not in prompt
    assert "relation_claims" not in prompt


@pytest.mark.parametrize(
    "payload",
    [
        _analysis_payload(
            modality="observed",
            active_step_index=None,
        ),
        _analysis_payload(
            polarity="negative",
            active_step_index=None,
        ),
        _analysis_payload(
            modality="conditional",
            active_step_index=None,
            category="plan",
        ),
    ],
)
def test_mechanics_adjudicator_skips_non_actionable_interpretations(payload):
    intent_provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": payload,
    }))
    analysis = IntentInterpreter(intent_provider).interpret(
        _context(),
        "Abro la puerta.",
    )
    mechanics_provider = FakeLLMProvider(response='{"decision":"none"}')

    decision = MechanicsAdjudicator(mechanics_provider).adjudicate_analysis(
        _context(),
        analysis,
    )

    assert decision.decision is MechanicsDecisionType.NONE
    assert mechanics_provider.call_count == 0


def test_mechanics_adjudicator_skips_provider_without_active_character():
    intent_provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": _analysis_payload(),
    }))
    analysis = IntentInterpreter(intent_provider).interpret(
        _context(active_character=False),
        "Abro la puerta.",
    )
    mechanics_provider = FakeLLMProvider(response='{"decision":"none"}')

    decision = MechanicsAdjudicator(mechanics_provider).adjudicate_analysis(
        _context(active_character=False),
        analysis,
    )

    assert decision.decision is MechanicsDecisionType.NONE
    assert mechanics_provider.call_count == 0
