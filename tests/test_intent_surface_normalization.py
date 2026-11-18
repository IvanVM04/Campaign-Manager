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


@pytest.mark.parametrize("active", [7, True, -1, "0"])
def test_surface_normalization_does_not_hide_invalid_active_step_indices(active):
    source = "¿Qué ocurre en la biblioteca?"
    payload = _payload(_step(source), active=active)

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized == payload
    assert summary.applied_rules == ()


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



@pytest.mark.parametrize(
    "source",
    [
        "Intento sustraer discretamente la bolsa del mercader.",
        "Trepo por la escalera de cuerda hasta el balcón.",
        "Enciendo la antorcha con el pedernal que llevo.",
    ],
)
def test_attempt_without_reported_result_is_not_marked_uncertain(source):
    payload = _payload(
        _step(source, modality="attempted", outcome="uncertain"),
        category="action",
        active=0,
    )
    normalized, summary = normalize_intent_surface_payload(payload, evidence_text=source)
    assert normalized["category"] == "action"
    assert normalized["active_step_index"] == 0
    assert normalized["steps"][0]["modality"] == "attempted"
    assert normalized["steps"][0]["reported_outcome"] == "not_claimed"
    assert "unreported_attempt_outcome" in summary.applied_rules


def test_explicit_epistemic_uncertainty_is_not_erased_from_an_attempt():
    source = "Intento abrir la puerta, pero no sé si lo consigo."
    payload = _payload(
        _step(source, modality="attempted", outcome="uncertain"),
        category="action",
        active=0,
    )
    normalized, summary = normalize_intent_surface_payload(payload, evidence_text=source)
    assert normalized["steps"][0]["reported_outcome"] == "uncertain"
    assert "unreported_attempt_outcome" not in summary.applied_rules


@pytest.mark.parametrize(
    ("source", "expected_modality"),
    [
        ("Al amanecer viajaré desde el puerto hasta la fortaleza.", "planned"),
        ("Cuando termine la patrulla, hablaré con el capitán.", "planned"),
        ("Si Mara acepta acompañarme, entraré en la cripta.", "conditional"),
    ],
)
def test_future_intent_distinguishes_planned_from_conditional(source, expected_modality):
    payload = _payload(_step(source), category="action", active=0)
    normalized, summary = normalize_intent_surface_payload(payload, evidence_text=source)
    assert normalized["category"] == "plan"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["actor"] == "player"
    assert normalized["steps"][0]["modality"] == expected_modality
    assert normalized["steps"][0]["reported_outcome"] == "not_claimed"
    assert (
        "explicit_conditional_future" in summary.applied_rules
        if expected_modality == "conditional"
        else "explicit_first_person_future_plan" in summary.applied_rules
    )


def test_epistemically_uncertain_future_is_not_promoted_to_a_plan():
    source = "No sé si viajaré al amanecer."
    payload = _payload(_step(source), category="action", active=0)
    normalized, summary = normalize_intent_surface_payload(payload, evidence_text=source)
    assert normalized["category"] == "report"
    assert normalized["steps"][0]["polarity"] == "uncertain"
    assert "explicit_first_person_future_plan" not in summary.applied_rules


@pytest.mark.parametrize(
    "source",
    [
        "Observo tres huellas recientes bajo la ventana.",
        "Veo una luz azul al otro lado del río.",
    ],
)
def test_single_first_person_observation_is_reported_not_actionable(source):
    payload = _payload(
        _step(source, actor="other", modality="attempted", outcome="uncertain"),
        category="action",
        active=0,
    )
    normalized, summary = normalize_intent_surface_payload(payload, evidence_text=source)
    step = normalized["steps"][0]
    assert normalized["category"] == "report"
    assert normalized["active_step_index"] is None
    assert step["actor"] == "player"
    assert step["modality"] == "observed"
    assert step["polarity"] == "positive"
    assert step["reported_outcome"] == "not_claimed"
    assert "explicit_player_observation" in summary.applied_rules


@pytest.mark.parametrize(
    ("source", "first_excerpt", "second_excerpt"),
    [
        (
            "Abro la ventana y luego intento salir al tejado.",
            "Abro la ventana",
            "intento salir al tejado",
        ),
        (
            "Recojo la cuerda y después intento alcanzar el balcón.",
            "Recojo la cuerda",
            "intento alcanzar el balcón",
        ),
    ],
)
def test_completed_first_person_action_precedes_a_later_active_attempt(
    source, first_excerpt, second_excerpt
):
    first = _step(first_excerpt, modality="attempted", outcome="not_claimed")
    second = dict(
        _step(second_excerpt, modality="attempted", outcome="uncertain"),
        index=1,
    )
    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second, category="action", active=0),
        evidence_text=source,
    )
    assert normalized["category"] == "mixed"
    assert normalized["active_step_index"] == 1
    assert normalized["steps"][0]["modality"] == "completed"
    assert normalized["steps"][0]["reported_outcome"] == "success"
    assert normalized["steps"][1]["actor"] == "player"
    assert normalized["steps"][1]["modality"] == "attempted"
    assert normalized["steps"][1]["reported_outcome"] == "not_claimed"
    assert "explicit_completed_action_before_attempt" in summary.applied_rules


def test_explicit_object_correction_repairs_only_an_ungrounded_predicate():
    source = "No era la llave de hierro, sino la llave de cobre."
    step = _step(source, modality="attempted", outcome="uncertain")
    step["action_frame"] = {
        "predicate": "abrir",
        "family": "interaction",
        "arguments": [],
    }
    normalized, summary = normalize_intent_surface_payload(
        _payload(step, category="action", active=0),
        evidence_text=source,
    )
    assert normalized["category"] == "correction"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["modality"] == "correction"
    assert normalized["steps"][0]["source_excerpt"] == source
    assert normalized["steps"][0]["action_frame"]["predicate"] == "era"
    assert "literal_correction_predicate_repaired" in summary.applied_rules
    assert "explicit_surface_correction" in summary.applied_rules


def test_interpreter_normalizes_object_correction_before_strict_frame_validation():
    source = "No era la llave de hierro, sino la llave de cobre."
    step = _step(source)
    step["action"] = "corregir el objeto mencionado"
    step["action_frame"] = {"predicate": "abrir", "family": "interaction", "arguments": []}
    provider = FakeLLMProvider(
        response=json.dumps(
            {"intent_analysis": _payload(step, category="action", active=0)},
            ensure_ascii=False,
        )
    )
    context = TurnContext(
        campaign=CampaignState(campaign_id=1, name="Test"),
        current_session=None,
        active_character=CharacterState(entity_id=20),
        world=WorldState(),
    )
    analysis = IntentInterpreter(provider).interpret(context, source)
    assert analysis.category.value == "correction"
    assert analysis.active_step_index is None
    assert analysis.steps[0].action_frame.predicate == "era"


def test_interpreter_normalizes_single_observation_before_strict_active_step_validation():
    source = "Observo tres huellas recientes bajo la ventana."
    step = _step(source, actor="other", modality="attempted", outcome="uncertain")
    step["action"] = "observar tres huellas"
    step["action_frame"] = {"predicate": "Observo", "family": "perception", "arguments": []}
    provider = FakeLLMProvider(
        response=json.dumps(
            {"intent_analysis": _payload(step, category="action", active=0)},
            ensure_ascii=False,
        )
    )
    context = TurnContext(
        campaign=CampaignState(campaign_id=1, name="Test"),
        current_session=None,
        active_character=CharacterState(entity_id=20),
        world=WorldState(),
    )
    analysis = IntentInterpreter(provider).interpret(context, source)
    assert analysis.category.value == "report"
    assert analysis.active_step_index is None
    assert analysis.steps[0].actor.value == "player"
    assert analysis.steps[0].modality.value == "observed"
    assert analysis.steps[0].reported_outcome.value == "not_claimed"
