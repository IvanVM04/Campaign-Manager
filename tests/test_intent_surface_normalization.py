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


@pytest.mark.parametrize(
    ("source", "first_excerpt", "second_excerpt"),
    [
        (
            (
                "Una exploradora asegura que encontró señales al norte, "
                "aunque no recuerda si eran recientes."
            ),
            "encontró señales al norte",
            "aunque no recuerda si eran recientes",
        ),
        (
            (
                "Un cartógrafo afirma que la senda termina junto al río, "
                "pero ignora si el puente sigue en pie."
            ),
            "la senda termina junto al río",
            "pero ignora si el puente sigue en pie",
        ),
    ],
)
def test_reported_speaker_and_uncertainty_scope_across_split_steps(
    source, first_excerpt, second_excerpt
):
    first = _step(first_excerpt, actor="player", modality="attempted")
    second = dict(_step(second_excerpt, actor="player", modality="attempted"), index=1)

    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second, category="action", active=0),
        evidence_text=source,
    )

    assert normalized["category"] == "report"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["actor"] == "other"
    assert normalized["steps"][0]["modality"] == "reported"
    assert normalized["steps"][0]["polarity"] == "uncertain"
    assert normalized["steps"][0]["attributed_to"] in {
        "Una exploradora",
        "Un cartógrafo",
    }
    assert normalized["steps"][1]["actor"] == "other"
    assert normalized["steps"][1]["modality"] == "reported"
    assert normalized["steps"][1]["polarity"] == "uncertain"
    assert "explicit_reported_clause_uncertainty" in summary.applied_rules


def test_unsplit_report_plus_player_action_fails_closed_for_clarification():
    source = (
        "Un viajero asegura que vio un wyvern al este, "
        "aunque no sabe si era real, pero yo intento seguir el rastro."
    )
    step = _step(source, actor="player", modality="attempted")
    step["action_frame"] = {
        "predicate": "intento",
        "family": "movement",
        "arguments": [],
    }

    normalized, summary = normalize_intent_surface_payload(
        _payload(step, category="action", active=0),
        evidence_text=source,
    )

    assert normalized["category"] == "unknown"
    assert normalized["active_step_index"] is None
    assert normalized["requires_clarification"] is True
    assert normalized["clarification_question"]
    assert "reported_action_not_split_requires_clarification" in summary.applied_rules


def test_narrow_step_excerpt_spanning_report_and_action_fails_closed():
    source = (
        "Un viajero asegura que vio un wyvern al este, "
        "aunque no sabe si era real, pero yo intento seguir el rastro."
    )
    merged_excerpt = (
        "vio un wyvern al este, aunque no sabe si era real, "
        "pero yo intento seguir el rastro"
    )
    step = _step(merged_excerpt, actor="player", modality="attempted")
    step["action_frame"] = {
        "predicate": "intento",
        "family": "movement",
        "arguments": [],
    }
    payload = _payload(step, category="action", active=0)

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "unknown"
    assert normalized["active_step_index"] is None
    assert normalized["requires_clarification"] is True
    assert "reported_action_not_split_requires_clarification" in summary.applied_rules


def test_reported_clause_does_not_absorb_linked_same_sentence_player_attempt():
    source = (
        "Un viajero asegura que vio un wyvern al este, "
        "aunque no sabe si era real, pero yo intento seguir el rastro."
    )
    first = _step("vio un wyvern al este", actor="player", modality="attempted")
    second = dict(
        _step("aunque no sabe si era real", actor="player", modality="attempted"),
        index=1,
    )
    third = dict(
        _step("pero yo intento seguir el rastro", actor="player", modality="attempted"),
        index=2,
    )

    normalized, _ = normalize_intent_surface_payload(
        _payload(first, second, third, category="action", active=0),
        evidence_text=source,
    )

    assert normalized["category"] == "mixed"
    assert normalized["active_step_index"] == 2
    assert normalized["steps"][0]["actor"] == "other"
    assert normalized["steps"][0]["modality"] == "reported"
    assert normalized["steps"][0]["polarity"] == "uncertain"
    assert normalized["steps"][0]["attributed_to"] == "Un viajero"
    assert normalized["steps"][1]["actor"] == "other"
    assert normalized["steps"][1]["polarity"] == "uncertain"
    assert normalized["steps"][2]["actor"] == "player"
    assert normalized["steps"][2]["modality"] == "attempted"
    assert normalized["steps"][2]["polarity"] == "positive"
    assert "pero yo intento seguir el rastro" in normalized["steps"][2]["source_excerpt"]


def test_reported_uncertainty_does_not_capture_a_later_player_action():
    source = (
        "Una exploradora asegura que encontró señales al norte, "
        "aunque no recuerda si eran recientes. Después intento seguir el rastro."
    )
    first = _step("encontró señales al norte", actor="player", modality="attempted")
    second = dict(
        _step("aunque no recuerda si eran recientes", actor="player", modality="attempted"),
        index=1,
    )
    third = dict(
        _step("Después intento seguir el rastro", actor="player", modality="attempted"),
        index=2,
    )

    normalized, _ = normalize_intent_surface_payload(
        _payload(first, second, third, category="action", active=2),
        evidence_text=source,
    )

    assert normalized["category"] == "mixed"
    assert normalized["active_step_index"] == 2
    assert normalized["steps"][0]["attributed_to"] == "Una exploradora"
    assert normalized["steps"][0]["polarity"] == "uncertain"
    assert normalized["steps"][2]["actor"] == "player"
    assert normalized["steps"][2]["modality"] == "attempted"
    assert normalized["steps"][2]["polarity"] == "positive"


@pytest.mark.parametrize(
    "source",
    [
        "Decido no entrar en la fortaleza y permanezco fuera.",
        "He decidido no cruzar el puente y me quedo al exterior.",
    ],
)
def test_explicit_decision_not_to_act_absorbs_abstention_state(source):
    first = _step(source.split(" y ")[0], modality="attempted", outcome="uncertain")
    continuation_text = source.split(" y ", 1)[1]
    second = dict(
        _step(continuation_text, modality="attempted", outcome="uncertain"),
        index=1,
    )

    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second, category="action", active=1),
        evidence_text=source,
    )

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] is None
    assert len(normalized["steps"]) == 1
    assert normalized["steps"][0]["actor"] == "player"
    assert normalized["steps"][0]["modality"] == "negated"
    assert normalized["steps"][0]["polarity"] == "negative"
    assert normalized["steps"][0]["source_excerpt"] == source
    assert "explicit_decision_not_to_act" in summary.applied_rules
    assert "explicit_abstention_state_collapsed" in summary.applied_rules


def test_reported_npc_then_player_refusal_removes_only_abstention_state():
    source = (
        "Mara me cuenta que el puente está cerrado, "
        "pero decido no cruzar y permanezco en esta orilla."
    )
    first = _step(
        "el puente está cerrado",
        actor="npc",
        modality="reported",
    )
    second = dict(
        _step("pero decido no cruzar", modality="attempted"),
        index=1,
    )
    third = dict(
        _step("y permanezco en esta orilla", modality="attempted"),
        index=2,
    )

    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second, third, category="action", active=1),
        evidence_text=source,
    )

    assert normalized["category"] == "mixed"
    assert normalized["active_step_index"] is None
    assert len(normalized["steps"]) == 2
    assert normalized["steps"][0]["actor"] == "npc"
    assert normalized["steps"][0]["modality"] == "reported"
    assert normalized["steps"][0]["attributed_to"] == "Mara"
    assert normalized["steps"][1]["actor"] == "player"
    assert normalized["steps"][1]["modality"] == "negated"
    assert normalized["steps"][1]["polarity"] == "negative"
    assert "explicit_decision_not_to_act" in summary.applied_rules
    assert "explicit_abstention_state_collapsed" in summary.applied_rules


def test_explicit_decision_does_not_cancel_a_distinct_later_player_attempt():
    source = "Decido no entrar en la fortaleza y después intento abrir la puerta."
    first = _step("Decido no entrar en la fortaleza", modality="attempted")
    second = dict(
        _step("después intento abrir la puerta", modality="attempted"),
        index=1,
    )

    normalized, _ = normalize_intent_surface_payload(
        _payload(first, second, category="action", active=1),
        evidence_text=source,
    )

    assert normalized["category"] == "mixed"
    assert normalized["active_step_index"] == 1
    assert normalized["steps"][0]["modality"] == "negated"
    assert normalized["steps"][0]["polarity"] == "negative"
    assert normalized["steps"][1]["modality"] == "attempted"
    assert normalized["steps"][1]["polarity"] == "positive"


@pytest.mark.parametrize(
    "source",
    [
        "Prefiero no forzar el portón.",
        "No quiero cruzar el patio.",
        "No voy a entrar en la sala.",
        "Me niego a abrir el cofre.",
        "Me abstengo de entrar en la cripta.",
        "Desisto de buscar la llave.",
        "Cancelo mi intento de trepar por el muro.",
        "Abandono la idea de robar la bolsa.",
    ],
)
def test_explicit_refusal_and_abandoned_intent_are_non_actionable(source):
    normalized, summary = normalize_intent_surface_payload(
        _payload(_step(source, modality="attempted", outcome="uncertain")),
        evidence_text=source,
    )

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["actor"] == "player"
    assert normalized["steps"][0]["modality"] == "negated"
    assert normalized["steps"][0]["polarity"] == "negative"
    assert normalized["steps"][0]["reported_outcome"] == "not_claimed"
    assert "explicit_decision_not_to_act" in summary.applied_rules


def test_decision_language_inside_player_dialogue_is_not_a_player_intent():
    source = 'Le digo a Mara: «He decidido no entrar en la torre».'
    payload = _payload(_step(source), category="action", active=0)

    normalized, _ = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "dialogue"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["actor"] == "player"
    assert normalized["steps"][0]["modality"] == "dialogue"


def test_reported_negative_proposition_keeps_source_and_negative_polarity():
    source = "Un viajero asegura que no entró en la torre."
    payload = _payload(
        _step(
            "no entró en la torre",
            actor="other",
            modality="reported",
            outcome="not_claimed",
        ),
        category="report",
        active=None,
    )
    payload["steps"][0]["polarity"] = "negative"

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    step = normalized["steps"][0]
    assert normalized["category"] == "report"
    assert normalized["active_step_index"] is None
    assert step["actor"] == "other"
    assert step["modality"] == "reported"
    assert step["polarity"] == "negative"
    assert step["attributed_to"] == "Un viajero"
    assert "explicit_reported_speaker" in summary.applied_rules


def test_uncertainty_about_another_entity_does_not_taint_a_full_excerpt_attempt():
    source = "Intento abrir la puerta. Quizá el guardia se despierte."
    payload = _payload(
        _step(source, modality="attempted", outcome="uncertain"),
        category="action",
        active=0,
    )

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] == 0
    assert normalized["steps"][0]["modality"] == "attempted"
    assert normalized["steps"][0]["reported_outcome"] == "not_claimed"
    assert "explicit_epistemic_uncertainty" not in summary.applied_rules


def test_uncertainty_attached_to_attempt_result_is_preserved_with_narrow_excerpt():
    source = "Intento abrir la puerta, pero no sé si lo consigo."
    payload = _payload(
        _step("Intento abrir la puerta", modality="attempted", outcome="uncertain"),
        category="action",
        active=0,
    )

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] == 0
    assert normalized["steps"][0]["reported_outcome"] == "uncertain"
    assert "unreported_attempt_outcome" not in summary.applied_rules


@pytest.mark.parametrize(
    "source",
    [
        "No consigo abrir la puerta.",
        "No puedo abrir la puerta.",
        "No logro desbloquear el cofre.",
    ],
)
def test_direct_inability_to_complete_action_is_a_resolved_failure(source):
    payload = _payload(
        _step(source, modality="attempted", outcome="uncertain"),
        category="action",
        active=0,
    )

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["modality"] == "completed"
    assert normalized["steps"][0]["polarity"] == "positive"
    assert normalized["steps"][0]["reported_outcome"] == "failure"
    assert "explicit_attempt_failure_outcome" in summary.applied_rules


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
        (
            "Abro la ventana y luego intento salir al tejado.",
            "Abro la ventana",
            "luego intento salir al tejado",
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


@pytest.mark.parametrize("old_predicate", ["abrir", "llave"])
def test_explicit_object_correction_repairs_only_a_noncanonical_predicate(old_predicate):
    source = "No era la llave de hierro, sino la llave de cobre."
    step = _step(source, modality="attempted", outcome="uncertain")
    step["action_frame"] = {
        "predicate": old_predicate,
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



@pytest.mark.parametrize(
    "source",
    [
        "No quiero intentar abrir el cofre.",
        "No voy a intentar abrir el cofre.",
        "Me niego a intentar abrir el cofre.",
        "Intento no abrir la puerta.",
    ],
)
def test_explicitly_negated_attempt_is_not_made_actionable(source):
    payload = _payload(_step(source, modality="attempted", outcome="uncertain"))
    normalized, summary = normalize_intent_surface_payload(payload, evidence_text=source)

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["actor"] == "player"
    assert normalized["steps"][0]["modality"] == "negated"
    assert normalized["steps"][0]["polarity"] == "negative"
    assert normalized["steps"][0]["reported_outcome"] == "not_claimed"
    assert "explicit_negated_attempt" in summary.applied_rules


@pytest.mark.parametrize(
    "source",
    [
        "Intento abrir la puerta: no consigo mover el cerrojo.",
        "Intento encender la antorcha y no lo consigo.",
    ],
)
def test_explicit_failure_without_but_is_still_a_resolved_failure(source):
    payload = _payload(_step(source, modality="attempted", outcome="uncertain"))
    normalized, summary = normalize_intent_surface_payload(payload, evidence_text=source)

    assert normalized["steps"][0]["modality"] == "completed"
    assert normalized["steps"][0]["reported_outcome"] == "failure"
    assert normalized["active_step_index"] is None
    assert "explicit_attempt_failure_outcome" in summary.applied_rules


def test_interpreter_normalizes_completed_action_before_later_attempt():
    source = "Abro la ventana y luego intento salir al tejado."
    first = _step("Abro la ventana")
    first["action"] = "abrir la ventana"
    first["action_frame"] = {
        "predicate": "Abro",
        "family": "state_change",
        "arguments": [],
    }
    second = dict(
        _step("luego intento salir al tejado"),
        index=1,
    )
    second["action"] = "intentar salir al tejado"
    second["action_frame"] = {
        "predicate": "intento",
        "family": "movement",
        "arguments": [],
    }
    provider = FakeLLMProvider(
        response=json.dumps(
            {"intent_analysis": _payload(first, second, category="action", active=0)},
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

    assert analysis.category.value == "mixed"
    assert analysis.active_step_index == 1
    assert analysis.steps[0].modality.value == "completed"
    assert analysis.steps[0].reported_outcome.value == "success"
    assert analysis.steps[1].modality.value == "attempted"
    assert analysis.steps[1].reported_outcome.value == "not_claimed"
    assert analysis.is_actionable



def test_negative_polarity_on_an_attempt_is_not_overwritten():
    source = "Intento evitar abrir la puerta."
    payload = _payload(
        _step(source, modality="attempted", outcome="not_claimed"),
        category="action",
        active=0,
    )
    payload["steps"][0]["polarity"] = "negative"

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["steps"][0]["polarity"] == "negative"
    assert normalized["steps"][0]["reported_outcome"] == "not_claimed"
    assert "unreported_attempt_outcome" not in summary.applied_rules



def test_attempt_normalization_does_not_invent_an_active_step_pointer():
    source = "Intento accionar la palanca de bronce."
    payload = _payload(
        _step(source, modality="attempted", outcome="uncertain"),
        category="action",
        active=None,
    )

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["reported_outcome"] == "not_claimed"
    assert "unreported_attempt_outcome" in summary.applied_rules



def test_non_action_first_person_present_is_not_inferred_as_a_completed_step():
    source = "Me llamo Dorian y luego intento abrir la puerta."
    first = _step("Me llamo Dorian")
    second = dict(
        _step("intento abrir la puerta"),
        index=1,
    )

    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second, category="action", active=0),
        evidence_text=source,
    )

    assert normalized["steps"][0]["modality"] == "attempted"
    assert normalized["steps"][0]["reported_outcome"] == "not_claimed"
    assert normalized["active_step_index"] == 0
    assert "explicit_completed_action_before_attempt" not in summary.applied_rules


def test_negative_result_cannot_be_mistaken_for_explicit_success():
    source = "Intento encender la antorcha, pero no funciona."
    payload = _payload(_step(source, modality="attempted", outcome="uncertain"))

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["steps"][0]["modality"] == "completed"
    assert normalized["steps"][0]["reported_outcome"] == "failure"
    assert normalized["active_step_index"] is None
    assert "explicit_attempt_success_outcome" not in summary.applied_rules



def test_uncertainty_about_another_entity_does_not_contaminate_attempt_outcome():
    source = "Intento abrir la puerta. Quizá el guardia se despierte."
    payload = _payload(
        _step("Intento abrir la puerta", modality="attempted", outcome="uncertain"),
        category="action",
        active=0,
    )

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] == 0
    assert normalized["steps"][0]["reported_outcome"] == "not_claimed"
    assert "explicit_epistemic_uncertainty" not in summary.applied_rules


def test_uncertainty_about_another_entity_does_not_cancel_a_future_plan():
    source = "Mañana viajaré al puerto. Quizá el guardia despierte."
    payload = _payload(
        _step("Mañana viajaré al puerto"),
        category="action",
        active=0,
    )

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "plan"
    assert normalized["active_step_index"] is None
    assert normalized["steps"][0]["modality"] == "planned"
    assert "explicit_epistemic_uncertainty" not in summary.applied_rules



def test_interpreter_fails_closed_when_report_and_action_are_one_unsplit_step():
    source = (
        "Un viajero asegura que vio un wyvern al este, "
        "aunque no sabe si era real, pero yo intento seguir el rastro."
    )
    step = _step(source, actor="player", modality="attempted")
    step["action_frame"] = {
        "predicate": "intento",
        "family": "movement",
        "arguments": [],
    }
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

    assert analysis.category.value == "unknown"
    assert analysis.active_step_index is None
    assert analysis.requires_clarification
    assert not analysis.is_actionable
    assert not analysis.allows_world_proposal


def test_interpreter_keeps_later_player_attempt_after_uncertain_multi_step_report():
    source = (
        "Un explorador asegura que hay un campamento al norte, "
        "aunque no está seguro. Después intento acercarme al campamento."
    )
    first = _step("hay un campamento al norte", actor="other", modality="reported")
    first["action_frame"] = {
        "predicate": "hay",
        "family": "other",
        "arguments": [],
    }
    second = dict(
        _step("aunque no está seguro", actor="other", modality="reported"),
        index=1,
    )
    second["action_frame"] = {
        "predicate": "está",
        "family": "other",
        "arguments": [],
    }
    third = dict(
        _step(
            "Después intento acercarme al campamento",
            actor="player",
            modality="attempted",
        ),
        index=2,
    )
    third["action_frame"] = {
        "predicate": "intento",
        "family": "movement",
        "arguments": [],
    }
    provider = FakeLLMProvider(
        response=json.dumps(
            {
                "intent_analysis": _payload(
                    first,
                    second,
                    third,
                    category="action",
                    active=0,
                )
            },
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

    assert analysis.category.value == "mixed"
    assert analysis.active_step_index == 2
    assert analysis.steps[0].actor.value == "other"
    assert analysis.steps[0].modality.value == "reported"
    assert analysis.steps[0].polarity.value == "uncertain"
    assert analysis.steps[0].attributed_to == "Un explorador"
    assert analysis.steps[1].actor.value == "other"
    assert analysis.steps[1].polarity.value == "uncertain"
    assert analysis.steps[2].actor.value == "player"
    assert analysis.steps[2].modality.value == "attempted"
    assert analysis.steps[2].polarity.value == "positive"
    assert analysis.is_actionable
    assert analysis.allows_world_proposal


def test_interpreter_does_not_turn_an_uncertain_other_entity_into_reported_attempt():
    source = "Intento abrir la puerta. Quizá el guardia se despierte."
    step = _step(source, modality="attempted", outcome="uncertain")
    step["action_frame"] = {
        "predicate": "Intento",
        "family": "state_change",
        "arguments": [],
    }
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

    assert analysis.category.value == "action"
    assert analysis.active_step_index == 0
    assert analysis.steps[0].modality.value == "attempted"
    assert analysis.steps[0].reported_outcome.value == "not_claimed"
    assert analysis.is_actionable


def test_interpreter_keeps_npc_report_and_player_refusal_as_separate_resolved_steps():
    source = (
        "Mara me cuenta que el puente está cerrado, "
        "pero decido no cruzar y permanezco en esta orilla."
    )
    first = _step(
        "el puente está cerrado",
        actor="npc",
        modality="reported",
    )
    first["action_frame"] = {
        "predicate": "está",
        "family": "other",
        "arguments": [],
    }
    second = dict(
        _step("pero decido no cruzar", modality="attempted"),
        index=1,
    )
    second["action_frame"] = {
        "predicate": "cruzar",
        "family": "movement",
        "arguments": [],
    }
    third = dict(
        _step("y permanezco en esta orilla", modality="attempted"),
        index=2,
    )
    third["action_frame"] = {
        "predicate": "permanezco",
        "family": "movement",
        "arguments": [],
    }
    provider = FakeLLMProvider(
        response=json.dumps(
            {"intent_analysis": _payload(first, second, third, category="action", active=1)},
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

    assert analysis.category.value == "mixed"
    assert analysis.active_step_index is None
    assert len(analysis.steps) == 2
    assert analysis.steps[0].actor.value == "npc"
    assert analysis.steps[0].modality.value == "reported"
    assert analysis.steps[0].attributed_to == "Mara"
    assert analysis.steps[1].actor.value == "player"
    assert analysis.steps[1].modality.value == "negated"
    assert analysis.steps[1].polarity.value == "negative"
    assert not analysis.is_actionable


def test_interpreter_keeps_split_reported_uncertainty_non_factual():
    source = (
        "Un viajero asegura que vio un wyvern al este, "
        "aunque no sabe si era real."
    )
    first = _step("vio un wyvern al este", modality="attempted", outcome="uncertain")
    first["action_frame"] = {
        "predicate": "vio",
        "family": "other",
        "arguments": [],
    }
    second = dict(
        _step("aunque no sabe si era real", modality="attempted", outcome="uncertain"),
        index=1,
    )
    second["action_frame"] = {
        "predicate": "sabe",
        "family": "other",
        "arguments": [],
    }
    provider = FakeLLMProvider(
        response=json.dumps(
            {"intent_analysis": _payload(first, second, category="action", active=0)},
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
    assert analysis.steps[0].actor.value == "other"
    assert analysis.steps[0].modality.value == "reported"
    assert analysis.steps[0].polarity.value == "uncertain"
    assert analysis.steps[0].attributed_to == "Un viajero"
    assert not analysis.is_actionable
    assert not analysis.allows_world_proposal


def test_interpreter_keeps_explicit_abstention_non_actionable_when_model_splits_steps():
    source = "Decido no entrar en la fortaleza y permanezco fuera."
    first = _step(
        "Decido no entrar en la fortaleza",
        modality="attempted",
        outcome="uncertain",
    )
    first["action_frame"] = {
        "predicate": "entrar",
        "family": "movement",
        "arguments": [],
    }
    second = dict(
        _step("permanezco fuera.", modality="attempted", outcome="uncertain"),
        index=1,
    )
    second["action_frame"] = {
        "predicate": "permanezco",
        "family": "movement",
        "arguments": [],
    }
    provider = FakeLLMProvider(
        response=json.dumps(
            {"intent_analysis": _payload(first, second, category="action", active=1)},
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

    assert analysis.category.value == "action"
    assert analysis.active_step_index is None
    assert len(analysis.steps) == 1
    assert analysis.steps[0].modality.value == "negated"
    assert analysis.steps[0].polarity.value == "negative"
    assert not analysis.is_actionable
    assert not analysis.allows_world_proposal

def test_explicit_examining_clue_is_an_active_investigation_attempt():
    source = "Examino las huellas de barro que hay junto a la ventana."
    payload = _payload(_step(source, modality="observed", outcome="not_claimed"),
                       category="report", active=None)

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] == 0
    assert normalized["steps"][0]["actor"] == "player"
    assert normalized["steps"][0]["modality"] == "attempted"
    assert normalized["steps"][0]["reported_outcome"] == "not_claimed"
    assert "explicit_player_investigation_attempt" in summary.applied_rules


def test_split_uncertain_attempt_result_is_collapsed_without_losing_active_step():
    source = "Intento abrir el cofre, pero no sé si lo consigo."
    first = _step("Intento abrir el cofre")
    second = dict(_step("no sé si lo consigo", actor="other", modality="reported"), index=1)

    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second, category="mixed", active=0),
        evidence_text=source,
    )

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] == 0
    assert len(normalized["steps"]) == 1
    assert normalized["steps"][0]["source_excerpt"] == source
    assert normalized["steps"][0]["modality"] == "attempted"
    assert normalized["steps"][0]["reported_outcome"] == "uncertain"
    assert "split_attempt_uncertainty_collapsed" in summary.applied_rules


def test_split_failed_attempt_result_collapses_to_one_resolved_failure():
    source = "Pruebo la llave en la cerradura, pero no gira y el cofre sigue cerrado."
    first = _step("Pruebo la llave en la cerradura")
    second = dict(_step("el cofre sigue cerrado", actor="other", modality="reported"), index=1)

    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second, category="mixed", active=0),
        evidence_text=source,
    )

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] is None
    assert len(normalized["steps"]) == 1
    assert normalized["steps"][0]["source_excerpt"] == source
    assert normalized["steps"][0]["modality"] == "completed"
    assert normalized["steps"][0]["reported_outcome"] == "failure"
    assert "split_attempt_failure_collapsed" in summary.applied_rules


def test_reported_uncertainty_split_by_model_remains_one_attributed_claim():
    source = "Un viajero asegura que vio un wyvern al este, aunque no sabe si era real."
    first = _step(
        "vio un wyvern al este",
        actor="other",
        modality="reported",
        outcome="not_claimed",
    )
    second = dict(
        _step("no sabe si era real", actor="other", modality="reported"),
        index=1,
    )

    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second, category="report", active=None),
        evidence_text=source,
    )

    assert normalized["category"] == "report"
    assert normalized["active_step_index"] is None
    assert len(normalized["steps"]) == 1
    assert normalized["steps"][0]["source_excerpt"] == source
    assert normalized["steps"][0]["actor"] == "other"
    assert normalized["steps"][0]["modality"] == "reported"
    assert normalized["steps"][0]["polarity"] == "uncertain"
    assert normalized["steps"][0]["attributed_to"] == "Un viajero"
    assert "reported_uncertainty_steps_collapsed" in summary.applied_rules


def test_observed_third_party_action_keeps_npc_as_actor():
    source = "Veo a Aldric dejar una bolsa sobre la mesa."
    payload = _payload(_step(source, actor="player"), category="action", active=0)

    normalized, summary = normalize_intent_surface_payload(
        payload,
        evidence_text=source,
    )

    step = normalized["steps"][0]
    assert normalized["category"] == "report"
    assert normalized["active_step_index"] is None
    assert step["actor"] == "npc"
    assert step["modality"] == "observed"
    assert step["attributed_to"] == "Aldric"
    assert "explicit_observed_npc_action" in summary.applied_rules


def test_multi_npc_dialogue_steps_keep_independent_speakers_and_modality():
    source = "Mara pregunta por el mapa y Aldric responde que no lo ha visto."
    first = dict(_step("Mara pregunta por el mapa", actor="npc", modality="reported"), index=0)
    second = dict(
        _step("Aldric responde que no lo ha visto", actor="npc", modality="observed"),
        index=1,
    )

    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second, category="mixed", active=0),
        evidence_text=source,
    )

    assert normalized["category"] == "dialogue"
    assert normalized["active_step_index"] is None
    assert [step["actor"] for step in normalized["steps"]] == ["npc", "npc"]
    assert [step["modality"] for step in normalized["steps"]] == ["dialogue", "dialogue"]
    assert [step["attributed_to"] for step in normalized["steps"]] == ["Mara", "Aldric"]
    assert "explicit_npc_dialogue_step" in summary.applied_rules


def test_npc_dialogue_before_player_attempt_remains_a_mixed_turn():
    source = "Mara me advierte del peligro y yo intento retroceder hasta la puerta."
    first = dict(_step("Mara me advierte del peligro", actor="npc", modality="reported"), index=0)
    second = dict(
        _step("yo intento retroceder hasta la puerta", actor="player", modality="attempted"),
        index=1,
    )

    normalized, _summary = normalize_intent_surface_payload(
        _payload(first, second, category="action", active=1),
        evidence_text=source,
    )

    assert normalized["category"] == "mixed"
    assert normalized["active_step_index"] == 1
    assert normalized["steps"][0]["modality"] == "dialogue"
    assert normalized["steps"][0]["actor"] == "npc"
    assert normalized["steps"][1]["modality"] == "attempted"


def test_explicit_negation_before_a_new_player_attempt_is_one_action_sequence():
    source = "No abro la puerta; en cambio, intento levantar la reja."
    first = _step("No abro la puerta", actor="player", modality="observed")
    second = dict(
        _step("en cambio, intento levantar la reja", actor="player", modality="attempted"),
        index=1,
    )

    normalized, summary = normalize_intent_surface_payload(
        _payload(first, second, category="mixed", active=0),
        evidence_text=source,
    )

    assert normalized["category"] == "action"
    assert normalized["active_step_index"] == 1
    assert normalized["steps"][0]["modality"] == "negated"
    assert normalized["steps"][0]["polarity"] == "negative"
    assert normalized["steps"][1]["modality"] == "attempted"
    assert "explicit_negated_then_positive_player_action" in summary.applied_rules
