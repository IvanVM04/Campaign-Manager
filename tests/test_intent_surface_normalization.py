import json

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.providers import FakeLLMProvider
from services.turns.intent_interpreter import IntentInterpreter
from services.turns.intent_surface_normalization import normalize_intent_surface_payload


def _step(excerpt, *, actor="player", modality="attempted", outcome="not_claimed"):
    return {
        "index": 0,
        "source_excerpt": excerpt,
        "actor": actor,
        "action": "acción descrita",
        "modality": modality,
        "polarity": "positive",
        "reported_outcome": outcome,
        "target_mentions": [],
        "attributed_to": None,
    }


def _payload(*steps, category="action", active=0):
    return {
        "schema_version": 2,
        "category": category,
        "steps": list(steps),
        "active_step_index": active,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }


def test_explicit_direct_dm_question_cannot_remain_an_active_action():
    source = "¿Qué señales hay cerca de la puerta oriental?"
    payload = _payload(_step(source), active=0)

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "question"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["modality"] == "question"
    assert "explicit_direct_question" in summary.applied_rules


def test_explicit_player_speech_to_npc_is_dialogue_not_an_action():
    source = "Le pregunto a la capitana: «¿Quién custodia el archivo?»"
    payload = _payload(_step(source), active=0)

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "dialogue"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["actor"] == "player"
    assert normalized["steps"][0]["modality"] == "dialogue"
    assert "explicit_player_dialogue" in summary.applied_rules


def test_explicit_observation_before_follow_up_attempt_keeps_step_order():
    source = "Inspecciono el broche y luego intento abrir el estuche."
    first = _step("Inspecciono el broche")
    second = dict(
        _step("intento abrir el estuche"),
        index=1,
    )
    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second),
        evidence_text=source,
    )

    assert normalized["category"] == "mixed"
    assert normalized["active_step_index"] == 1
    assert normalized["steps"][0]["modality"] == "observed"
    assert normalized["steps"][1]["modality"] == "attempted"
    assert "explicit_observation_before_attempt" in summary.applied_rules


def test_explicit_conditional_future_is_normalized_to_a_plan():
    source = "Si la capitana da su visto bueno, me internaré en las catacumbas."
    payload = _payload(_step("me internaré en las catacumbas"))

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "plan"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["modality"] == "conditional"
    assert normalized["steps"][0]["source_excerpt"] == source
    assert "explicit_conditional_future" in summary.applied_rules


@pytest.mark.parametrize(
    "source",
    [
        "Intento trepar por la muralla, pero resbalo y caigo al foso.",
        "Pruebo la ganzúa en el candado, pero no gira y el cajón sigue cerrado.",
    ],
)
def test_explicit_failed_attempt_is_resolved_not_left_active(source):
    payload = _payload(_step(source[:source.index(", pero")]))

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["modality"] == "completed"
    assert normalized["steps"][0]["reported_outcome"] == "failure"
    assert normalized["steps"][0]["source_excerpt"] == source
    assert "explicit_attempt_failure_outcome" in summary.applied_rules


def test_failure_clause_split_from_its_attempt_is_collapsed_safely():
    source = "Intento trepar por la muralla, pero resbalo y caigo al foso."
    first = _step("Intento trepar por la muralla")
    second = dict(
        _step("resbalo y caigo al foso", modality="completed"),
        index=1,
    )
    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second),
        evidence_text=source,
    )

    assert len(normalized["steps"]) == 1
    assert normalized["steps"][0]["reported_outcome"] == "failure"
    assert normalized["active_step_index"] is None
    assert "explicit_attempt_failure_outcome" in summary.applied_rules


def test_named_reporter_is_preserved_inside_the_literal_step_excerpt():
    source = "Dorian me comenta que la pasarela quedó reparada al alba."
    payload = _payload(
        _step("que la pasarela quedó reparada al alba", actor="npc", modality="reported"),
        category="report",
        active=None,
    )

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    step = normalized["steps"][0]
    assert step["actor"] == "npc"
    assert step["modality"] == "reported"
    assert step["attributed_to"] == "Dorian"
    assert step["source_excerpt"] == source
    assert "explicit_reported_speaker" in summary.applied_rules


def test_unnamed_report_source_stays_uncertain_and_is_not_promoted_to_a_fact():
    source = (
        "Una exploradora comenta que halló huellas al sur, "
        "pero ignora si pertenecían a un lobo."
    )
    payload = _payload(
        _step("halló huellas al sur", actor="npc", modality="observed"),
        category="report",
        active=None,
    )

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    step = normalized["steps"][0]
    assert step["actor"] == "other"
    assert step["modality"] == "reported"
    assert step["polarity"] == "uncertain"
    assert step["attributed_to"] == "Una exploradora"
    assert normalized["active_step_index"] is None
    assert {"explicit_reported_speaker", "explicit_epistemic_uncertainty"}.issubset(
        set(summary.applied_rules)
    )


def test_explicit_suspicion_is_uncertain_and_not_actionable():
    source = (
        "Me parece sospechoso que la regente oculte un secreto; "
        "no dispongo de evidencias."
    )
    payload = _payload(_step(source), active=0)

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "report"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["polarity"] == "uncertain"
    assert normalized["steps"][0]["modality"] == "reported"
    assert "explicit_epistemic_uncertainty" in summary.applied_rules


def test_explicit_no_era_sino_correction_is_not_a_new_action():
    source = "No era el mapa viejo, sino el pergamino sellado."
    payload = _payload(_step(source), active=0)

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "correction"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["modality"] == "correction"
    assert "explicit_surface_correction" in summary.applied_rules


def test_simple_negation_and_unconditional_future_are_not_over_normalized():
    source = "No tomo la moneda que está junto al pozo."
    payload = _payload(_step(source))

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized == payload
    assert summary.applied_rules == ()


def test_interpreter_applies_conditional_normalization_before_domain_validation():
    source = "Si la capitana da su visto bueno, me internaré en las catacumbas."
    step = _step("me internaré en las catacumbas")
    step["action"] = "internarse en las catacumbas"
    step["action_frame"] = {
        "predicate": "internaré",
        "family": "movement",
        "arguments": [
            {
                "role": "destination",
                "mention": {"text": "las catacumbas", "kind_hint": "location"},
            }
        ],
    }
    response = json.dumps({"intent_analysis": _payload(step)}, ensure_ascii=False)
    provider = FakeLLMProvider(response=response)
    context = TurnContext(
        campaign=CampaignState(campaign_id=1, name="Test"),
        current_session=None,
        active_character=CharacterState(entity_id=20),
        world=WorldState(),
    )

    analysis = IntentInterpreter(provider).interpret(context, source)

    assert analysis.category.value == "plan"
    assert analysis.active_step_index is None
    assert analysis.steps[0].modality.value == "conditional"
