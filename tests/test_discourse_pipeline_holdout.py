"""Deterministic integrity and contract tests for the PR #227 discourse holdout."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from models.entity import Entity
from models.player_intent_analysis import PlayerIntentAnalysis
from models.turn_record import TurnRecord
from models.world_state import WorldState
from services.context.conversation_reference_resolver import (
    ConversationReferenceResolver,
)
from services.discourse_context import DiscourseContextBuilder

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "discourse_pipeline_corpus_holdout_v1.json"
EXISTING_HELD_OUT = (
    "language_understanding_corpus_holdout_v1.json",
    "semantic_frame_corpus_holdout_v1.json",
    "conversation_understanding_corpus_holdout_v1.json",
)
EXPECTED_FAMILIES = {
    "topic_boundary",
    "explicit_callback",
    "ellipsis_pending_action",
    "long_distance_reference",
    "local_grammatical_agreement",
    "npc_attribution_quoted_speech",
    "multi_turn_correction",
}


def _read_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _turns(scenario: dict) -> list[TurnRecord]:
    return [
        TurnRecord(
            id=item["id"],
            player_input=item.get("player_input", ""),
            narrative=item.get("narrative", ""),
        )
        for item in scenario["recent_turns"]
    ]


def _world(entities: list[dict]) -> WorldState:
    return WorldState(
        entities={
            item["id"]: Entity(
                id=item["id"],
                name=item["name"],
                entity_type=item.get("entity_type", "npc"),
                description=item.get("description", ""),
                active=item.get("active", True),
                aliases=item.get("aliases", []),
            )
            for item in entities
        }
    )


def _analysis(utterance: str, mention: str) -> PlayerIntentAnalysis:
    return PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 1,
            "category": "action",
            "steps": [
                {
                    "index": 0,
                    "source_excerpt": utterance,
                    "actor": "player",
                    "action": "interactuar con el objetivo mencionado",
                    "modality": "attempted",
                    "polarity": "positive",
                    "reported_outcome": "not_claimed",
                    "target_mentions": [mention],
                    "attributed_to": None,
                }
            ],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
        source_text=utterance,
    )


def test_discourse_pipeline_holdout_has_twenty_eight_balanced_cases():
    corpus = _read_fixture()
    scenarios = corpus["scenarios"]
    family_counts = Counter(item["family"] for item in scenarios)

    assert corpus["schema_version"] == 1
    assert corpus["split"] == "held_out"
    assert len(scenarios) == 28
    assert set(family_counts) == EXPECTED_FAMILIES
    assert set(family_counts.values()) == {4}
    assert len({item["id"] for item in scenarios}) == len(scenarios)
    assert all(item["critical"] is True or item["critical"] is False for item in scenarios)


def test_discourse_pipeline_holdout_does_not_duplicate_existing_held_out_inputs():
    corpus = _read_fixture()
    seen: dict[str, str] = {}

    for filename in EXISTING_HELD_OUT:
        existing = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
        for item in existing["scenarios"]:
            utterance = item.get("input") or item.get("utterance")
            if not isinstance(utterance, str) or not utterance.strip():
                continue
            key = " ".join(utterance.casefold().split())
            seen[key] = f"{filename}:{item['id']}"

    for item in corpus["scenarios"]:
        key = " ".join(item["input"].casefold().split())
        assert key not in seen, (
            f"{item['id']} duplicates held-out input {seen.get(key)}"
        )
        seen[key] = item["id"]


def test_discourse_pipeline_topic_scope_and_ellipsis_cues_match_fixture():
    builder = DiscourseContextBuilder()
    failures = []

    for scenario in _read_fixture()["scenarios"]:
        expected = scenario["expected"]
        recent_turns = _turns(scenario)
        actual_scope = [
            item.id
            for item in builder.scope_history(recent_turns, scenario["input"])
        ]
        if actual_scope != expected["scoped_turn_ids"]:
            failures.append(
                f"{scenario['id']}: scope expected={expected['scoped_turn_ids']} "
                f"observed={actual_scope}"
            )
        if "current_topic_shift" in expected:
            actual = builder.has_topic_shift(scenario["input"])
            if actual is not expected["current_topic_shift"]:
                failures.append(
                    f"{scenario['id']}: topic_shift expected="
                    f"{expected['current_topic_shift']} observed={actual}"
                )
        if "callback" in expected:
            actual = builder.reactivates_prior_topic(scenario["input"])
            if actual is not expected["callback"]:
                failures.append(
                    f"{scenario['id']}: callback expected={expected['callback']} "
                    f"observed={actual}"
                )
        if "topic_segments" in expected:
            actual = list(builder.topic_segments(recent_turns))
            if actual != expected["topic_segments"]:
                failures.append(
                    f"{scenario['id']}: segments expected="
                    f"{expected['topic_segments']} observed={actual}"
                )
        if "ellipsis_hint" in expected:
            rendered = builder.render(scenario["input"], recent_turns)
            actual = "Posible elipsis" in rendered
            if actual is not expected["ellipsis_hint"]:
                failures.append(
                    f"{scenario['id']}: ellipsis_hint expected="
                    f"{expected['ellipsis_hint']} observed={actual}"
                )

    assert not failures, "\\n".join(failures)


def test_discourse_pipeline_local_grammar_and_npc_attribution_match_fixture():
    builder = DiscourseContextBuilder()
    failures = []

    for scenario in _read_fixture()["scenarios"]:
        expected = scenario["expected"]
        grammar = expected.get("grammatical_features")
        if grammar is not None:
            actual = builder.grammatical_features(
                grammar["text"],
                grammar["alias"],
            )
            wanted = (grammar["gender"], grammar["number"])
            if actual != wanted:
                failures.append(
                    f"{scenario['id']}: grammar expected={wanted} observed={actual}"
                )

        if "npc_speaker_ids" in expected:
            visible = [
                Entity(
                    id=item["id"],
                    name=item["name"],
                    entity_type=item.get("entity_type", "npc"),
                    active=item.get("active", True),
                    aliases=item.get("aliases", []),
                )
                for item in scenario["npc_entities"]
            ]
            utterances = builder.extract_npc_utterances(
                scenario["npc_narrative"],
                700,
                visible,
            )
            actual = sorted({item.speaker_entity_id for item in utterances})
            wanted = sorted(expected["npc_speaker_ids"])
            if actual != wanted:
                failures.append(
                    f"{scenario['id']}: npc_speakers expected={wanted} observed={actual}"
                )

    assert not failures, "\\n".join(failures)


def test_discourse_pipeline_deterministic_reference_cases_match_expected_abstention():
    resolver = ConversationReferenceResolver()
    failures = []

    for scenario in _read_fixture()["scenarios"]:
        reference = scenario["expected"].get("reference")
        if reference is None:
            continue
        world = _world(scenario["visible_entities"])
        result = resolver.resolve(
            world,
            _analysis(scenario["input"], reference["mention"]),
            recent_turns=_turns(scenario),
            current_input=scenario["input"],
        )
        observed_id = (
            result.references[0].entity_id
            if len(result.references) == 1
            else None
        )
        clarification = result.clarification_question is not None
        if observed_id != reference["entity_id"] or clarification is not reference["clarification"]:
            failures.append(
                f"{scenario['id']}: expected_id={reference['entity_id']} "
                f"observed_id={observed_id}, expected_clarification="
                f"{reference['clarification']} observed={clarification}, "
                f"reason={result.abstention_reason}"
            )

    assert not failures, "\\n".join(failures)


def test_discourse_pipeline_correction_fixtures_keep_player_evidence_separate():
    scenarios = [
        item
        for item in _read_fixture()["scenarios"]
        if item["family"] == "multi_turn_correction"
    ]
    assert len(scenarios) == 4

    for scenario in scenarios:
        rounds = scenario["correction_rounds"]
        assert rounds
        for correction_round in rounds:
            question = correction_round["dm_question"]
            answer = correction_round["player_answer"]
            expected = correction_round["expected"]
            assert question.strip()
            assert answer.strip()
            assert question != answer
            if expected["accepted"]:
                assert expected["replacement"]
                assert expected["replacement"].casefold() in answer.casefold()
            else:
                assert expected["replacement"] is None
                assert expected["rejection_reason"] == "ambiguous_or_ungrounded"
