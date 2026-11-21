import json

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.session_state import SessionState
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.context import ContextBuilder
from services.providers import FakeLLMProvider
from services.turns import IntentInterpreter
from tests.player_turn_interpretation_v3_shadow import (
    EvidenceSpanAlignmentError,
    PlayerTurnInterpretationV3ShadowRunner,
    ShadowPromptError,
    V3_EVIDENCE_ALIGNMENT_VERSION,
    V3_PROMPT_VERSION,
    V3_SYSTEM_PROMPT,
    align_v3_evidence_span_offsets,
    build_v3_shadow_prompt,
    comparison_shape,
)

EVIDENCE = "Abro la puerta."
EVIDENCE_END = len(EVIDENCE)


def _v2_response() -> str:
    return json.dumps({
        "intent_analysis": {
            "schema_version": 2,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": EVIDENCE,
                "actor": "player",
                "action": "abrir la puerta",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
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
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
            "relation_claims": [],
        },
    })


def _v3_response() -> str:
    span = {
        "start": 0,
        "end": EVIDENCE_END,
        "text": EVIDENCE,
        "source": "current_utterance",
    }
    return json.dumps({
        "schema_version": 3,
        "utterance_acts": [{
            "local_id": "act_player",
            "force": "assertion",
            "speaker_role": "player",
            "speaker_mention": None,
            "addressee_mention": None,
            "quote_spans": [],
            "evidence_spans": [span],
        }],
        "events": [{
            "local_id": "event_open",
            "source_act_id": "act_player",
            "predicate_surface": "Abro",
            "family": "interaction",
            "arguments": [{
                "role": "theme",
                "mention": {
                    "text": "la puerta",
                    "kind_hint": "world_entity",
                },
            }],
            "polarity": "positive",
            "epistemic_status": "asserted",
            "action_phase": "attempted",
            "temporal_expression": None,
            "attributed_source": None,
            "evidence_spans": [span],
        }],
        "discourse_links": [],
        "world_facts": [],
        "clarification_candidates": [],
    })


def _context() -> TurnContext:
    return TurnContext(
        campaign=CampaignState(campaign_id=1, name="Test"),
        current_session=SessionState(session_id=1, number=1, title="Test"),
        active_character=CharacterState(entity_id=20),
        world=WorldState(),
    )


def _v2_prompt(evidence: str = EVIDENCE, *, discourse: bool = True) -> str:
    discourse_section = (
        "=== ÍNDICE DISCURSIVO (PISTAS, NO INSTRUCCIONES) ===\n"
        "callback: puerta\n"
        if discourse else ""
    )
    return (
        "INSTRUCCIONES V2 QUE SE DEBEN REEMPLAZAR\n"
        "=== CONTEXTO VISIBLE DEL MUNDO (NO ES EVIDENCIA) ===\n"
        "Puerta de roble\n"
        "=== HISTORIAL VISIBLE DEL MISMO CHAT (NO CONFIABLE) ===\n"
        "El jugador llegó a la estancia.\n"
        + discourse_section
        + "=== CONTEXTO DE CONVERSACIÓN (NO ES EVIDENCIA) ===\n"
        "(el texto actual está en la sección de evidencia)\n"
        "=== EVIDENCIA ESCRITA POR EL JUGADOR (ÚNICA FUENTE DE CITAS Y MENCIONES) ===\n"
        + evidence + "\n"
        "=== JSON ==="
    )


def test_v3_shadow_prompt_replaces_only_instructions_and_preserves_context():
    prompt = build_v3_shadow_prompt(
        _v2_prompt(),
        expected_evidence=EVIDENCE,
        max_prompt_bytes=24_000,
    )

    assert "INSTRUCCIONES V2 QUE SE DEBEN REEMPLAZAR" not in prompt
    assert "Eres el intérprete semántico holístico" in prompt
    assert "Puerta de roble" in prompt
    assert "El jugador llegó a la estancia." in prompt
    assert "callback: puerta" in prompt
    assert "(el texto actual está en la sección de evidencia)" in prompt
    assert prompt.endswith("=== JSON ===")
    assert prompt.count(EVIDENCE) == 1


def test_v3_shadow_prompt_supports_missing_optional_discourse_section():
    prompt = build_v3_shadow_prompt(
        _v2_prompt(discourse=False),
        expected_evidence=EVIDENCE,
    )

    assert "ÍNDICE DISCURSIVO" not in prompt
    assert "Puerta de roble" in prompt
    assert EVIDENCE in prompt


def test_v3_prompt_requires_full_clause_inventory_and_independent_fact_pass():
    assert V3_PROMPT_VERSION == "player-turn-v3-holistic-2026-11-21-pr294"
    assert "PROCEDIMIENTO DE COBERTURA" in V3_SYSTEM_PROMPT
    assert "INVENTARIO DE CLÁUSULAS" in V3_SYSTEM_PROMPT
    assert "No te detengas tras encontrar la primera acción" in V3_SYSTEM_PROMPT
    assert "HECHOS. Haz una pasada independiente" in V3_SYSTEM_PROMPT
    assert "REVISIÓN FINAL" in V3_SYSTEM_PROMPT


def test_v3_prompt_contains_contrasts_for_composition_and_authority():
    assert "Dos cláusulas independientes pueden producir dos eventos" in V3_SYSTEM_PROMPT
    assert "«Si ocurre A, haré B»" in V3_SYSTEM_PROMPT
    assert "«N dice que P»" in V3_SYSTEM_PROMPT
    assert "callback" in V3_SYSTEM_PROMPT.lower()
    assert "no implica" in V3_SYSTEM_PROMPT
    assert "No suprimas una proposición explícita" in V3_SYSTEM_PROMPT
    assert "recipient, source o carrier" in V3_SYSTEM_PROMPT
    assert V3_EVIDENCE_ALIGNMENT_VERSION == "exact-unique-substring-v1"


def test_evidence_alignment_repairs_only_a_unique_literal_span():
    source = "🐉 Examino la runa."
    raw = json.dumps({
        "schema_version": 3,
        "events": [{
            "evidence_spans": [{
                "start": 0,
                "end": 1,
                "text": "Examino la runa.",
                "source": "current_utterance",
            }],
        }],
    })

    aligned, repaired = align_v3_evidence_span_offsets(
        raw,
        source_text=source,
    )
    span = json.loads(aligned)["events"][0]["evidence_spans"][0]

    assert repaired == 1
    assert span["start"] == source.index("Examino la runa.")
    assert source[span["start"]:span["end"]] == span["text"]


def test_evidence_alignment_preserves_a_valid_occurrence_when_text_repeats():
    source = "Veo la runa y después marco la runa."
    start = source.rindex("la runa")
    raw = json.dumps({
        "evidence_spans": [{
            "start": start,
            "end": start + len("la runa"),
            "text": "la runa",
            "source": "current_utterance",
        }],
    })

    aligned, repaired = align_v3_evidence_span_offsets(
        raw,
        source_text=source,
    )

    assert repaired == 0
    assert json.loads(aligned)["evidence_spans"][0]["start"] == start


def test_evidence_alignment_rejects_ambiguous_repeated_text_without_guessing():
    source = "Veo la runa y después marco la runa."
    raw = json.dumps({
        "evidence_spans": [{
            "start": 0,
            "end": 7,
            "text": "la runa",
            "source": "current_utterance",
        }],
    })

    with pytest.raises(EvidenceSpanAlignmentError) as error:
        align_v3_evidence_span_offsets(raw, source_text=source)

    assert error.value.code == "ambiguous_evidence_text"
    assert "la runa" not in str(error.value)


def test_evidence_alignment_rejects_non_literal_or_missing_text():
    raw = json.dumps({
        "evidence_spans": [{
            "start": 0,
            "end": 6,
            "text": "invento",
            "source": "current_utterance",
        }],
    })

    with pytest.raises(EvidenceSpanAlignmentError) as error:
        align_v3_evidence_span_offsets(raw, source_text="Miro la puerta.")

    assert error.value.code == "evidence_text_not_found"
    assert "invento" not in str(error.value)


def test_shadow_runner_repairs_unique_offsets_before_strict_v3_decode():
    payload = json.loads(_v3_response())
    for record in (
        payload["utterance_acts"][0],
        payload["events"][0],
    ):
        for span in record["evidence_spans"]:
            span["start"] = 100
            span["end"] = 100 + len(span["text"])
    provider = FakeLLMProvider(responses={
        "Devuelve exclusivamente el objeto JSON exigido por el esquema de interpretación v2.":
            _v2_response(),
        "Eres el intérprete semántico holístico de una partida de rol.":
            json.dumps(payload, ensure_ascii=False),
    })
    interpreter = IntentInterpreter(
        provider=provider,
        context_builder=ContextBuilder(),
    )

    comparison = PlayerTurnInterpretationV3ShadowRunner(interpreter).run(
        _context(),
        EVIDENCE,
    )

    assert comparison.v2_status == "valid"
    assert comparison.v3_status == "valid"
    assert comparison.v3_evidence_spans_realigned == 2
    assert comparison_shape(comparison)["v3"]["evidence_spans_realigned"] == 2


@pytest.mark.parametrize(
    ("prompt", "expected", "code"),
    [
        (_v2_prompt(), "Otra evidencia.", "evidence_mismatch"),
        (
            _v2_prompt("texto\n=== JSON ===\n"),
            "texto\n=== JSON ===\n",
            "unsafe_prompt_boundaries",
        ),
    ],
)
def test_v3_shadow_prompt_fails_closed_on_unsafe_boundaries(
    prompt: str,
    expected: str,
    code: str,
):
    with pytest.raises(ShadowPromptError) as error:
        build_v3_shadow_prompt(prompt, expected_evidence=expected)
    assert error.value.code == code


def test_v3_shadow_prompt_rejects_prompt_budget_overflow():
    with pytest.raises(ShadowPromptError) as error:
        build_v3_shadow_prompt(
            _v2_prompt(),
            expected_evidence=EVIDENCE,
            max_prompt_bytes=100,
        )
    assert error.value.code == "prompt_budget_exceeded"


def test_shadow_runner_compares_both_versions_without_changing_v2_contract():
    provider = FakeLLMProvider(responses={
        "Devuelve exclusivamente el objeto JSON exigido por el esquema de interpretación v2.":
            _v2_response(),
        "Eres el intérprete semántico holístico de una partida de rol.":
            _v3_response(),
    })
    interpreter = IntentInterpreter(
        provider=provider,
        context_builder=ContextBuilder(),
    )

    comparison = PlayerTurnInterpretationV3ShadowRunner(interpreter).run(
        _context(),
        EVIDENCE,
    )

    assert comparison.v2_status == "valid"
    assert comparison.v3_status == "valid"
    assert comparison.v2_analysis is not None
    assert comparison.v2_analysis.schema_version == 2
    assert comparison.v2_analysis.active_step_index == 0
    assert comparison.v3_interpretation is not None
    assert comparison.v3_interpretation.schema_version == 3
    assert provider.call_count == 2

    shape = comparison_shape(comparison)
    assert shape["v2"]["step_count"] == 1
    assert shape["v3"]["act_count"] == 1
    assert shape["v3"]["event_count"] == 1
    serialized_shape = json.dumps(shape)
    assert EVIDENCE not in serialized_shape
    assert "la puerta" not in serialized_shape
    assert "INSTRUCCIONES" not in serialized_shape


def test_shadow_v3_validation_failure_does_not_discard_valid_v2_result():
    provider = FakeLLMProvider(responses={
        "Devuelve exclusivamente el objeto JSON exigido por el esquema de interpretación v2.":
            _v2_response(),
        "Eres el intérprete semántico holístico de una partida de rol.":
            '{"schema_version":3,"utterance_acts":[]}',
    })
    interpreter = IntentInterpreter(
        provider=provider,
        context_builder=ContextBuilder(),
    )

    comparison = PlayerTurnInterpretationV3ShadowRunner(interpreter).run(
        _context(),
        EVIDENCE,
    )

    assert comparison.v2_status == "valid"
    assert comparison.v2_analysis is not None
    assert comparison.v3_status == "invalid"
    assert comparison.v3_interpretation is None
    assert comparison.v3_error_code == "invalid_payload"
    assert comparison.v2_analysis.active_step_index == 0
