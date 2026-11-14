import json
from types import SimpleNamespace

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.entity import Entity
from models.mechanics import MechanicsDecisionType
from models.resolved_conversation_reference import ResolvedConversationReference
from models.resolved_world_reference import (
    ResolvedWorldReference,
    WorldReferenceCategory,
)
from models.session_state import SessionState
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.world_context_projection import (
    ContextProjectionDiagnostics,
    WorldContextProjection,
)
from models.world_state import WorldState
from services.providers import FakeLLMProvider
from services.turns import IntentInterpreter, MechanicsAdjudicator
from services.turns.intent_interpreter import IntentInterpreterError
from services.turns.intent_response_schema import (
    INTENT_ANALYSIS_RESPONSE_SCHEMA,
    INTENT_CORRECTION_RESPONSE_SCHEMA,
    MECHANICS_ONLY_RESPONSE_SCHEMA,
)


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
    source_excerpt="Abro la puerta.",
    action="abrir la puerta",
    predicate="Abro",
):
    return {
        "schema_version": 2,
        "category": category,
        "steps": [{
            "index": 0,
            "source_excerpt": source_excerpt,
            "actor": "player",
            "action": action,
            "modality": modality,
            "polarity": polarity,
            "reported_outcome": reported_outcome,
            "target_mentions": ["la puerta"],
            "attributed_to": None,
            "action_frame": {
                "predicate": predicate,
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


def test_intent_interpreter_attributes_visible_npc_quotes_from_recent_turns():
    context = _context()
    context.world.entities[77] = Entity(
        id=77,
        name="Aldric",
        entity_type="npc",
        active=True,
    )
    provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": {
            "schema_version": 2,
            "category": "dialogue",
            "steps": [{
                "index": 0,
                "source_excerpt": "Le digo que sí.",
                "actor": "player",
                "action": "responder afirmativamente",
                "modality": "dialogue",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": [],
                "attributed_to": None,
                "action_frame": {
                    "predicate": "digo",
                    "family": "communication",
                    "arguments": [],
                },
            }],
            "active_step_index": None,
            "requires_clarification": False,
            "clarification_question": None,
            "relation_claims": [],
        },
    }))
    recent_turns = [
        TurnRecord(
            id=12,
            player_input="Hablo con Aldric.",
            narrative='Aldric pregunta: «¿Vienes conmigo?»',
        )
    ]

    analysis = IntentInterpreter(provider).interpret(
        context,
        "Le digo que sí.",
        recent_turns=recent_turns,
    )

    assert analysis.category.value == "dialogue"
    assert "NPC Aldric (turno 12)" in provider.prompts[0]
    assert "¿Vienes conmigo?" in provider.prompts[0]
    assert "citas de npc visible etiquetadas" in provider.prompts[0].casefold()


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
    assert prompt.count("abro la puerta.") == 1


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

    with pytest.raises(IntentInterpreterError, match="intent prompt exceeds byte budget"):
        interpreter.interpret(
            _context(),
            evidence,
            evidence_text=evidence,
        )

    assert provider.call_count == 0


def test_mechanics_adjudicator_receives_only_active_step_resolved_references():
    player_text = "Abro la puerta con la llave."
    payload = _analysis_payload(
        source_excerpt=player_text,
        action="abrir la puerta con la llave",
        predicate="Abro",
    )
    payload["steps"][0]["target_mentions"] = ["la puerta", "la llave"]
    payload["steps"][0]["action_frame"]["arguments"].append({
        "role": "instrument",
        "mention": {
            "text": "la llave",
            "kind_hint": "item_instance",
        },
    })
    analysis_provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": payload,
    }))
    analysis = IntentInterpreter(analysis_provider).interpret(
        _context(),
        player_text,
    )
    provider = FakeLLMProvider(response=json.dumps({
        "decision": "skill_check",
        "skill": "athletics",
        "ability": "strength",
        "dc": 13,
        "reason": "La puerta se resiste.",
    }))
    resolved_entity = ResolvedConversationReference(
        mention="la puerta",
        entity_id=42,
        entity_name="Puerta de piedra",
        match_kind="explicit_alias",
        antecedent_turn_id=8,
    )
    resolved_item = ResolvedWorldReference(
        mention="la llave",
        category=WorldReferenceCategory.ITEM_INSTANCE,
        referent_id=73,
        name="Llave oxidada",
        match_kind="direct_name",
    )
    unrelated_entity = ResolvedConversationReference(
        mention="el guardia",
        entity_id=99,
        entity_name="Guardia del norte",
        match_kind="direct_name",
    )
    unrelated_item = ResolvedWorldReference(
        mention="el anillo",
        category=WorldReferenceCategory.ITEM_INSTANCE,
        referent_id=74,
        name="Anillo de plata",
        match_kind="direct_name",
    )

    decision = MechanicsAdjudicator(provider).adjudicate_analysis(
        _context(),
        analysis,
        resolved_references=(resolved_entity, unrelated_entity),
        resolved_world_references=(resolved_item, unrelated_item),
    )

    assert decision.decision is MechanicsDecisionType.SKILL_CHECK
    prompt = provider.prompts[0]
    assert "REFERENCIAS CANÓNICAS RESUELTAS POR EL BACKEND" in prompt
    assert '"canonical_id":42' in prompt
    assert '"canonical_id":73' in prompt
    assert '"canonical_name":"Puerta de piedra"' in prompt
    assert '"category":"item_instance"' in prompt
    assert '"canonical_id":99' not in prompt
    assert '"canonical_id":74' not in prompt


def test_mechanics_only_parser_applies_safe_defaults_for_optional_modifiers():
    provider = FakeLLMProvider(response=json.dumps({
        "decision": "ability_check",
        "ability": "strength",
        "dc": 12,
        "reason": "La pared carece de asideros.",
    }))
    analysis_provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": _analysis_payload(),
    }))
    analysis = IntentInterpreter(analysis_provider).interpret(
        _context(),
        "Abro la puerta.",
    )

    decision = MechanicsAdjudicator(provider).adjudicate_analysis(
        _context(),
        analysis,
    )

    assert decision.decision is MechanicsDecisionType.ABILITY_CHECK
    assert decision.advantage is False
    assert decision.disadvantage is False
    assert decision.situational_modifier == 0


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


def test_mechanics_adjudicator_skips_provider_when_interpreter_requests_clarification():
    payload = _analysis_payload()
    payload["active_step_index"] = None
    payload["requires_clarification"] = True
    payload["clarification_question"] = "¿A qué puerta te refieres?"
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


def _build_resolution_service(
    intent_provider,
    mechanics_provider,
    extractor,
    *,
    enable_context_projection=False,
):
    from services.context import ContextBuilder
    from services.turns import DMService
    from services.turns.turn_resolution_service import TurnResolutionService
    from services.world import WorldApplier, WorldService

    context_builder = ContextBuilder()
    intent_interpreter = IntentInterpreter(intent_provider, context_builder)
    mechanics_adjudicator = MechanicsAdjudicator(
        mechanics_provider,
        context_builder,
    )
    dm_service = DMService(
        FakeLLMProvider(response="La acción queda registrada."),
        context_builder,
    )
    return TurnResolutionService(
        dm_service=dm_service,
        extractor=extractor,
        world_service=WorldService(applier=WorldApplier()),
        mechanics_adjudicator=mechanics_adjudicator,
        intent_interpreter=intent_interpreter,
        context_builder=context_builder if enable_context_projection else None,
    )


def test_turn_pipeline_reuses_one_analysis_and_calls_mechanics_only_for_active_attempt():
    from services.llm_world import LLMWorldExtractor
    from services.llm_world.operation_parser import OperationParser

    class RecordingExtractor(LLMWorldExtractor):
        def __init__(self):
            super().__init__(
                provider=FakeLLMProvider(response='{"operations": []}'),
                operation_parser=OperationParser(),
            )
            self.received_analysis = None
            self.call_count = 0

        def propose(self, player_intent, context, **kwargs):
            self.call_count += 1
            self.received_analysis = kwargs["intent_analysis"]
            return []

    intent_provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": _analysis_payload(),
    }))
    mechanics_provider = FakeLLMProvider(response='{"decision":"none"}')
    extractor = RecordingExtractor()
    service = _build_resolution_service(
        intent_provider,
        mechanics_provider,
        extractor,
    )

    plan = service.prepare_turn(_context(), "Abro la puerta.")

    assert plan.intent_analysis is extractor.received_analysis
    assert intent_provider.call_count == 1
    assert mechanics_provider.call_count == 1
    assert extractor.call_count == 1


def test_turn_pipeline_skips_mechanics_for_completed_observation_but_keeps_proposal():
    from services.llm_world import LLMWorldExtractor
    from services.llm_world.operation_parser import OperationParser

    class RecordingExtractor(LLMWorldExtractor):
        def __init__(self):
            super().__init__(
                provider=FakeLLMProvider(response='{"operations": []}'),
                operation_parser=OperationParser(),
            )
            self.call_count = 0

        def propose(self, player_intent, context, **kwargs):
            self.call_count += 1
            assert kwargs["intent_analysis"].active_step_index is None
            return []

    observed = _analysis_payload(
        modality="observed",
        active_step_index=None,
        source_excerpt="Observo la puerta.",
        action="observar la puerta",
        predicate="Observo",
    )
    intent_provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": observed,
    }))
    mechanics_provider = FakeLLMProvider(response='{"decision":"none"}')
    extractor = RecordingExtractor()
    service = _build_resolution_service(
        intent_provider,
        mechanics_provider,
        extractor,
    )

    plan = service.prepare_turn(_context(), "Observo la puerta.")

    assert plan.intent_analysis.active_step_index is None
    assert intent_provider.call_count == 1
    assert mechanics_provider.call_count == 0
    assert extractor.call_count == 1


def test_ambiguous_reference_is_clarified_before_mechanics_or_proposal(monkeypatch):
    from services.llm_world import LLMWorldExtractor
    from services.llm_world.operation_parser import OperationParser

    class RecordingExtractor(LLMWorldExtractor):
        def __init__(self):
            super().__init__(
                provider=FakeLLMProvider(response='{"operations": []}'),
                operation_parser=OperationParser(),
            )
            self.call_count = 0

        def propose(self, player_intent, context, **kwargs):
            self.call_count += 1
            return []

    active_step = _analysis_payload(
        source_excerpt="Intento abrir la puerta.",
        action="intentar abrir la puerta",
        predicate="Intento",
    )
    intent_provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": active_step,
    }))
    mechanics_provider = FakeLLMProvider(response='{"decision":"none"}')
    extractor = RecordingExtractor()
    service = _build_resolution_service(
        intent_provider,
        mechanics_provider,
        extractor,
        enable_context_projection=True,
    )
    projection = WorldContextProjection(
        world=WorldState(),
        diagnostics=ContextProjectionDiagnostics(
            estimated_tokens=0,
            budget_tokens=4096,
            available_counts=(),
            candidate_counts=(),
            selected_counts=(),
        ),
    )
    monkeypatch.setattr(
        service.context_builder,
        "build_proposal_context",
        lambda *args, **kwargs: projection,
    )
    monkeypatch.setattr(
        service.conversation_reference_resolver,
        "resolve",
        lambda *args, **kwargs: SimpleNamespace(
            references=(),
            clarification_question="¿A qué puerta te refieres?",
        ),
    )

    plan = service.prepare_turn(
        _context(),
        "Intento abrir la puerta.",
    )

    assert plan.clarification_question == "¿A qué puerta te refieres?"
    assert mechanics_provider.call_count == 0
    assert extractor.call_count == 0


def test_turn_pipeline_skips_mechanics_and_proposal_for_question_only():
    from services.llm_world import LLMWorldExtractor
    from services.llm_world.operation_parser import OperationParser

    class RecordingExtractor(LLMWorldExtractor):
        def __init__(self):
            super().__init__(
                provider=FakeLLMProvider(response='{"operations": []}'),
                operation_parser=OperationParser(),
            )
            self.call_count = 0

        def propose(self, player_intent, context, **kwargs):
            self.call_count += 1
            return []

    question = _analysis_payload(
        modality="question",
        active_step_index=None,
        category="question",
        source_excerpt="¿Qué hay detrás de la puerta?",
        action="preguntar qué hay detrás de la puerta",
        predicate="hay",
    )
    intent_provider = FakeLLMProvider(response=json.dumps({
        "intent_analysis": question,
    }))
    mechanics_provider = FakeLLMProvider(response='{"decision":"none"}')
    extractor = RecordingExtractor()
    service = _build_resolution_service(
        intent_provider,
        mechanics_provider,
        extractor,
    )

    plan = service.prepare_turn(_context(), "¿Qué hay detrás de la puerta?")

    assert plan.intent_analysis.category.value == "question"
    assert intent_provider.call_count == 1
    assert mechanics_provider.call_count == 0
    assert extractor.call_count == 0


def test_intent_interpreter_pending_correction_is_independent_of_mechanics():
    original = "Entrego la llave de hierro a Mara."
    correction = "No, quería decir Aldric."
    conversation = (
        original
        + "\n\nAclaración del DM: ¿A quién entregas la llave?"
        + "\nRespuesta del jugador: "
        + correction
    )
    evidence = original + "\n" + correction
    pending_payload = {
        "schema_version": 2,
        "category": "action",
        "steps": [{
            "index": 0,
            "source_excerpt": original,
            "actor": "player",
            "action": "entregar la llave de hierro a Mara",
            "modality": "attempted",
            "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": ["la llave de hierro", "Mara"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "Entrego",
                "family": "transfer",
                "arguments": [
                    {
                        "role": "theme",
                        "mention": {
                            "text": "la llave de hierro",
                            "kind_hint": "item_instance",
                        },
                    },
                    {
                        "role": "recipient",
                        "mention": {
                            "text": "Mara",
                            "kind_hint": "character",
                        },
                    },
                ],
            },
        }],
        "active_step_index": 0,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }
    corrected_payload = {
        "schema_version": 2,
        "category": "action",
        "steps": [{
            "index": 0,
            "source_excerpt": evidence,
            "actor": "player",
            "action": "entregar la llave de hierro a Aldric",
            "modality": "attempted",
            "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": ["la llave de hierro", "Aldric"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "Entrego",
                "family": "transfer",
                "arguments": [
                    {
                        "role": "theme",
                        "mention": {
                            "text": "la llave de hierro",
                            "kind_hint": "item_instance",
                        },
                    },
                    {
                        "role": "recipient",
                        "mention": {
                            "text": "Aldric",
                            "kind_hint": "character",
                        },
                    },
                ],
            },
        }],
        "active_step_index": 0,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }
    correction_payload = {
        "step_index": 0,
        "slot": "target_mention",
        "previous_value": "Mara",
        "replacement": {"text": "Aldric", "kind_hint": "character"},
        "source_excerpt": correction,
        "argument_role": None,
        "relation_claim_index": None,
    }
    response = {
        "intent_analysis": corrected_payload,
        "pending_corrections": [correction_payload],
    }
    provider = FakeLLMProvider(response=json.dumps(response, ensure_ascii=False))
    interpreter = IntentInterpreter(provider)
    from models.player_intent_analysis import PlayerIntentAnalysis

    pending = PlayerIntentAnalysis.from_payload(
        pending_payload,
        source_text=original,
    )
    result = interpreter.understand_pending(
        _context(),
        conversation,
        pending_analysis=pending,
        correction_evidence_text=correction,
        evidence_text=evidence,
    )

    assert result.analysis.steps[0].target_mentions == ("la llave de hierro", "Aldric")
    assert len(result.corrections) == 1
    assert result.corrections[0].matches_analysis(result.analysis)
    assert provider.call_count == 1
    assert INTENT_CORRECTION_RESPONSE_SCHEMA["required"] == [
        "intent_analysis",
        "pending_corrections",
    ]
    assert "mechanics_decision" not in INTENT_CORRECTION_RESPONSE_SCHEMA["properties"]
    assert "INTERPRETACIÓN PENDIENTE" in provider.prompts[0]
    assert "mechanics_decision" not in provider.prompts[0]
