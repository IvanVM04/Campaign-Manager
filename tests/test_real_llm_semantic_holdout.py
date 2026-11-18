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
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger
from tests.semantic_evaluation_report import (
    build_live_evaluation_report,
    write_live_evaluation_report,
)
from tests.semantic_frame_evaluation import score_semantic_frame_scenario

pytestmark = pytest.mark.real_llm

FIXTURES = Path(__file__).parent / "fixtures"


def _optional_bool_environment_variable(name: str) -> bool | None:
    """Parse an optional boolean setting for live LLM evaluation."""
    value = os.getenv(name)
    if value is None:
        return None
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean (true/false)")


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
        think=_optional_bool_environment_variable("CAMPAIGN_MANAGER_REAL_LLM_THINK"),
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


def _value(value):
    return value.value if hasattr(value, "value") else value


def _score_object(actual, expected: dict[str, object]) -> tuple[int, int, list[str]]:
    matched = 0
    failures = []
    for field, wanted in expected.items():
        observed = None if actual is None else _value(getattr(actual, field, None))
        if observed == wanted:
            matched += 1
        else:
            failures.append(f"{field}: expected={wanted!r} observed={observed!r}")
    return matched, len(expected), failures


def _score_language_scenario(analysis, expected: dict) -> tuple[int, int, list[str]]:
    matched = 0
    total = 0
    failures: list[str] = []
    for field in ("category", "active_step_index", "requires_clarification"):
        observed = _value(getattr(analysis, field))
        wanted = expected[field]
        total += 1
        if observed == wanted:
            matched += 1
        else:
            failures.append(f"{field}: expected={wanted!r} observed={observed!r}")

    steps = analysis.steps
    step_expectations = (
        ("step", analysis.active_step_index if analysis.active_step_index is not None else 0),
        ("first_step", 0),
        ("later_step", 1),
    )
    for key, index in step_expectations:
        if key not in expected:
            continue
        wanted_fields = expected[key]
        actual = steps[index] if index < len(steps) else None
        score, count, errors = _score_object(actual, wanted_fields)
        matched += score
        total += count
        failures.extend(
            f"{key}[{index}].{error}" for error in errors
        )
    return matched, total, failures


def test_real_ollama_meets_held_out_language_understanding_corpus_v1(record_property):
    corpus = json.loads(
        (FIXTURES / "language_understanding_corpus_holdout_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert corpus["schema_version"] == 1
    assert corpus["split"] == "held_out"
    assert len(corpus["scenarios"]) >= 24
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
            try:
                analysis = interpreter.interpret(
                    context,
                    scenario["input"],
                )
                matched, total, failures = _score_language_scenario(
                    analysis,
                    scenario["expected"],
                )
            except Exception as exc:  # noqa: BLE001 - provider/decoder failures are failed evaluation cases
                matched, total = 0, 3 + len(scenario["expected"].get("step", {}))
                failures = [f"provider/decoder error: {type(exc).__name__}: {exc}"]
            elapsed = perf_counter() - case_started
            provider_calls += 1
            ledger.record_case(
                scenario["family"],
                expected_slots=total,
                matched_slots=matched,
                elapsed_seconds=elapsed,
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
    ledger.emit(record_property, prefix="semantic_holdout_intent")
    usage_summary = {
        "calls": len(usage_events),
        "failed_requests": sum(
            event.get("request_status") == "failed" for event in usage_events
        ),
        "duration_ms_total": round(
            sum(float(event.get("duration_ms", 0)) for event in usage_events), 3
        ),
        "prompt_bytes_total": sum(
            int(event.get("prompt_bytes", 0)) for event in usage_events
        ),
        "prompt_tokens_total": sum(
            int(event.get("prompt_eval_count", 0)) for event in usage_events
        ),
        "completion_tokens_total": sum(
            int(event.get("eval_count", 0)) for event in usage_events
        ),
    }
    record_property("semantic_holdout_intent_model", provider.model)
    record_property(
        "semantic_holdout_intent_model_digest",
        provider.get_model_digest() or "unavailable",
    )
    record_property(
        "semantic_holdout_intent_ollama_version",
        provider.get_server_version() or "unavailable",
    )
    record_property("semantic_holdout_intent_timeout_seconds", provider.timeout)
    record_property(
        "semantic_holdout_intent_think",
        "server_default" if provider.think is None else str(provider.think).lower(),
    )
    record_property(
        "semantic_holdout_intent_git_commit",
        os.getenv("GITHUB_SHA")
        or os.getenv("CAMPAIGN_MANAGER_GIT_COMMIT")
        or "unavailable",
    )
    record_property(
        "semantic_holdout_intent_hardware",
        os.getenv("CAMPAIGN_MANAGER_REAL_LLM_HARDWARE") or "unspecified",
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
        sum(
            "provider/decoder error:" in item
            for item in critical_failures + observational_failures
        ),
    )
    record_property(
        "semantic_holdout_intent_provider_usage",
        json.dumps(usage_summary, sort_keys=True, separators=(",", ":")),
    )
    print(ledger.render())
    if observational_failures:
        print("Non-critical held-out mismatches:\n" + "\n".join(observational_failures))
    assert not critical_failures, "\n".join(critical_failures) + "\n" + ledger.render()


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
                matched, total, failures = score_semantic_frame_scenario(
                    analysis,
                    scenario,
                    ledger=ledger,
                )
            except Exception as exc:  # noqa: BLE001 - provider/decoder failures are failed cases
                matched, total = 0, 1
                failures = [f"provider/decoder error: {type(exc).__name__}: {exc}"]
                # A rejected response still counts as a missing expected predicate.
                score_semantic_frame_scenario(None, scenario, ledger=ledger)
            elapsed = perf_counter() - case_started
            provider_calls += 1
            ledger.record_case(
                scenario["family"],
                expected_slots=total,
                matched_slots=matched,
                elapsed_seconds=elapsed,
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
