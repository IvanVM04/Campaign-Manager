"""Opt-in live evaluation of held-out semantic understanding cases.

The held-out files are deliberately separate from prompt fixtures. Non-critical
results establish per-family baselines; critical safety cases remain hard gates.
"""

import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any, cast

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.semantic_frames import SemanticArgumentRole, SemanticObjectKind
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.providers import OllamaProvider
from services.turns.intent_interpreter import IntentInterpreter
from tests.intent_analysis_evaluation import (
    load_language_step_count_gold,
    score_intent_analysis,
)
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger
from tests.live_llm_config import thinking_for_role
from tests.semantic_evaluation_report import (
    build_live_evaluation_report,
    write_live_evaluation_report,
)
from tests.semantic_frame_evaluation import (
    load_semantic_frame_presence_gold,
    score_semantic_frame_scenario,
)

pytestmark = pytest.mark.real_llm

FIXTURES = Path(__file__).parent / "fixtures"



def _make_interpreter(
    usage_events: list[dict[str, Any]] | None = None,
) -> IntentInterpreter:
    provider = OllamaProvider(
        model=os.getenv("CAMPAIGN_MANAGER_REAL_LLM_MODEL", "gemma4:26b"),
        base_url=os.getenv(
            "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL",
            OllamaProvider.DEFAULT_BASE_URL,
        ),
        timeout=float(os.getenv("CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT", "120")),
        think=thinking_for_role("intent"),
        metrics_callback=(usage_events.append if usage_events is not None else None),
    )
    return IntentInterpreter(provider=provider)


def _make_context() -> TurnContext:
    return TurnContext(
        campaign=CampaignState(),
        current_session=None,
        active_character=CharacterState(entity_id=99220),
        world=WorldState(),
    )


def test_real_ollama_meets_held_out_language_understanding_corpus_v1(record_property):
    corpus = json.loads(
        (FIXTURES / "language_understanding_corpus_holdout_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert corpus["schema_version"] == 1
    assert corpus["split"] == "held_out"
    assert len(corpus["scenarios"]) >= 24
    expected_step_counts = load_language_step_count_gold(corpus)
    scenario_filter = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID")
    scenarios = corpus["scenarios"]
    if scenario_filter:
        scenarios = [item for item in scenarios if item["id"] == scenario_filter]
        if len(scenarios) != 1:
            raise ValueError(
                "CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID must match one language "
                "understanding holdout scenario"
            )

    usage_events: list[dict[str, Any]] = []
    interpreter = _make_interpreter(usage_events)
    provider = cast(OllamaProvider, interpreter.provider)
    context = _make_context()
    ledger = SemanticEvaluationLedger()
    critical_failures: list[str] = []
    observational_failures: list[str] = []
    provider_calls = 0
    started = perf_counter()

    for scenario in scenarios:
        repetitions = 3 if scenario["critical"] else 1
        for repetition in range(repetitions):
            case_started = perf_counter()
            analysis = None
            provider_error: str | None = None
            try:
                analysis = interpreter.interpret(
                    context,
                    scenario["input"],
                )
            except Exception as exc:  # noqa: BLE001 - failed calls remain scored misses
                provider_error = type(exc).__name__

            elapsed = perf_counter() - case_started
            _matched, _total, scored_failures = score_intent_analysis(
                analysis,
                expected=scenario["expected"],
                expected_step_count=expected_step_counts[scenario["id"]],
                family=scenario["family"],
                ledger=ledger,
                elapsed_seconds=elapsed,
            )
            failures = list(scored_failures)
            if provider_error is not None:
                failures.append(f"provider_or_decoder_error:{provider_error}")
            provider_calls += 1

            if failures:
                description = (
                    f"{scenario['id']} repetition={repetition + 1}: "
                    + "; ".join(failures)
                )
                if scenario["critical"] or scenario_filter:
                    critical_failures.append(description)
                else:
                    observational_failures.append(description)

    total_seconds = perf_counter() - started
    report = build_live_evaluation_report(
        evaluation_name="language_intent_holdout",
        corpus_name="language_understanding_corpus_holdout_v1.json",
        provider=provider,
        ledger=ledger,
        scenario_count=len(scenarios),
        provider_calls=provider_calls,
        elapsed_seconds=total_seconds,
        usage_events=usage_events,
        scenario_filter=scenario_filter,
    )
    report_path = write_live_evaluation_report(report)
    ledger.emit(record_property, prefix="semantic_holdout_intent")
    metadata = report["metadata"]
    record_property("semantic_holdout_intent_model", metadata["model"])
    record_property(
        "semantic_holdout_intent_model_digest",
        metadata["model_digest"] or "unavailable",
    )
    record_property(
        "semantic_holdout_intent_ollama_version",
        metadata["ollama_version"] or "unavailable",
    )
    record_property(
        "semantic_holdout_intent_timeout_seconds",
        metadata["timeout_seconds"]
        if metadata["timeout_seconds"] is not None
        else "unavailable",
    )
    record_property(
        "semantic_holdout_intent_think",
        "server_default" if metadata["think"] is None else str(metadata["think"]).lower(),
    )
    record_property(
        "semantic_holdout_intent_git_commit",
        metadata["git_commit"] or "unavailable",
    )
    record_property(
        "semantic_holdout_intent_hardware",
        metadata["hardware_label"] or "unspecified",
    )
    record_property("semantic_holdout_intent_cases", len(scenarios))
    record_property("semantic_holdout_intent_scenario_filter", scenario_filter or "all")
    record_property("semantic_holdout_intent_provider_calls", provider_calls)
    record_property("semantic_holdout_intent_total_seconds", round(total_seconds, 3))
    record_property(
        "semantic_holdout_intent_critical_failure_count",
        len(critical_failures),
    )
    record_property(
        "semantic_holdout_intent_observational_failure_count",
        len(observational_failures),
    )
    record_property(
        "semantic_holdout_intent_provider_error_case_count",
        sum("provider_or_decoder_error:" in item for item in critical_failures + observational_failures),
    )
    record_property(
        "semantic_holdout_intent_json_report",
        report_path or "not_configured",
    )
    print(ledger.render())
    if observational_failures:
        print("Non-critical held-out mismatches:\\n" + "\\n".join(observational_failures))
    assert not critical_failures, "\\n".join(critical_failures) + "\\n" + ledger.render()

def test_real_ollama_meets_held_out_semantic_frame_corpus_v1(record_property):
    """Score action/relation surface predicates independently from other slots."""
    corpus = json.loads(
        (FIXTURES / "semantic_frame_corpus_holdout_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert corpus["schema_version"] == 1
    assert corpus["split"] == "held_out"
    assert len(corpus["scenarios"]) >= 18
    presence_gold = load_semantic_frame_presence_gold(corpus)
    predicate_gold = json.loads(
        (FIXTURES / "semantic_frame_predicate_gold_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert predicate_gold["schema_version"] == 1
    assert predicate_gold["split"] == "held_out_annotations"
    predicate_by_id = {
        item["id"]: item for item in predicate_gold["scenarios"]
    }
    assert set(predicate_by_id) == {
        item["id"] for item in corpus["scenarios"]
    }

    # Attach sidecar gold only in memory. The original held-out corpus remains
    # byte-for-byte unchanged and the annotation fixture contains no utterances.
    scenarios = []
    for item in corpus["scenarios"]:
        scenario = dict(item)
        gold = predicate_by_id[item["id"]]
        if "action_frame_predicate" in gold:
            frame = dict(scenario["expected_action_frame"])
            frame["predicate"] = gold["action_frame_predicate"]
            scenario["expected_action_frame"] = frame
        if "relation_predicate" in gold:
            relation = dict(scenario["expected_relation"])
            relation["predicate"] = gold["relation_predicate"]
            scenario["expected_relation"] = relation
        scenarios.append(scenario)

    scenario_filter = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID")
    if scenario_filter:
        scenarios = [item for item in scenarios if item["id"] == scenario_filter]
        if len(scenarios) != 1:
            raise ValueError(
                "CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID must match one semantic-frame "
                "held-out scenario"
            )

    usage_events: list[dict[str, Any]] = []
    interpreter = _make_interpreter(usage_events)
    context = _make_context()
    ledger = SemanticEvaluationLedger()
    critical_failures: list[str] = []
    observational_failures: list[str] = []
    provider_calls = 0
    started = perf_counter()

    for scenario in scenarios:
        repetitions = 3 if scenario["critical"] else 1
        for repetition in range(repetitions):
            case_started = perf_counter()
            try:
                analysis = interpreter.interpret(
                    context,
                    scenario["input"],
                )
                assert analysis.schema_version == 2
                presence = presence_gold[scenario["id"]]
                matched, total, failures = score_semantic_frame_scenario(
                    analysis,
                    scenario,
                    expected_action_frame_count=presence["expected_action_frame_count"],
                    expected_relation_count=presence["expected_relation_count"],
                    ledger=ledger,
                )
            except Exception as exc:  # noqa: BLE001 - failed calls remain scored misses
                presence = presence_gold[scenario["id"]]
                matched, total, failures = score_semantic_frame_scenario(
                    None,
                    scenario,
                    expected_action_frame_count=presence["expected_action_frame_count"],
                    expected_relation_count=presence["expected_relation_count"],
                    ledger=ledger,
                )
                failures.append(f"provider_or_decoder_error:{type(exc).__name__}")
            elapsed = perf_counter() - case_started
            provider_calls += 1
            ledger.record_case(
                scenario["family"],
                expected_slots=total,
                matched_slots=matched,
                elapsed_seconds=elapsed,
                case_passed=not failures,
            )
            if failures:
                description = (
                    f"{scenario['id']} repetition={repetition + 1}: "
                    + "; ".join(failures)
                )
                if scenario["critical"] or scenario_filter:
                    critical_failures.append(description)
                else:
                    observational_failures.append(description)

    total_seconds = perf_counter() - started
    report = build_live_evaluation_report(
        evaluation_name="semantic_frame_predicate_holdout",
        corpus_name="semantic_frame_corpus_holdout_v1.json + semantic_frame_predicate_gold_v1.json",
        provider=interpreter.provider,
        ledger=ledger,
        scenario_count=len(scenarios),
        provider_calls=provider_calls,
        elapsed_seconds=total_seconds,
        usage_events=usage_events,
        scenario_filter=scenario_filter,
    )
    report_path = write_live_evaluation_report(report)
    ledger.emit(record_property, prefix="semantic_holdout_frames")
    metadata = report["metadata"]
    record_property("semantic_holdout_frames_model", metadata["model"])
    record_property(
        "semantic_holdout_frames_model_digest",
        metadata["model_digest"] or "unavailable",
    )
    record_property(
        "semantic_holdout_frames_ollama_version",
        metadata["ollama_version"] or "unavailable",
    )
    record_property(
        "semantic_holdout_frames_timeout_seconds",
        metadata["timeout_seconds"]
        if metadata["timeout_seconds"] is not None
        else "unavailable",
    )
    record_property(
        "semantic_holdout_frames_git_commit",
        metadata["git_commit"] or "unavailable",
    )
    record_property("semantic_holdout_frames_scenario_filter", scenario_filter or "all")
    record_property("semantic_holdout_frames_provider_calls", provider_calls)
    record_property("semantic_holdout_frames_total_seconds", round(total_seconds, 3))
    record_property(
        "semantic_holdout_frames_json_report",
        report_path or "not_configured",
    )
    print(ledger.render())
    if report_path:
        print(f"Predicate evaluation JSON report: {report_path}")
    if observational_failures:
        print("Non-critical held-out mismatches:\n" + "\n".join(observational_failures))
    assert not critical_failures, "\n".join(critical_failures) + "\n" + ledger.render()


def test_real_ollama_emits_evidence_bound_recipient_correction(record_property):
    """The configured model must repair a wrong recipient from the latest answer."""
    from models.pending_intent_correction import PendingCorrectionSlot
    from models.player_intent_analysis import PlayerIntentAnalysis

    original = "Entrego la llave de hierro a Aldric."
    clarification_question = "¿A qué persona entregas la llave?"
    correction_answer = "No, me refería a Mara, no a Aldric."
    cumulative_evidence = original + "\n\n" + correction_answer
    pending = PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 2,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": original,
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
                                "kind_hint": SemanticObjectKind.ITEM_INSTANCE.value,
                            },
                        },
                        {
                            "role": SemanticArgumentRole.RECIPIENT.value,
                            "mention": {
                                "text": "Aldric",
                                "kind_hint": SemanticObjectKind.CHARACTER.value,
                            },
                        },
                    ],
                },
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
            "relation_claims": [],
        },
        source_text=original,
    )

    interpreter = _make_interpreter()
    result = interpreter.understand_pending(
        _make_context(),
        original + "\n\nDM: " + clarification_question + "\n" + correction_answer,
        pending_analysis=pending,
        correction_evidence_text=correction_answer,
        evidence_text=cumulative_evidence,
    )

    assert result.analysis.schema_version == 2
    assert len(result.corrections) == 1
    correction = result.corrections[0]
    assert correction.slot is PendingCorrectionSlot.ACTION_ARGUMENT
    assert correction.argument_role is SemanticArgumentRole.RECIPIENT
    assert correction.previous_value == "Aldric"
    assert correction.replacement.text == "Mara"
    assert correction.matches_analysis(result.analysis)

    corrected = correction.apply(
        pending,
        player_evidence_text=cumulative_evidence,
        resolution_pending=True,
        committed=False,
    )
    assert corrected.steps[0].action_frame.arguments[1].mention.text == "Mara"
    record_property(
        "pending_correction_model",
        os.getenv("CAMPAIGN_MANAGER_REAL_LLM_MODEL", "gemma4:26b"),
    )
    record_property("pending_correction_slot", correction.slot.value)
    record_property("pending_correction_role", correction.argument_role.value)
    record_property("pending_correction_provider_calls", 1)
