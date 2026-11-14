"""Opt-in live evaluation for the PR #227 discourse/pipeline holdout.

The fixture is intentionally separate from prompt examples. This module records
stage-specific metrics and never logs prompts, model completions or campaign data.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.entity import Entity
from models.pending_intent_correction import PendingCorrectionSlot
from models.semantic_frames import (
    SemanticArgumentRole,
    SemanticObjectKind,
    SemanticRelationFamily,
)
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.world_state import WorldState
from services.context import ContextBuilder
from services.context.conversation_reference_resolver import (
    ConversationReferenceResolver,
)
from services.discourse_context import DiscourseContextBuilder
from services.providers import LLMSettings
from services.turns import IntentInterpreter
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

pytestmark = pytest.mark.real_llm

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "discourse_pipeline_corpus_holdout_v1.json"


def _live_intent_runtime():
    settings = LLMSettings.from_env()
    common_model = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_MODEL")
    common_timeout_raw = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT")
    common_timeout = (
        float(common_timeout_raw)
        if common_timeout_raw is not None
        else None
    )
    role_timeout = settings.intent_timeout_seconds
    if (
        "CAMPAIGN_MANAGER_LLM_INTENT_TIMEOUT_SECONDS" not in os.environ
        and common_timeout is not None
    ):
        role_timeout = common_timeout
    settings = replace(
        settings,
        base_url=os.getenv("CAMPAIGN_MANAGER_REAL_LLM_BASE_URL", settings.base_url),
        intent_model=os.getenv(
            "CAMPAIGN_MANAGER_LLM_INTENT_MODEL",
            common_model or settings.intent_model,
        ),
        intent_timeout_seconds=role_timeout,
    )
    usage_events: list[dict] = []
    provider = settings.create_provider(
        "intent",
        metrics_callback=usage_events.append,
    )
    context_builder = ContextBuilder()
    return (
        IntentInterpreter(provider=provider, context_builder=context_builder),
        provider,
        context_builder,
        usage_events,
    )


def _context(scenario: dict) -> TurnContext:
    entities = {
        item["id"]: Entity(
            id=item["id"],
            name=item["name"],
            entity_type=item.get("entity_type", "npc"),
            description=item.get("description", ""),
            active=item.get("active", True),
            aliases=item.get("aliases", []),
        )
        for item in scenario.get("visible_entities", [])
    }
    return TurnContext(
        campaign=CampaignState(
            campaign_id=99227,
            name="PR227 discourse evaluation",
        ),
        current_session=None,
        active_character=CharacterState(entity_id=99227),
        world=WorldState(entities=entities),
    )


def _recent_turns(scenario: dict) -> list[TurnRecord]:
    return [
        TurnRecord(
            id=item["id"],
            player_input=item.get("player_input", ""),
            narrative=item.get("narrative", ""),
        )
        for item in scenario["recent_turns"]
    ]


def _load_scenarios() -> list[dict]:
    corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert corpus["schema_version"] == 1
    assert corpus["split"] == "held_out"
    assert len(corpus["scenarios"]) == 28
    return corpus["scenarios"]


def test_real_ollama_meets_held_out_discourse_intent_and_resolution_corpus(
    record_property,
):
    """Score Intent and deterministic resolution separately, by family."""
    scenarios = [
        item
        for item in _load_scenarios()
        if item["family"] != "multi_turn_correction"
    ]
    interpreter, provider, context_builder, usage_events = _live_intent_runtime()
    resolver = ConversationReferenceResolver()
    ledger = SemanticEvaluationLedger()
    failures: list[str] = []
    observational_failures: list[str] = []
    calls = 0
    prompt_observations: Counter[str] = Counter()
    family_calls: Counter[str] = Counter()
    started = perf_counter()

    for scenario in scenarios:
        repetitions = 3 if scenario["critical"] else 1
        for repetition in range(repetitions):
            case_started = perf_counter()
            context = _context(scenario)
            recent_turns = _recent_turns(scenario)
            expected_intent = scenario["expected"]["intent"]
            analysis = None
            case_failures: list[str] = []
            prompt_bytes = 0
            section_sizes: dict[str, int] = {}
            discourse_retained = False
            try:
                prompt, section_sizes = interpreter._build_prompt(
                    context,
                    scenario["input"],
                    recent_turns=recent_turns,
                    evidence_text=scenario["input"],
                )
                prompt_bytes = len(prompt.encode("utf-8"))
                discourse_retained = "=== ÍNDICE DISCURSIVO" in prompt
                analysis = interpreter.interpret(
                    context,
                    scenario["input"],
                    recent_turns=recent_turns,
                    evidence_text=scenario["input"],
                )
                if analysis.category.value != expected_intent["category"]:
                    case_failures.append(
                        "intent.category: expected="
                        f"{expected_intent['category']!r} "
                        f"observed={analysis.category.value!r}"
                    )
            except Exception as exc:  # noqa: BLE001 - provider/decoder failure is a failed case
                case_failures.append(
                    f"intent provider/decoder error: {type(exc).__name__}"
                )

            elapsed = perf_counter() - case_started
            calls += 1
            family_calls[scenario["family"]] += 1
            prompt_observations[f"{scenario['family']}:calls"] += 1
            prompt_observations[f"{scenario['family']}:discourse_retained"] += int(
                discourse_retained
            )
            prompt_observations[f"{scenario['family']}:discourse_omitted"] += int(
                not discourse_retained
            )
            prompt_observations[f"{scenario['family']}:prompt_bytes"] += prompt_bytes
            prompt_observations[f"{scenario['family']}:history_bytes"] += (
                section_sizes.get("history", 0)
            )
            prompt_observations[f"{scenario['family']}:discourse_bytes"] += (
                section_sizes.get("discourse", 0)
            )

            ledger.record_case(
                f"intent:{scenario['family']}",
                expected_slots=1,
                matched_slots=int(not case_failures),
                elapsed_seconds=elapsed,
            )

            reference = scenario["expected"].get("reference")
            if reference is not None:
                resolution_started = perf_counter()
                observed_id = None
                clarification = False
                resolution_reason = "intent_interpretation_failed"
                try:
                    if analysis is not None:
                        resolution = resolver.resolve(
                            context.world,
                            analysis,
                            recent_turns=recent_turns,
                            current_input=scenario["input"],
                        )
                        observed_id = (
                            resolution.references[0].entity_id
                            if len(resolution.references) == 1
                            else None
                        )
                        clarification = (
                            analysis.requires_clarification
                            or resolution.clarification_question is not None
                        )
                        resolution_reason = resolution.abstention_reason or "resolved"
                    expected_id = reference["entity_id"]
                    expected_abstention = reference["clarification"]
                    resolution_passed = (
                        observed_id == expected_id
                        and clarification is expected_abstention
                    )
                    ledger.record_entity_resolution(
                        expected_entity_id=expected_id,
                        observed_entity_id=observed_id,
                        expected_abstention=expected_abstention,
                    )
                    if not resolution_passed:
                        case_failures.append(
                            "resolution: expected_id="
                            f"{expected_id!r}, observed_id={observed_id!r}, "
                            f"expected_clarification={expected_abstention}, "
                            f"observed_clarification={clarification}, "
                            f"reason={resolution_reason}"
                        )
                except Exception as exc:  # noqa: BLE001 - resolution error is a failed case
                    case_failures.append(
                        f"resolution error: {type(exc).__name__}"
                    )
                    ledger.record_entity_resolution(
                        expected_entity_id=reference["entity_id"],
                        observed_entity_id=None,
                        expected_abstention=reference["clarification"],
                    )
                ledger.record_case(
                    f"resolution:{scenario['family']}",
                    expected_slots=1,
                    matched_slots=int(
                        observed_id == reference["entity_id"]
                        and clarification is reference["clarification"]
                    ),
                    elapsed_seconds=perf_counter() - resolution_started,
                )

            if case_failures:
                description = (
                    f"{scenario['id']} repetition={repetition + 1}: "
                    + "; ".join(case_failures)
                )
                if scenario["critical"]:
                    failures.append(description)
                else:
                    observational_failures.append(description)

    elapsed_total = perf_counter() - started
    ledger.emit(record_property, prefix="discourse_holdout")
    record_property("discourse_holdout_model", provider.model)
    record_property("discourse_holdout_model_digest", provider.get_model_digest() or "unavailable")
    record_property(
        "discourse_holdout_ollama_version",
        provider.get_server_version() or "unavailable",
    )
    record_property("discourse_holdout_timeout_seconds", provider.timeout)
    record_property("discourse_holdout_scenarios", len(scenarios))
    record_property("discourse_holdout_provider_calls", calls)
    record_property("discourse_holdout_total_seconds", round(elapsed_total, 3))
    record_property(
        "discourse_holdout_family_calls",
        json.dumps(dict(family_calls), sort_keys=True),
    )
    record_property(
        "discourse_holdout_prompt_observations",
        json.dumps(dict(prompt_observations), sort_keys=True),
    )
    record_property(
        "discourse_holdout_usage_events",
        json.dumps(
            [
                {
                    key: event.get(key)
                    for key in (
                        "provider_role",
                        "provider_model",
                        "prompt_bytes",
                        "prompt_eval_count",
                        "eval_count",
                        "duration_ms",
                    )
                }
                for event in usage_events
            ],
            sort_keys=True,
        ),
    )
    print(ledger.render())
    if observational_failures:
        print("Non-critical mismatches:\\n" + "\\n".join(observational_failures))
    assert not failures, "\\n".join(failures) + "\\n" + ledger.render()


def _pending_analysis(prior_input: str, expected: dict):
    from models.player_intent_analysis import PlayerIntentAnalysis

    slot = expected["slot"]
    if slot == "relation_object":
        return PlayerIntentAnalysis.from_payload(
            {
                "schema_version": 2,
                "category": "report",
                "steps": [
                    {
                        "index": 0,
                        "source_excerpt": prior_input,
                        "actor": "player",
                        "action": "informar de una protección",
                        "modality": "reported",
                        "polarity": "positive",
                        "reported_outcome": "not_claimed",
                        "target_mentions": ["Mara", expected["previous_value"]],
                        "attributed_to": None,
                        "action_frame": {
                            "predicate": "protege",
                            "family": "social",
                            "arguments": [
                                {
                                    "role": "agent",
                                    "mention": {
                                        "text": "Mara",
                                        "kind_hint": "character",
                                    },
                                },
                                {
                                    "role": "patient",
                                    "mention": {
                                        "text": expected["previous_value"],
                                        "kind_hint": "character",
                                    },
                                },
                            ],
                        },
                    }
                ],
                "active_step_index": None,
                "requires_clarification": False,
                "clarification_question": None,
                "relation_claims": [
                    {
                        "step_index": 0,
                        "subject": {"text": "Mara", "kind_hint": "character"},
                        "predicate": "protege",
                        "object": {
                            "text": expected["previous_value"],
                            "kind_hint": "character",
                        },
                        "relation_family": "protection",
                        "polarity": "positive",
                        "modality": "reported",
                        "source_excerpt": prior_input,
                        "attributed_to": None,
                        "temporal_expression": None,
                    }
                ],
            },
            source_text=prior_input,
        )

    recipient = next(
        (name for name in ("Aldric", "Mara") if name in prior_input),
        "Aldric",
    )
    theme = "el mapa" if "mapa" in prior_input.casefold() else "la llave"
    return PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 2,
            "category": "action",
            "steps": [
                {
                    "index": 0,
                    "source_excerpt": prior_input,
                    "actor": "player",
                    "action": f"entregar {theme} a {recipient}",
                    "modality": "attempted",
                    "polarity": "positive",
                    "reported_outcome": "not_claimed",
                    "target_mentions": [theme, recipient],
                    "attributed_to": None,
                    "action_frame": {
                        "predicate": "Entrego",
                        "family": "transfer",
                        "arguments": [
                            {
                                "role": "theme",
                                "mention": {
                                    "text": theme,
                                    "kind_hint": "item_instance",
                                },
                            },
                            {
                                "role": "recipient",
                                "mention": {
                                    "text": recipient,
                                    "kind_hint": "character",
                                },
                            },
                        ],
                    },
                }
            ],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
            "relation_claims": [],
        },
        source_text=prior_input,
    )


def test_real_ollama_meets_pending_multi_turn_correction_holdout(record_property):
    """Corrections must be literal in the latest player answer and role-safe."""
    scenarios = [
        item
        for item in _load_scenarios()
        if item["family"] == "multi_turn_correction"
    ]
    interpreter, provider, _context_builder, usage_events = _live_intent_runtime()
    context = TurnContext(
        campaign=CampaignState(campaign_id=99228, name="PR227 correction evaluation"),
        current_session=None,
        active_character=CharacterState(entity_id=99228),
        world=WorldState(),
    )
    failures: list[str] = []
    provider_calls = 0
    started = perf_counter()

    for scenario in scenarios:
        repetitions = 3 if scenario["critical"] else 1
        for repetition in range(repetitions):
            pending = _pending_analysis(
                scenario["correction_rounds"][0]["prior_player_input"],
                scenario["correction_rounds"][0]["expected"],
            )
            evidence_parts = [scenario["correction_rounds"][0]["prior_player_input"]]
            for round_index, correction_round in enumerate(scenario["correction_rounds"]):
                answer = correction_round["player_answer"]
                evidence_parts.append(answer)
                evidence_text = "\\n\\n".join(evidence_parts)
                player_input = (
                    pending.steps[0].source_excerpt
                    + "\\n\\nDM: "
                    + correction_round["dm_question"]
                    + "\\n"
                    + answer
                )
                try:
                    result = interpreter.understand_pending(
                        context,
                        player_input,
                        pending_analysis=pending,
                        correction_evidence_text=answer,
                        evidence_text=evidence_text,
                    )
                    provider_calls += 1
                    expected = correction_round["expected"]
                    if expected["accepted"]:
                        if len(result.corrections) != 1:
                            raise AssertionError(
                                f"expected one correction, observed {len(result.corrections)}"
                            )
                        correction = result.corrections[0]
                        if correction.slot.value != expected["slot"]:
                            raise AssertionError("correction slot mismatch")
                        if correction.previous_value.casefold() != expected["previous_value"].casefold():
                            raise AssertionError("correction previous_value mismatch")
                        if correction.replacement.text.casefold() != expected["replacement"].casefold():
                            raise AssertionError("correction replacement mismatch")
                        if expected.get("role") is not None and (
                            correction.argument_role is None
                            or correction.argument_role.value != expected["role"]
                        ):
                            raise AssertionError("correction argument role mismatch")
                        if not correction.matches_analysis(result.analysis):
                            raise AssertionError("full analysis did not reflect correction")
                        pending = correction.apply(
                            pending,
                            player_evidence_text=evidence_text,
                            resolution_pending=True,
                            committed=False,
                        )
                    else:
                        if result.corrections:
                            raise AssertionError(
                                "ambiguous/ungrounded clarification emitted a correction"
                            )
                except Exception as exc:  # noqa: BLE001 - a failed correction is evaluation evidence
                    failures.append(
                        f"{scenario['id']} round={round_index + 1} "
                        f"repetition={repetition + 1}: {type(exc).__name__}: {exc}"
                    )
                    break

    record_property("discourse_correction_model", provider.model)
    record_property(
        "discourse_correction_model_digest",
        provider.get_model_digest() or "unavailable",
    )
    record_property(
        "discourse_correction_ollama_version",
        provider.get_server_version() or "unavailable",
    )
    record_property("discourse_correction_provider_calls", provider_calls)
    record_property(
        "discourse_correction_usage_events",
        json.dumps(
            [
                {
                    key: event.get(key)
                    for key in (
                        "provider_role",
                        "provider_model",
                        "prompt_bytes",
                        "prompt_eval_count",
                        "eval_count",
                        "duration_ms",
                    )
                }
                for event in usage_events
            ],
            sort_keys=True,
        ),
    )
    record_property(
        "discourse_correction_total_seconds",
        round(perf_counter() - started, 3),
    )
    assert not failures, "\\n".join(failures)
