from __future__ import annotations

import json

from services.context import ContextBuilder
from services.providers import FakeLLMProvider
from services.turns.intent_interpreter import IntentInterpreter
from tests.player_turn_interpretation_v3_shadow import (
    PlayerTurnInterpretationV3ShadowRunner,
    comparison_shape,
)
from tests.player_turn_v3_shadow_evaluation import (
    _V3_SEQUENCE_FIELDS,
    load_v3_shadow_corpus,
    score_shadow_comparison,
)
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger
from tests.test_player_turn_v3_shadow import (
    EVIDENCE,
    _context,
    _v2_response,
    _v3_response,
)


def test_v3_shadow_corpus_is_held_out_and_covers_audit_families():
    scenarios = load_v3_shadow_corpus()

    assert len(scenarios) == 12
    assert len({item["id"] for item in scenarios}) == 12
    assert all(item["critical"] for item in scenarios)
    assert {
        "npc_speech_quote",
        "quoted_instruction",
        "callback",
        "conditionals",
        "uncertainty_scope",
        "compound_dialogue_action",
        "explicit_relation",
        "transfer",
        "npc_attribute",
        "failed_action",
        "negation_and_sequence",
        "epistemic_uncertainty",
    } == {item["family"] for item in scenarios}


def test_shadow_scorer_emits_only_structural_diagnostics():
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
    assert set(_V3_SEQUENCE_FIELDS).issubset(
        comparison_shape(comparison)["v3"]
    )
    scenario = next(
        item
        for item in load_v3_shadow_corpus()
        if item["id"] == "attempt_uncertain_outcome"
    )
    ledger = SemanticEvaluationLedger()

    result = score_shadow_comparison(scenario, comparison, ledger)
    rendered = json.dumps(result, ensure_ascii=False)
    summary = json.dumps(ledger.summary(), ensure_ascii=False)

    assert result["case_id"] == "attempt_uncertain_outcome"
    assert EVIDENCE not in rendered
    assert scenario["input"] not in rendered
    assert EVIDENCE not in summary
    assert scenario["input"] not in summary
    assert "v3_polarities" in summary
