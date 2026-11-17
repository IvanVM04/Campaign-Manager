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
from models.resolved_conversation_reference import (
    ResolvedConversationGroupReference,
    ResolvedConversationReference,
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
from services.turns import IntentInterpreter, IntentInterpreterError
from tests.discourse_evaluation import (
    DiscourseControlLedger,
    build_live_discourse_report,
    load_primary_actor_gold,
)
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

pytestmark = pytest.mark.real_llm

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "discourse_pipeline_corpus_holdout_v1.json"


_SPANISH_DETERMINERS = frozenset({
    "el", "la", "los", "las", "un", "una", "unos", "unas",
})


def _correction_mentions_equivalent(left: str, right: str) -> bool:
    """Compare noun mentions while allowing an optional Spanish article.

    Both values must still be independently grounded as literal mentions by
    the correction parser. This helper only prevents evaluation from treating
    "mapa" and "el mapa" as different semantic replacements.
    """
    def normalize(value: str) -> tuple[str | None, tuple[str, ...]]:
        tokens = tuple(value.casefold().split())
        article = tokens[0] if tokens and tokens[0] in _SPANISH_DETERMINERS else None
        return article, tokens[1:] if article is not None else tokens

    left_article, left_tokens = normalize(left)
    right_article, right_tokens = normalize(right)
    return bool(left_tokens) and left_tokens == right_tokens and (
        left_article is None
        or right_article is None
        or left_article == right_article
    )


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
    # NPC discourse fixtures are visible-world entities too. Keeping them in a
    # separate fixture field documents which entities participate in speaker
    # attribution, but they must still reach the actual prompt/context builder.
    entity_specs = {
        item["id"]: item
        for item in (
            *scenario.get("npc_entities", []),
            *scenario.get("visible_entities", []),
        )
    }
    entities = {
        item["id"]: Entity(
            id=item["id"],
            name=item["name"],
            entity_type=item.get("entity_type", "npc"),
            description=item.get("description", ""),
            active=item.get("active", True),
            aliases=item.get("aliases", []),
        )
        for item in entity_specs.values()
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
    turns = [
        TurnRecord(
            id=item["id"],
            player_input=item.get("player_input", ""),
            narrative=item.get("narrative", ""),
        )
        for item in scenario["recent_turns"]
    ]
    npc_narrative = scenario.get("npc_narrative")
    if npc_narrative and turns:
        last = turns[-1]
        turns[-1] = TurnRecord(
            id=last.id,
            session_id=last.session_id,
            player_input=last.player_input,
            narrative=npc_narrative,
            created_at=last.created_at,
            external_turn_id=last.external_turn_id,
            conversation_id=last.conversation_id,
        )
    return turns


def _load_scenarios() -> list[dict]:
    corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert corpus["schema_version"] == 1
    assert corpus["split"] == "held_out"
    assert len(corpus["scenarios"]) == 28
    return corpus["scenarios"]


def _evaluate_action_frame(
    analysis,
    expected_frame: dict,
    ledger: SemanticEvaluationLedger,
    family: str,
) -> list[str]:
    frames = (
        [
            step.action_frame
            for step in analysis.steps
            if step.action_frame is not None
        ]
        if analysis is not None
        else []
    )
    expected_family = expected_frame["family"]
    predicted_families = tuple(frame.family.value for frame in frames)
    ledger.record_semantic_slots(
        "action_frame_family",
        expected_slots=(expected_family,),
        predicted_slots=predicted_families,
    )
    expected_arguments = tuple(
        "argument:"
        + item["role"]
        + "|"
        + " ".join(item["mention"].casefold().split())
        for item in expected_frame["arguments"]
    )
    predicted_arguments = tuple(
        "argument:"
        + argument.role.value
        + "|"
        + " ".join(argument.mention.text.casefold().split())
        for frame in frames
        for argument in frame.arguments
    )
    ledger.record_semantic_slots(
        f"action_arguments:{family}",
        expected_slots=expected_arguments,
        predicted_slots=predicted_arguments,
    )
    failures = []
    if expected_family not in predicted_families:
        failures.append("action_frame.family_mismatch")
    if sorted(expected_arguments) != sorted(predicted_arguments):
        failures.append("action_frame.arguments_mismatch")
    return failures


def test_real_ollama_meets_held_out_discourse_intent_and_resolution_corpus(
    record_property,
):
    """Score Intent and deterministic resolution separately, by family."""
    scenarios = [
        item
        for item in _load_scenarios()
        if item["family"] != "multi_turn_correction"
    ]
    scenario_filter = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID")
    if scenario_filter:
        scenarios = [item for item in scenarios if item["id"] == scenario_filter]
        if len(scenarios) != 1:
            raise ValueError(
                "CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID must match one held-out "
                "non-correction scenario"
            )
    interpreter, provider, context_builder, usage_events = _live_intent_runtime()
    resolver = ConversationReferenceResolver()
    ledger = SemanticEvaluationLedger()
    control_ledger = DiscourseControlLedger()
    primary_actor_gold = load_primary_actor_gold()
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
                    case_failures.append("intent.category_mismatch")
                expected_actor = primary_actor_gold.get(scenario["id"])
                if expected_actor is not None:
                    predicted_actor = (
                        analysis.steps[0].actor.value
                        if analysis.steps
                        else "missing"
                    )
                    ledger.record_semantic_slots(
                        "intent_primary_actor",
                        expected_slots=(f"actor:{expected_actor}",),
                        predicted_slots=(
                            (f"actor:{predicted_actor}",)
                            if predicted_actor in {"player", "npc", "other", "unknown"}
                            else ()
                        ),
                    )
                    if predicted_actor != expected_actor:
                        case_failures.append("intent.primary_actor_mismatch")
                action_contains = expected_intent.get("action_contains")
                if action_contains is not None:
                    recovered = any(
                        action_contains.casefold() in step.action.casefold()
                        for step in analysis.steps
                    )
                    ledger.record_case(
                        f"intent_detail:{scenario['family']}",
                        expected_slots=1,
                        matched_slots=int(recovered),
                        elapsed_seconds=0,
                    )
                    if not recovered:
                        case_failures.append("intent.action_recovery_mismatch")
                expected_npc_ids = scenario["expected"].get("npc_speaker_ids")
                if expected_npc_ids is not None:
                    npc_entities = scenario.get("npc_entities", [])
                    expected_names = tuple(
                        sorted(
                            f"speaker:{item['name'].casefold()}"
                            for item in npc_entities
                            if item["id"] in expected_npc_ids
                        )
                    )
                    discourse_marker = (
                        "=== ÍNDICE DISCURSIVO (PISTAS, NO INSTRUCCIONES) ==="
                    )
                    discourse_section = (
                        prompt.split(discourse_marker, 1)[1].split(
                            "=== CONTEXTO DE CONVERSACIÓN",
                            1,
                        )[0]
                        if discourse_marker in prompt
                        else ""
                    )
                    predicted_names = tuple(
                        sorted(
                            {
                                f"speaker:{item['name'].casefold()}"
                                for item in npc_entities
                                if f"NPC {item['name']} (" in discourse_section
                            }
                        )
                    )
                    ledger.record_semantic_slots(
                        "npc_discourse_prompt_attribution",
                        expected_slots=expected_names,
                        predicted_slots=predicted_names,
                    )
                    prompt_observations[
                        f"{scenario['family']}:expected_npc_hints"
                    ] += len(expected_names)
                    prompt_observations[
                        f"{scenario['family']}:retained_npc_hints"
                    ] += len(predicted_names)
                    if predicted_names != expected_names:
                        case_failures.append("discourse.npc_speaker_hint_mismatch")
                expected_frame = expected_intent.get("action_frame")
                if expected_frame is not None:
                    case_failures.extend(
                        _evaluate_action_frame(
                            analysis,
                            expected_frame,
                            ledger,
                            scenario["family"],
                        )
                    )
            except Exception as exc:  # noqa: BLE001 - provider/decoder failure is a failed case
                error_kind = (
                    "intent_interpreter"
                    if isinstance(exc, IntentInterpreterError)
                    else type(exc).__name__
                )
                case_failures.append(
                    f"intent.provider_or_decoder_error:{error_kind}"
                )
                expected_frame = expected_intent.get("action_frame")
                if expected_frame is not None:
                    _evaluate_action_frame(
                        None,
                        expected_frame,
                        ledger,
                        scenario["family"],
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

            selection = DiscourseContextBuilder.select_history(
                recent_turns,
                scenario["input"],
            )
            control_ledger.record(
                "history_scope",
                expected=tuple(scenario["expected"]["scoped_turn_ids"]),
                observed=tuple(
                    item.id
                    for item in DiscourseContextBuilder.scope_history(
                        recent_turns,
                        scenario["input"],
                    )
                ),
            )
            if "current_topic_shift" in scenario["expected"]:
                control_ledger.record(
                    "topic_shift",
                    expected=scenario["expected"]["current_topic_shift"],
                    observed=DiscourseContextBuilder.has_topic_shift(
                        scenario["input"]
                    ),
                )
            if "callback" in scenario["expected"]:
                control_ledger.record(
                    "callback",
                    expected=scenario["expected"]["callback"],
                    observed=DiscourseContextBuilder.reactivates_prior_topic(
                        scenario["input"]
                    ),
                )
            if "ellipsis_hint" in scenario["expected"]:
                rendered_discourse = DiscourseContextBuilder.render(
                    scenario["input"],
                    recent_turns,
                )
                control_ledger.record(
                    "ellipsis_hint",
                    expected=scenario["expected"]["ellipsis_hint"],
                    observed="Posible elipsis" in rendered_discourse,
                )
            prompt_observations[
                f"{scenario['family']}:selection_reason:{selection.reason}"
            ] += 1
            prompt_observations[
                f"{scenario['family']}:surface_pronouns_detected"
            ] += len(
                DiscourseContextBuilder.surface_pronoun_mentions(
                    scenario["input"]
                )
            )

            reference = scenario["expected"].get("reference")
            if reference is not None:
                expected_group_ids = tuple(reference.get("entity_ids", ()))
                expected_entity_ids = expected_group_ids or (
                    (reference["entity_id"],)
                    if reference.get("entity_id") is not None
                    else ()
                )
                if expected_entity_ids:
                    context_started = perf_counter()
                    context_data = context_builder.build(
                        context.world,
                        scenario["input"],
                        recent_turns=recent_turns,
                        supplemental_queries=IntentInterpreter._recent_context_queries(
                            recent_turns
                        ),
                        character_entity_id=(
                            context.active_character.entity_id
                            if context.active_character is not None
                            else None
                        ),
                    )
                    selected_entities = context_data.get("entities", [])
                    selected_ids = {
                        (
                            item.get("id")
                            if isinstance(item, dict)
                            else getattr(item, "id", None)
                        )
                        for item in selected_entities
                    }
                    selected_ids.discard(None)
                    context_hit = set(expected_entity_ids).issubset(selected_ids)
                    ledger.record_context_recall(
                        expected_entity_ids=expected_entity_ids,
                        retrieved_entity_ids=selected_ids,
                    )
                    ledger.record_case(
                        f"context:{scenario['family']}",
                        expected_slots=1,
                        matched_slots=int(context_hit),
                        elapsed_seconds=perf_counter() - context_started,
                    )

                resolution_started = perf_counter()
                observed_id = None
                observed_group_ids: tuple[int, ...] = ()
                clarification = False
                resolution_passed = False
                expected_id = reference.get("entity_id")
                expected_group_ids = tuple(reference.get("entity_ids", ()))
                resolution_reason = "intent_interpretation_failed"
                try:
                    if analysis is not None:
                        intent_mentions = [
                            mention
                            for step in analysis.steps
                            for mention in (
                                *step.target_mentions,
                                *(
                                    argument.mention.text
                                    for argument in (
                                        step.action_frame.arguments
                                        if step.action_frame is not None
                                        else ()
                                    )
                                ),
                            )
                        ]
                        intent_mentions.extend(
                            mention.text
                            for claim in analysis.relation_claims
                            for mention in (claim.subject, claim.object)
                        )
                        prompt_observations[
                            f"{scenario['family']}:intent_mentions_present"
                        ] += int(bool(intent_mentions))
                        prompt_observations[
                            f"{scenario['family']}:intent_allows_world_proposal"
                        ] += int(analysis.allows_world_proposal)
                        prompt_observations[
                            f"{scenario['family']}:resolver_invocations"
                        ] += 1
                        resolution = resolver.resolve(
                            context.world,
                            analysis,
                            recent_turns=recent_turns,
                            current_input=scenario["input"],
                        )
                        resolved = (
                            resolution.references[0]
                            if len(resolution.references) == 1
                            else None
                        )
                        observed_id = (
                            resolved.entity_id
                            if isinstance(resolved, ResolvedConversationReference)
                            else None
                        )
                        observed_group_ids = (
                            resolved.entity_ids
                            if isinstance(resolved, ResolvedConversationGroupReference)
                            else ()
                        )
                        clarification = (
                            analysis.requires_clarification
                            or resolution.clarification_question is not None
                        )
                        reference_match = (
                            observed_group_ids == expected_group_ids
                            if expected_group_ids
                            else observed_id == expected_id
                        )
                        resolution_passed = (
                            reference_match
                            and clarification is reference["clarification"]
                        )
                        if resolution.abstention_reason is not None:
                            resolution_reason = resolution.abstention_reason
                        elif resolution.clarification_question is not None:
                            resolution_reason = "clarification_requested"
                        elif len(resolution.references) == 1:
                            resolution_reason = "resolved"
                        elif resolution.references:
                            resolution_reason = "multiple_references_returned"
                        else:
                            resolution_reason = "no_reference_returned"
                        prompt_observations[
                            f"{scenario['family']}:resolver_references_returned"
                        ] += len(resolution.references)
                        prompt_observations[
                            f"{scenario['family']}:resolver_group_references_returned"
                        ] += sum(
                            isinstance(item, ResolvedConversationGroupReference)
                            for item in resolution.references
                        )
                        prompt_observations[
                            f"{scenario['family']}:resolver_clarifications"
                        ] += int(resolution.clarification_question is not None)
                        prompt_observations[
                            f"{scenario['family']}:resolver_empty_results"
                        ] += int(
                            not resolution.references
                            and resolution.clarification_question is None
                        )
                        prompt_observations[
                            f"{scenario['family']}:resolver_reason:{resolution_reason}"
                        ] += 1
                    else:
                        prompt_observations[
                            f"{scenario['family']}:intent_mentions_present"
                        ] += 0
                        prompt_observations[
                            f"{scenario['family']}:intent_allows_world_proposal"
                        ] += 0
                        prompt_observations[
                            f"{scenario['family']}:resolver_not_invoked"
                        ] += 1
                    expected_abstention = reference["clarification"]
                    if expected_group_ids:
                        ledger.record_entity_group_resolution(
                            expected_entity_ids=expected_group_ids,
                            observed_entity_ids=observed_group_ids,
                        )
                    else:
                        ledger.record_entity_resolution(
                            expected_entity_id=expected_id,
                            observed_entity_id=observed_id,
                            expected_abstention=expected_abstention,
                        )
                    if not resolution_passed:
                        case_failures.append("resolution.reference_mismatch")
                except Exception as exc:  # noqa: BLE001 - resolution error is a failed case
                    case_failures.append(
                        f"resolution error: {type(exc).__name__}"
                    )
                    resolution_passed = False
                    if expected_group_ids:
                        ledger.record_entity_group_resolution(
                            expected_entity_ids=expected_group_ids,
                            observed_entity_ids=(),
                        )
                    else:
                        ledger.record_entity_resolution(
                            expected_entity_id=expected_id,
                            observed_entity_id=None,
                            expected_abstention=reference["clarification"],
                        )
                ledger.record_case(
                    f"resolution:{scenario['family']}",
                    expected_slots=1,
                    matched_slots=int(resolution_passed),
                    elapsed_seconds=perf_counter() - resolution_started,
                )

            if case_failures:
                description = (
                    f"{scenario['id']} repetition={repetition + 1}: "
                    + "; ".join(case_failures)
                )
                # A focused diagnostic run is intentionally strict even when
                # the selected corpus case is observational in the full suite.
                if scenario["critical"] or scenario_filter:
                    failures.append(description)
                else:
                    observational_failures.append(description)

    elapsed_total = perf_counter() - started
    ledger.emit(record_property, prefix="discourse_holdout")
    control_summary = control_ledger.summary()
    print("Discourse control accuracy: " + json.dumps(control_summary, sort_keys=True))
    for dimension, values in control_summary.items():
        record_property(
            f"discourse_holdout_control_{dimension}_accuracy",
            values["exact_accuracy"]
            if values["exact_accuracy"] is not None
            else "not_measured",
        )
        record_property(
            f"discourse_holdout_control_{dimension}_cases",
            values["cases"],
        )
    record_property("discourse_holdout_model", provider.model)
    record_property("discourse_holdout_model_digest", provider.get_model_digest() or "unavailable")
    record_property(
        "discourse_holdout_ollama_version",
        provider.get_server_version() or "unavailable",
    )
    record_property("discourse_holdout_timeout_seconds", provider.timeout)
    record_property("discourse_holdout_scenarios", len(scenarios))
    record_property("discourse_holdout_provider_calls", calls)
    record_property(
        "discourse_holdout_scenario_filter", scenario_filter or "all"
    )
    record_property(
        "discourse_holdout_strict_scenario_filter", bool(scenario_filter)
    )
    record_property("discourse_holdout_total_seconds", round(elapsed_total, 3))
    record_property(
        "discourse_holdout_family_calls",
        json.dumps(dict(family_calls), sort_keys=True),
    )
    record_property(
        "discourse_holdout_prompt_observations",
        json.dumps(dict(prompt_observations), sort_keys=True),
    )
    usage_summary = [
        {
            key: event.get(key)
            for key in (
                "provider_role",
                "provider_model",
                "response_model",
                "request_status",
                "prompt_bytes",
                "prompt_eval_count",
                "eval_count",
                "load_duration_ms",
                "prompt_eval_duration_ms",
                "eval_duration_ms",
                "total_duration_ms",
                "duration_ms",
                "think",
                "done",
                "done_reason",
            )
        }
        for event in usage_events
    ]
    usage_summary_json = json.dumps(usage_summary, sort_keys=True)
    record_property("discourse_holdout_usage_events", usage_summary_json)
    print("Ollama provider telemetry: " + usage_summary_json)
    print(ledger.render())
    if observational_failures:
        print("Non-critical mismatches:\n" + "\n".join(observational_failures))
    report_path = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH")
    if report_path:
        report_file = Path(report_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        think_value = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_THINK")
        report = build_live_discourse_report(
            ledger_summary=ledger.summary(),
            control_summary=control_ledger.summary(),
            prompt_observations=dict(prompt_observations),
            family_calls=dict(family_calls),
            usage_events=usage_events,
            model=provider.model,
            model_digest=provider.get_model_digest(),
            ollama_version=provider.get_server_version(),
            timeout_seconds=provider.timeout,
            think=think_value,
            git_commit=os.getenv("CAMPAIGN_MANAGER_GIT_COMMIT"),
            scenario_filter=scenario_filter,
            scenario_count=len(scenarios),
            provider_calls=calls,
            elapsed_seconds=elapsed_total,
            critical_failure_count=len(failures),
            observational_failure_count=len(observational_failures),
        )
        report_file.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
    assert not failures, "\n".join(failures) + "\n" + ledger.render()


def _pending_analysis(prior_input: str, expected: dict):
    from models.player_intent_analysis import PlayerIntentAnalysis

    slot = expected["slot"]
    if expected.get("accepted") is False:
        # The player explicitly left two recipients undecided. Do not seed the
        # correction test with an invented single recipient; the model must
        # preserve ambiguity and ask for a literal choice.
        ambiguous_recipient = "Mara o a Aldric"
        return PlayerIntentAnalysis.from_payload(
            {
                "schema_version": 2,
                "category": "plan",
                "steps": [
                    {
                        "index": 0,
                        "source_excerpt": prior_input,
                        "actor": "player",
                        "action": "entregar la carta a una de dos personas sin decidir",
                        "modality": "planned",
                        "polarity": "positive",
                        "reported_outcome": "not_claimed",
                        "target_mentions": ["la carta", ambiguous_recipient],
                        "attributed_to": None,
                        "action_frame": {
                            "predicate": "Entrego",
                            "family": "transfer",
                            "arguments": [
                                {
                                    "role": "theme",
                                    "mention": {
                                        "text": "la carta",
                                        "kind_hint": "item_instance",
                                    },
                                },
                                {
                                    "role": "recipient",
                                    "mention": {
                                        "text": ambiguous_recipient,
                                        "kind_hint": "character",
                                    },
                                },
                            ],
                        },
                    }
                ],
                "active_step_index": None,
                "requires_clarification": True,
                "clarification_question": "¿A cuál de las dos personas quieres entregar la carta?",
                "relation_claims": [],
            },
            source_text=prior_input,
        )
    if slot == "relation_object":
        return PlayerIntentAnalysis.from_payload(
            {
                "schema_version": 2,
                "category": "report",
                "steps": [
                    {
                        "index": 0,
                        "source_excerpt": prior_input,
                        "actor": "npc",
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
    lowered = prior_input.casefold()
    theme = (
        "el mapa"
        if "mapa" in lowered
        else "la carta"
        if "carta" in lowered
        else "la llave"
    )
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
                evidence_text = "\n\n".join(evidence_parts)
                player_input = (
                    pending.steps[0].source_excerpt
                    + "\n\nDM: "
                    + correction_round["dm_question"]
                    + "\n"
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
                        if not _correction_mentions_equivalent(
                            correction.replacement.text,
                            expected["replacement"],
                        ):
                            raise AssertionError("correction replacement mismatch")
                        if correction.slot.value == "action_argument":
                            expected_role = expected.get("role")
                            if (
                                expected_role is None
                                or correction.argument_role is None
                                or correction.argument_role.value != expected_role
                            ):
                                raise AssertionError("correction action argument role mismatch")
                            if correction.relation_claim_index is not None:
                                raise AssertionError(
                                    "action argument correction unexpectedly carries a relation claim index"
                                )
                        elif correction.slot.value in {"relation_subject", "relation_object"}:
                            expected_endpoint = expected.get("endpoint")
                            if (
                                expected_endpoint is not None
                                and correction.slot.value != f"relation_{expected_endpoint}"
                            ):
                                raise AssertionError("correction relation endpoint mismatch")
                            if correction.argument_role is not None:
                                raise AssertionError(
                                    "relation endpoint correction unexpectedly carries an action argument role"
                                )
                            expected_claim_index = expected.get("relation_claim_index")
                            if (
                                expected_claim_index is not None
                                and correction.relation_claim_index != expected_claim_index
                            ):
                                raise AssertionError("correction relation claim index mismatch")
                        elif (
                            correction.argument_role is not None
                            or correction.relation_claim_index is not None
                        ):
                            raise AssertionError(
                                "target correction unexpectedly carries structured selector metadata"
                            )
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
                        if scenario["id"] == "dp-correction-ungrounded-28":
                            if not result.analysis.requires_clarification:
                                raise AssertionError(
                                    "ambiguous alternative was not kept pending clarification"
                                )
                            if not result.analysis.clarification_question:
                                raise AssertionError(
                                    "ambiguous alternative returned no clarification question"
                                )
                except Exception as exc:  # noqa: BLE001 - a failed correction is evaluation evidence
                    cause = exc.__cause__
                    cause_detail = (
                        f"; cause={type(cause).__name__}: {cause}"
                        if cause is not None
                        else ""
                    )
                    failures.append(
                        f"{scenario['id']} round={round_index + 1} "
                        f"repetition={repetition + 1}: "
                        f"{type(exc).__name__}: {exc}{cause_detail}"
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
    assert not failures, "\n".join(failures)


def test_real_ollama_discourse_callback_survives_integrated_turn_pipeline(
    record_property,
):
    """Exercise callback → shared intent → mechanics → planner in production flow."""
    from models.entity import Entity
    from services.llm_world import LLMWorldExtractor
    from services.llm_world.operation_parser import OperationParser
    from services.providers import FakeLLMProvider
    from services.turns import DMService, MechanicsAdjudicator
    from services.turns.turn_resolution_service import TurnResolutionService
    from services.world import WorldApplier, WorldService

    operation_ledger = SemanticEvaluationLedger()
    settings = LLMSettings.from_env()
    common_model = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_MODEL")
    common_timeout_raw = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT")
    common_timeout = (
        float(common_timeout_raw)
        if common_timeout_raw is not None
        else None
    )

    def role_timeout(role: str, configured: float) -> float:
        env_name = f"CAMPAIGN_MANAGER_LLM_{role.upper()}_TIMEOUT_SECONDS"
        if env_name in os.environ or common_timeout is None:
            return configured
        return common_timeout

    settings = replace(
        settings,
        base_url=os.getenv(
            "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL",
            settings.base_url,
        ),
        intent_model=os.getenv(
            "CAMPAIGN_MANAGER_LLM_INTENT_MODEL",
            common_model or settings.intent_model,
        ),
        mechanics_model=os.getenv(
            "CAMPAIGN_MANAGER_LLM_MECHANICS_MODEL",
            common_model or settings.mechanics_model,
        ),
        extraction_model=os.getenv(
            "CAMPAIGN_MANAGER_LLM_EXTRACTION_MODEL",
            common_model or settings.extraction_model,
        ),
        intent_timeout_seconds=role_timeout(
            "intent",
            settings.intent_timeout_seconds,
        ),
        mechanics_timeout_seconds=role_timeout(
            "mechanics",
            settings.mechanics_timeout_seconds,
        ),
        extraction_timeout_seconds=role_timeout(
            "extraction",
            settings.extraction_timeout_seconds,
        ),
    )
    usage_events: list[dict] = []
    providers = {
        role: settings.create_provider(role, metrics_callback=usage_events.append)
        for role in ("intent", "mechanics", "extraction")
    }
    context_builder = ContextBuilder()
    interpreter = IntentInterpreter(
        provider=providers["intent"],
        context_builder=context_builder,
    )
    mechanics = MechanicsAdjudicator(
        provider=providers["mechanics"],
        context_builder=context_builder,
    )
    extractor = LLMWorldExtractor(
        provider=providers["extraction"],
        operation_parser=OperationParser(),
    )
    service = TurnResolutionService(
        dm_service=DMService(
            provider=FakeLLMProvider(response="No se genera narración en esta sonda."),
            context_builder=context_builder,
        ),
        extractor=extractor,
        world_service=WorldService(applier=WorldApplier()),
        mechanics_adjudicator=mechanics,
        intent_interpreter=interpreter,
        context_builder=context_builder,
    )
    context = TurnContext(
        campaign=CampaignState(
            campaign_id=99229,
            name="PR227 discourse callback integration",
            system="D&D 5e 2014",
        ),
        current_session=None,
        active_character=CharacterState(
            entity_id=99231,
            strength=3,
            dexterity=3,
            constitution=3,
            intelligence=3,
            wisdom=3,
            charisma=3,
        ),
        world=WorldState(
            entities={
                99229: Entity(
                    id=99229,
                    name="Pared lisa de piedra",
                    entity_type="obstacle",
                    description=(
                        "Pared vertical de piedra lisa, de cuatro metros, "
                        "sin asideros visibles ni salientes."
                    ),
                    active=True,
                )
            }
        ),
    )
    recent_turns = [
        TurnRecord(
            id=701,
            player_input="Examino la pared lisa de piedra.",
            narrative="La pared no tiene asideros visibles.",
        ),
        TurnRecord(
            id=702,
            player_input="Cambiando de tema, observo el patio.",
            narrative="Hay una fuente junto al muro.",
        ),
        TurnRecord(
            id=703,
            player_input="Busco una salida del patio.",
            narrative="La torre sigue al otro lado de la plaza.",
        ),
    ]
    player_input = (
        "Retomando lo de la pared lisa de piedra, intento escalarla "
        "usando Atletismo. Si alcanzo la cornisa, entro en la torre."
    )

    started = perf_counter()
    plan = service.prepare_turn(
        context,
        player_input,
        recent_turns=recent_turns,
        manual_rolls=(1,),
    )
    elapsed_ms = (perf_counter() - started) * 1000

    assert plan.intent_analysis is not None
    assert plan.intent_analysis.schema_version == 2
    assert plan.intent_analysis.active_step_index == 0
    assert plan.intent_analysis.is_actionable
    assert len(plan.intent_analysis.steps) >= 2
    assert plan.intent_analysis.steps[1].modality.value in {
        "conditional",
        "planned",
    }
    assert plan.mechanics_decision is not None
    assert plan.mechanics_result is not None
    assert plan.mechanics_result.outcome == "failure"
    assert not plan.mechanics_result.check.success
    assert plan.world_operations == ()
    assert plan.ordered_operations == ()
    operation_ledger.record_operations(
        expected_operations=(),
        predicted_operations=(
            f"{type(operation).__name__}:{index}"
            for index, operation in enumerate(plan.ordered_operations)
        ),
        critical_negative_control=True,
    )
    operation_summary = operation_ledger.summary()
    assert operation_summary["critical_false_persistent_changes"] == 0
    operation_ledger.emit(record_property, prefix="discourse_integrated_operations")

    record_property(
        "discourse_integrated_ollama_version",
        providers["intent"].get_server_version() or "unavailable",
    )
    record_property("discourse_integrated_elapsed_ms", round(elapsed_ms, 3))
    record_property(
        "discourse_integrated_intent_digest",
        providers["intent"].get_model_digest() or "unavailable",
    )
    record_property(
        "discourse_integrated_mechanics_digest",
        providers["mechanics"].get_model_digest() or "unavailable",
    )
    record_property(
        "discourse_integrated_extraction_digest",
        providers["extraction"].get_model_digest() or "unavailable",
    )
    record_property(
        "discourse_integrated_step_count",
        len(plan.intent_analysis.steps),
    )
    record_property(
        "discourse_integrated_mechanics_outcome",
        plan.mechanics_result.outcome,
    )
    for role in ("intent", "mechanics", "extraction"):
        role_events = [
            event for event in usage_events
            if event.get("provider_role") == role
        ]
        assert role_events, f"no live provider telemetry captured for {role}"
        assert all(event.get("prompt_bytes", 0) > 0 for event in role_events)
        record_property(
            f"discourse_integrated_{role}_calls",
            len(role_events),
        )
        record_property(
            f"discourse_integrated_{role}_metrics",
            json.dumps(
                [
                    {
                        key: event.get(key)
                        for key in (
                            "prompt_bytes",
                            "prompt_eval_count",
                            "eval_count",
                            "duration_ms",
                        )
                    }
                    for event in role_events
                ],
                sort_keys=True,
            ),
        )


def test_real_ollama_integrated_pipeline_preserves_one_explicit_npc_fact(
    record_property,
):
    """A completed observation must skip mechanics but reach the planner once."""
    from dataclasses import replace

    from operations.world_operations import (
        CreateEntityOperation,
        UpdateEntityOperation,
    )
    from services.llm_world import LLMWorldExtractor
    from services.llm_world.operation_parser import OperationParser
    from services.providers import FakeLLMProvider
    from services.turns import DMService
    from services.turns.turn_resolution_service import TurnResolutionService
    from services.world import WorldApplier, WorldService

    interpreter, intent_provider, context_builder, intent_events = (
        _live_intent_runtime()
    )
    settings = LLMSettings.from_env()
    common_model = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_MODEL")
    common_timeout = os.getenv("CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT")
    extraction_timeout = settings.extraction_timeout_seconds
    if (
        "CAMPAIGN_MANAGER_LLM_EXTRACTION_TIMEOUT_SECONDS" not in os.environ
        and common_timeout is not None
    ):
        extraction_timeout = float(common_timeout)
    settings = replace(
        settings,
        base_url=os.getenv(
            "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL",
            settings.base_url,
        ),
        extraction_model=os.getenv(
            "CAMPAIGN_MANAGER_LLM_EXTRACTION_MODEL",
            common_model or settings.extraction_model,
        ),
        extraction_timeout_seconds=extraction_timeout,
    )
    extraction_events: list[dict] = []
    extraction_provider = settings.create_provider(
        "extraction",
        metrics_callback=extraction_events.append,
    )
    extractor = LLMWorldExtractor(
        provider=extraction_provider,
        operation_parser=OperationParser(),
    )
    context = TurnContext(
        campaign=CampaignState(
            campaign_id=99230,
            name="PR227 positive operation quality",
        ),
        current_session=None,
        active_character=None,
        world=WorldState(
            entities={
                1: Entity(
                    id=1,
                    name="Aldric",
                    entity_type="npc",
                    description="Tabernero de la posada del Dragón.",
                    notes="Conoce los rumores del pueblo.",
                    active=True,
                )
            }
        ),
    )
    service = TurnResolutionService(
        dm_service=DMService(
            provider=FakeLLMProvider(
                response="No se genera narración en esta sonda."
            ),
            context_builder=context_builder,
        ),
        extractor=extractor,
        world_service=WorldService(applier=WorldApplier()),
        mechanics_adjudicator=None,
        intent_interpreter=interpreter,
        context_builder=context_builder,
    )
    source = (
        "Aldric me muestra una cicatriz con forma de dragón en el antebrazo; "
        "es un detalle visible que no conocíamos."
    )

    started = perf_counter()
    plan = service.prepare_turn(context, source)
    elapsed_ms = (perf_counter() - started) * 1000

    assert plan.intent_analysis is not None
    assert plan.intent_analysis.schema_version == 2
    assert plan.intent_analysis.allows_world_proposal
    assert plan.mechanics_decision is not None
    assert plan.mechanics_decision.decision.value == "none"
    updates = [
        operation
        for operation in plan.ordered_operations
        if isinstance(operation, UpdateEntityOperation)
    ]
    creates = [
        operation
        for operation in plan.ordered_operations
        if isinstance(operation, CreateEntityOperation)
    ]
    assert len(updates) == 1
    assert len(plan.ordered_operations) == 1
    assert updates[0].entity_id == 1
    assert not creates
    update_text = (
        f"{updates[0].description or ''} {updates[0].notes or ''}"
    ).casefold()
    assert "cicatriz" in update_text
    assert "dragón" in update_text

    predicted_operations = []
    for operation in plan.ordered_operations:
        if isinstance(operation, UpdateEntityOperation):
            predicted_operations.append(f"update_entity:{operation.entity_id}")
        elif isinstance(operation, CreateEntityOperation):
            predicted_operations.append(
                f"create_entity:{operation.name.casefold()}"
            )
        else:
            predicted_operations.append(type(operation).__name__)

    ledger = SemanticEvaluationLedger()
    ledger.record_operations(
        expected_operations=("update_entity:1",),
        predicted_operations=predicted_operations,
    )
    ledger.record_case(
        "positive_explicit_npc_fact",
        expected_slots=1,
        matched_slots=int(len(updates) == 1 and "dragón" in update_text),
        elapsed_seconds=elapsed_ms / 1000,
    )
    summary = ledger.summary()
    assert summary["operation_precision"] == 1.0
    assert summary["operation_recall"] == 1.0
    ledger.emit(record_property, prefix="discourse_positive_operation")

    intent_role_events = [
        event for event in intent_events
        if event.get("provider_role") == "intent"
    ]
    extraction_role_events = [
        event for event in extraction_events
        if event.get("provider_role") == "extraction"
    ]
    assert intent_role_events
    assert extraction_role_events
    record_property("discourse_positive_elapsed_ms", round(elapsed_ms, 3))
    record_property("discourse_positive_intent_model", intent_provider.model)
    record_property(
        "discourse_positive_intent_digest",
        intent_provider.get_model_digest() or "unavailable",
    )
    record_property(
        "discourse_positive_extraction_model",
        extraction_provider.model,
    )
    record_property(
        "discourse_positive_extraction_digest",
        extraction_provider.get_model_digest() or "unavailable",
    )
    record_property(
        "discourse_positive_intent_metrics",
        json.dumps(
            [
                {
                    key: event.get(key)
                    for key in (
                        "prompt_bytes",
                        "prompt_eval_count",
                        "eval_count",
                        "duration_ms",
                    )
                }
                for event in intent_role_events
            ],
            sort_keys=True,
        ),
    )
    record_property(
        "discourse_positive_extraction_metrics",
        json.dumps(
            [
                {
                    key: event.get(key)
                    for key in (
                        "prompt_bytes",
                        "prompt_eval_count",
                        "eval_count",
                        "duration_ms",
                    )
                }
                for event in extraction_role_events
            ],
            sort_keys=True,
        ),
    )
