"""Opt-in live evaluation of held-out semantic understanding cases.

The held-out files are deliberately separate from prompt fixtures. Non-critical
results establish per-family baselines; critical safety cases remain hard gates.
"""

import json
import os
from pathlib import Path
from time import perf_counter

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.turn_context import TurnContext
from models.world_state import WorldState
from models.semantic_frames import SemanticObjectKind, SemanticArgumentRole
from services.providers import OllamaProvider
from services.turns.mechanics_adjudicator import MechanicsAdjudicator
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

pytestmark = pytest.mark.real_llm

FIXTURES = Path(__file__).parent / "fixtures"


def _make_adjudicator() -> MechanicsAdjudicator:
    provider = OllamaProvider(
        model=os.getenv("CAMPAIGN_MANAGER_REAL_LLM_MODEL", "gemma4:26b"),
        base_url=os.getenv(
            "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL",
            OllamaProvider.DEFAULT_BASE_URL,
        ),
        timeout=float(os.getenv("CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT", "120")),
    )
    return MechanicsAdjudicator(provider=provider)


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


def _score_semantic_scenario(analysis, scenario: dict) -> tuple[int, int, list[str]]:
    matched = 0
    total = 0
    failures: list[str] = []

    expected_frame = scenario.get("expected_action_frame")
    if expected_frame is not None:
        frames = [
            step.action_frame
            for step in analysis.steps
            if step.action_frame is not None
        ]
        total += 1
        if frames:
            matched += 1
        else:
            failures.append("action_frame: no frame returned")
        family = expected_frame.get("family")
        selected_frames = frames
        if family is not None:
            total += 1
            family_matches = [
                frame for frame in frames if frame.family.value == family
            ]
            if family_matches:
                matched += 1
                selected_frames = family_matches
            else:
                selected_frames = []
                failures.append(
                    f"action_frame.family: expected={family!r}; "
                    f"observed={[frame.family.value for frame in frames]!r}"
                )
        for expected_argument in expected_frame["arguments"]:
            total += 1
            argument_matches = any(
                argument.role.value == expected_argument["role"]
                and argument.mention.text.casefold()
                == expected_argument["mention"].casefold()
                and argument.mention.kind_hint.value
                == expected_argument["kind_hint"]
                for frame in selected_frames
                for argument in frame.arguments
            )
            if argument_matches:
                matched += 1
            else:
                failures.append(
                    f"action_frame.argument: expected={expected_argument!r}"
                )

    expected_relation = scenario.get("expected_relation")
    if expected_relation is not None:
        claims = analysis.relation_claims
        subject = expected_relation["subject"].casefold()
        object_ = expected_relation["object"].casefold()
        direction_matches = [
            claim for claim in claims
            if claim.subject.text.casefold() == subject
            and claim.object.text.casefold() == object_
        ]
        total += 1
        if direction_matches:
            matched += 1
        else:
            failures.append(
                "relation direction: expected="
                f"({expected_relation['subject']!r}, {expected_relation['object']!r}) "
                f"observed={[(claim.subject.text, claim.object.text) for claim in claims]!r}"
            )
        for field, wanted in expected_relation.items():
            if field in {"subject", "object"}:
                continue
            total += 1
            observed_values = []
            for claim in direction_matches:
                if field == "attributed_to":
                    observed = (
                        None if claim.attributed_to is None
                        else claim.attributed_to.text
                    )
                else:
                    observed = getattr(claim, field, None)
                    observed = _value(observed)
                observed_values.append(observed)
            if any(
                (observed.casefold() if isinstance(observed, str) else observed)
                == (wanted.casefold() if isinstance(wanted, str) else wanted)
                for observed in observed_values
            ):
                matched += 1
            else:
                failures.append(
                    f"relation.{field}: expected={wanted!r} "
                    f"observed={observed_values!r}"
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

    adjudicator = _make_adjudicator()
    context = _make_context()
    ledger = SemanticEvaluationLedger()
    critical_failures: list[str] = []
    observational_failures: list[str] = []
    provider_calls = 0
    started = perf_counter()

    for scenario in corpus["scenarios"]:
        repetitions = 3 if scenario["critical"] else 1
        for repetition in range(repetitions):
            case_started = perf_counter()
            try:
                analysis, _decision = adjudicator.understand(
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
                if scenario["critical"]:
                    critical_failures.append(description)
                else:
                    observational_failures.append(description)

    total_seconds = perf_counter() - started
    ledger.emit(record_property, prefix="semantic_holdout_intent")
    record_property("semantic_holdout_intent_model", os.getenv(
        "CAMPAIGN_MANAGER_REAL_LLM_MODEL", "gemma4:26b"
    ))
    record_property("semantic_holdout_intent_cases", len(corpus["scenarios"]))
    record_property("semantic_holdout_intent_provider_calls", provider_calls)
    record_property("semantic_holdout_intent_total_seconds", round(total_seconds, 3))
    print(ledger.render())
    if observational_failures:
        print("Non-critical held-out mismatches:\\n" + "\\n".join(observational_failures))
    assert not critical_failures, "\\n".join(critical_failures) + "\\n" + ledger.render()


def test_real_ollama_meets_held_out_semantic_frame_corpus_v1(record_property):
    corpus = json.loads(
        (FIXTURES / "semantic_frame_corpus_holdout_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert corpus["schema_version"] == 1
    assert corpus["split"] == "held_out"
    assert len(corpus["scenarios"]) >= 18

    adjudicator = _make_adjudicator()
    context = _make_context()
    ledger = SemanticEvaluationLedger()
    critical_failures: list[str] = []
    observational_failures: list[str] = []
    provider_calls = 0
    started = perf_counter()

    for scenario in corpus["scenarios"]:
        repetitions = 3 if scenario["critical"] else 1
        for repetition in range(repetitions):
            case_started = perf_counter()
            try:
                analysis, _decision = adjudicator.understand(
                    context,
                    scenario["input"],
                )
                assert analysis.schema_version == 2
                matched, total, failures = _score_semantic_scenario(
                    analysis,
                    scenario,
                )
            except Exception as exc:  # noqa: BLE001 - provider/decoder failures are failed evaluation cases
                matched, total = 0, 1
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
                if scenario["critical"]:
                    critical_failures.append(description)
                else:
                    observational_failures.append(description)

    total_seconds = perf_counter() - started
    ledger.emit(record_property, prefix="semantic_holdout_frames")
    record_property("semantic_holdout_frames_model", os.getenv(
        "CAMPAIGN_MANAGER_REAL_LLM_MODEL", "gemma4:26b"
    ))
    record_property("semantic_holdout_frames_cases", len(corpus["scenarios"]))
    record_property("semantic_holdout_frames_provider_calls", provider_calls)
    record_property("semantic_holdout_frames_total_seconds", round(total_seconds, 3))
    print(ledger.render())
    if observational_failures:
        print("Non-critical held-out mismatches:\\n" + "\\n".join(observational_failures))
    assert not critical_failures, "\\n".join(critical_failures) + "\\n" + ledger.render()


def test_real_ollama_emits_evidence_bound_recipient_correction(record_property):
    """The configured model must repair a wrong recipient from the latest answer."""
    from models.player_intent_analysis import PlayerIntentAnalysis
    from models.pending_intent_correction import PendingCorrectionSlot

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

    adjudicator = _make_adjudicator()
    result = adjudicator.understand_pending(
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
