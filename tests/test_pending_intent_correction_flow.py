"""End-to-end contracts for typed corrections during durable clarifications."""

import json

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.mechanics import MechanicsDecision, MechanicsDecisionType
from models.pending_intent_correction import (
    PendingCorrectionSlot,
    PendingIntentCorrection,
)
from models.player_intent_analysis import PlayerIntentAnalysis
from models.semantic_frames import SemanticMention, SemanticObjectKind
from models.session_state import SessionState
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.providers import FakeLLMProvider
from services.turns.durable_native_turn_service import DurableNativeTurnError
from services.turns.intent_response_schema import (
    INTENT_MECHANICS_CORRECTION_RESPONSE_SCHEMA,
    INTENT_MECHANICS_RESPONSE_SCHEMA,
)
from services.turns.mechanics_adjudicator import (
    IntentUnderstandingResult,
    MechanicsAdjudicator,
    MechanicsAdjudicatorError,
)
from services.turns.turn_resolution_service import (
    TurnResolutionPlan,
    TurnResolutionServiceError,
)
from tests.durable_turn_test_support import service_with_fake_models

ORIGINAL = "Entrego la llave de hierro a Mara."
CORRECTION = "No, quería decir Aldric."
SECOND_ANSWER = "La destinataria sigue siendo Aldric."


def _pending_analysis() -> PlayerIntentAnalysis:
    payload = {
        "schema_version": 2,
        "category": "action",
        "steps": [{
            "index": 0,
            "source_excerpt": ORIGINAL,
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
                        "mention": {"text": "Mara", "kind_hint": "character"},
                    },
                ],
            },
        }],
        "active_step_index": 0,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }
    return PlayerIntentAnalysis.from_payload(payload, source_text=ORIGINAL)


def _corrected_analysis(evidence: str) -> PlayerIntentAnalysis:
    excerpt = evidence
    payload = {
        "schema_version": 2,
        "category": "action",
        "steps": [{
            "index": 0,
            "source_excerpt": excerpt,
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
                        "mention": {"text": "Aldric", "kind_hint": "character"},
                    },
                ],
            },
        }],
        "active_step_index": 0,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }
    return PlayerIntentAnalysis.from_payload(
        payload,
        source_text=evidence,
        evidence_text=evidence,
    )


def _correction_payload() -> dict:
    return {
        "step_index": 0,
        "slot": "target_mention",
        "previous_value": "Mara",
        "replacement": {"text": "Aldric", "kind_hint": "character"},
        "source_excerpt": CORRECTION,
        "argument_role": None,
        "relation_claim_index": None,
    }


def _correction() -> PendingIntentCorrection:
    return PendingIntentCorrection.from_payload(
        _correction_payload(),
        evidence_text=CORRECTION,
    )


def _turn_context() -> TurnContext:
    return TurnContext(
        campaign=CampaignState(campaign_id=1, name="Corrections"),
        current_session=SessionState(session_id=1, number=1, title="Test"),
        active_character=CharacterState(entity_id=20),
        world=WorldState(),
    )


def test_correction_payload_is_strict_and_round_trips_to_a_typed_value():
    correction = _correction()

    assert correction.slot is PendingCorrectionSlot.TARGET_MENTION
    assert correction.replacement == SemanticMention(
        "Aldric", SemanticObjectKind.CHARACTER
    )
    assert correction.to_dict() == _correction_payload()

    extra = _correction_payload()
    extra["canonical_entity_id"] = 123
    try:
        PendingIntentCorrection.from_payload(extra, evidence_text=CORRECTION)
    except ValueError as exc:
        assert "unexpected fields" in str(exc)
    else:
        raise AssertionError("unexpected correction fields were accepted")

    ungrounded = _correction_payload()
    ungrounded["replacement"] = {
        "text": "Bram",
        "kind_hint": "character",
    }
    try:
        PendingIntentCorrection.from_payload(
            ungrounded,
            evidence_text=CORRECTION,
        )
    except ValueError as exc:
        assert "literal player evidence" in str(exc)
    else:
        raise AssertionError("ungrounded replacement was accepted")


def test_correction_matches_and_applies_only_to_the_pending_analysis():
    pending = _pending_analysis()
    evidence = ORIGINAL + "\n\n" + CORRECTION
    updated = _correction().apply(
        pending,
        player_evidence_text=evidence,
        resolution_pending=True,
        committed=False,
    )

    assert _correction().matches_analysis(updated)
    assert not _correction().matches_analysis(pending)
    assert updated.steps[0].target_mentions == ("la llave de hierro", "Aldric")
    assert pending.steps[0].target_mentions == ("la llave de hierro", "Mara")


def test_pending_adjudication_uses_correction_schema_and_returns_validated_edits(
    monkeypatch,
):
    pending = _pending_analysis()
    evidence = ORIGINAL + "\n\n" + CORRECTION
    conversation = (
        ORIGINAL
        + "\n\nAclaración del DM: ¿A quién entregas la llave?"
        + "\nRespuesta del jugador: "
        + CORRECTION
    )
    response = json.dumps({
        "intent_analysis": _corrected_analysis(evidence).to_dict(),
        "mechanics_decision": {"decision": "none"},
        "pending_corrections": [_correction_payload()],
    })
    provider = FakeLLMProvider(response=response)
    captured = {}
    original_generate = provider.generate

    def generate_structured(prompt, *, schema):
        captured["prompt"] = prompt
        captured["schema"] = schema
        return original_generate(prompt)

    monkeypatch.setattr(provider, "generate_structured", generate_structured)
    result = MechanicsAdjudicator(provider).understand_pending(
        _turn_context(),
        conversation,
        pending_analysis=pending,
        correction_evidence_text=CORRECTION,
        evidence_text=evidence,
    )

    assert isinstance(result, IntentUnderstandingResult)
    assert result.analysis.steps[0].target_mentions[-1] == "Aldric"
    assert result.mechanics_decision.decision is MechanicsDecisionType.NONE
    assert len(result.corrections) == 1
    assert result.corrections[0].matches_analysis(result.analysis)
    assert captured["schema"] is INTENT_MECHANICS_CORRECTION_RESPONSE_SCHEMA
    assert "pending_corrections" in captured["schema"]["required"]
    assert "INTERPRETACIÓN ANTERIOR PENDIENTE" in captured["prompt"]
    assert CORRECTION in captured["prompt"]
    assert provider.call_count == 1
    assert "pending_corrections" not in INTENT_MECHANICS_RESPONSE_SCHEMA["properties"]


def test_pending_adjudication_rejects_corrections_not_reflected_by_reanalysis(
    monkeypatch,
):
    pending = _pending_analysis()
    evidence = ORIGINAL + "\n\n" + CORRECTION
    conversation = ORIGINAL + "\n\n" + CORRECTION
    unchanged = pending.to_dict()
    response = json.dumps({
        "intent_analysis": unchanged,
        "mechanics_decision": {"decision": "none"},
        "pending_corrections": [_correction_payload()],
    })
    provider = FakeLLMProvider(response=response)
    original_generate = provider.generate
    monkeypatch.setattr(
        provider,
        "generate_structured",
        lambda prompt, *, schema: original_generate(prompt),
    )

    with pytest.raises(
        MechanicsAdjudicatorError,
        match="does not reflect its explicit correction",
    ):
        MechanicsAdjudicator(provider).understand_pending(
            _turn_context(),
            conversation,
            pending_analysis=pending,
            correction_evidence_text=CORRECTION,
            evidence_text=evidence,
        )


def test_durable_clarification_persists_correction_audit_across_multiple_rounds(
    monkeypatch,
):
    service, _proposal_calls, _narrative_calls = service_with_fake_models()
    pending = _pending_analysis()
    evidence_after_first = ORIGINAL + "\n\n" + CORRECTION
    updated = _corrected_analysis(evidence_after_first)
    correction = _correction()
    calls = []

    def prepare_turn(_context, player_input, **kwargs):
        calls.append((player_input, kwargs))
        if len(calls) == 1:
            return TurnResolutionPlan(
                player_input=player_input,
                narrative="¿A quién entregas la llave?",
                world_operations=(),
                character_operations=(),
                ordered_operations=(),
                clarification_question="¿A quién entregas la llave?",
                intent_analysis=pending,
                intent_evidence_text=ORIGINAL,
            )
        if len(calls) == 2:
            assert kwargs["pending_intent_analysis"] == pending
            assert kwargs["pending_correction_evidence_text"] == CORRECTION
            return TurnResolutionPlan(
                player_input=player_input,
                narrative="¿Confirmas la destinataria?",
                world_operations=(),
                character_operations=(),
                ordered_operations=(),
                clarification_question="¿Confirmas la destinataria?",
                intent_analysis=updated,
                intent_evidence_text=evidence_after_first,
                intent_corrections=(correction,),
            )
        assert len(calls) == 3
        assert kwargs["pending_intent_analysis"] == updated
        assert kwargs["pending_correction_evidence_text"] == SECOND_ANSWER
        cumulative = evidence_after_first + "\n\n" + SECOND_ANSWER
        return TurnResolutionPlan(
            player_input=player_input,
            narrative="La entrega queda preparada.",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
            intent_analysis=updated,
            intent_evidence_text=cumulative,
        )

    monkeypatch.setattr(service.resolver, "prepare_turn", prepare_turn)
    # The durable service refuses a stored semantic draft when the shared
    # adjudicator is absent. The stub is only a capability marker here because
    # prepare_turn is replaced to inspect the durable hand-off.
    service.resolver.mechanics_adjudicator = object()

    first = service.play_turn(
        ORIGINAL,
        idempotency_key="pending-correction-multi-round-001",
    )
    second = service.submit_clarification(first.pending_clarification_id, CORRECTION)
    assert second.pending_clarification_id
    third = service.submit_clarification(
        second.pending_clarification_id,
        SECOND_ANSWER,
    )

    assert third.narrative == "El personaje observa su entorno."
    assert len(calls) == 3
    resolution_id = int(first.pending_clarification_id.split(":", 1)[0])
    record = service.resolution_repository.get(
        resolution_id,
        scope=service.scope,
    )
    assert record is not None
    state = json.loads(record.adjudication_json)
    assert state["intent_correction_history"] == [correction.to_dict()]
    assert state["clarification_history"] == [
        {
            "question": "¿A quién entregas la llave?",
            "answer": CORRECTION,
        },
        {
            "question": "¿Confirmas la destinataria?",
            "answer": SECOND_ANSWER,
        },
    ]
    assert record.player_input == ORIGINAL

    with pytest.raises(
        DurableNativeTurnError,
        match="clarification request is no longer pending",
    ):
        service.submit_clarification(
            second.pending_clarification_id,
            "Corrijo otra vez después de confirmar la entrega.",
        )


def test_failed_correction_releases_claim_back_to_awaiting_input(monkeypatch):
    service, _proposal_calls, _narrative_calls = service_with_fake_models()
    service.resolver.mechanics_adjudicator = object()
    pending = _pending_analysis()
    attempts = []

    def fail_after_claim(_context, player_input, **kwargs):
        attempts.append((player_input, kwargs))
        if len(attempts) == 1:
            return TurnResolutionPlan(
                player_input=player_input,
                narrative="¿A quién entregas la llave?",
                world_operations=(),
                character_operations=(),
                ordered_operations=(),
                clarification_question="¿A quién entregas la llave?",
                intent_analysis=pending,
                intent_evidence_text=ORIGINAL,
            )
        raise RuntimeError("simulated correction provider failure")

    monkeypatch.setattr(service.resolver, "prepare_turn", fail_after_claim)
    first = service.play_turn(
        ORIGINAL,
        idempotency_key="pending-correction-release-lease-001",
    )

    with pytest.raises(
        DurableNativeTurnError,
        match="clarification resolution failed",
    ):
        service.submit_clarification(
            first.pending_clarification_id,
            CORRECTION,
        )

    resolution_id = int(first.pending_clarification_id.split(":", 1)[0])
    saved = service.resolution_repository.get(resolution_id, scope=service.scope)
    assert saved is not None
    assert saved.lifecycle_state == "awaiting_input"
    assert saved.lease_token is None
    assert saved.lease_expires_at is None
    assert saved.last_error_code == "clarification_resolution_failed"

def test_turn_planner_requires_correction_to_match_the_provider_reanalysis():
    service, _proposal_calls, _narrative_calls = service_with_fake_models()
    pending = _pending_analysis()
    updated = _corrected_analysis(ORIGINAL + "\n\n" + CORRECTION)
    correction = _correction()
    service.resolver.context_builder = None

    class FakeAdjudicator:
        def understand_pending(self, *args: object, **kwargs: object) -> IntentUnderstandingResult:
            return IntentUnderstandingResult(
                analysis=pending,
                mechanics_decision=MechanicsDecision(MechanicsDecisionType.NONE),
                corrections=(correction,),
            )

    # A malformed adjudicator result must be rejected before proposal extraction.
    service.resolver.mechanics_adjudicator = FakeAdjudicator()
    with pytest.raises(
        TurnResolutionServiceError,
        match="pending intent correction failed validation",
    ):
        service.resolver.prepare_turn(
            _turn_context(),
            ORIGINAL + "\n\nAclaración del DM: ¿A quién?\n" + CORRECTION,
            intent_evidence_text=ORIGINAL + "\n\n" + CORRECTION,
            pending_intent_analysis=pending,
            pending_correction_evidence_text=CORRECTION,
        )

    class ConsistentAdjudicator:
        def understand_pending(self, *args, **kwargs):
            assert kwargs["pending_analysis"] == pending
            assert kwargs["correction_evidence_text"] == CORRECTION
            return IntentUnderstandingResult(
                analysis=updated,
                mechanics_decision=MechanicsDecision(MechanicsDecisionType.NONE),
                corrections=(correction,),
            )

    service.resolver.mechanics_adjudicator = ConsistentAdjudicator()
    plan = service.resolver.prepare_turn(
        _turn_context(),
        ORIGINAL + "\n\nAclaración del DM: ¿A quién?\n" + CORRECTION,
        intent_evidence_text=ORIGINAL + "\n\n" + CORRECTION,
        pending_intent_analysis=pending,
        pending_correction_evidence_text=CORRECTION,
    )
    assert plan.intent_analysis == updated
    assert plan.intent_corrections == (correction,)
