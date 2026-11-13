"""Held-out regression suite for evidence-backed discourse resolution."""

import json
from pathlib import Path
from types import SimpleNamespace
from time import perf_counter

from models.entity import Entity
from models.player_intent_analysis import PlayerIntentAnalysis
from models.world_state import WorldState
from services.context.conversation_reference_resolver import (
    ConversationReferenceResolver,
)
from tests.semantic_evaluation_metrics import SemanticEvaluationLedger

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "conversation_understanding_corpus_holdout_v1.json"
)


def _analysis(utterance: str, mention: str) -> PlayerIntentAnalysis:
    return PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 1,
            "category": "action",
            "steps": [{
                "index": 0,
                "source_excerpt": utterance,
                "actor": "player",
                "action": "interactuar con el objetivo mencionado",
                "modality": "attempted",
                "polarity": "positive",
                "reported_outcome": "not_claimed",
                "target_mentions": [mention],
                "attributed_to": None,
            }],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
        source_text=utterance,
    )


def test_conversation_reference_held_out_corpus_v1():
    corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert corpus["schema_version"] == 1
    assert corpus["split"] == "held_out"
    assert len(corpus["scenarios"]) >= 12

    resolver = ConversationReferenceResolver()
    ledger = SemanticEvaluationLedger()
    failures: list[str] = []

    for scenario in corpus["scenarios"]:
        started = perf_counter()
        world = WorldState(
            entities={
                item["id"]: Entity(
                    id=item["id"],
                    name=item["name"],
                    entity_type=item["entity_type"],
                    description=item["description"],
                )
                for item in scenario["visible_entities"]
            }
        )
        turns = [
            SimpleNamespace(
                id=item["id"],
                player_input=item["player_input"],
                narrative=item.get("narrative", ""),
            )
            for item in scenario["recent_turns"]
        ]
        result = resolver.resolve(
            world,
            _analysis(scenario["utterance"], scenario["target_mention"]),
            recent_turns=turns,
        )
        elapsed = perf_counter() - started
        expected = scenario["expected"]
        observed_id = (
            result.references[0].entity_id
            if len(result.references) == 1
            else None
        )
        expected_id = expected.get("entity_id")
        expected_abstention = expected["clarification"]
        passed = (
            bool(result.clarification_question) is expected_abstention
            and (
                expected_id is None
                or observed_id == expected_id
            )
            and (
                expected_id is not None
                or observed_id is None
            )
        )
        ledger.record_case(
            scenario["family"],
            expected_slots=1,
            matched_slots=int(passed),
            elapsed_seconds=elapsed,
        )
        ledger.record_entity_resolution(
            expected_entity_id=expected_id,
            observed_entity_id=observed_id,
            expected_abstention=expected_abstention,
        )
        if not passed:
            failures.append(
                f"{scenario['id']}: expected={expected}, "
                f"observed_id={observed_id}, "
                f"clarification={bool(result.clarification_question)}, "
                f"reason={result.abstention_reason}"
            )

    report = ledger.render()
    assert not failures, "\\n".join(failures) + "\\n" + report
    assert "entity_link_precision: 1.0" in report
    assert "entity_link_recall: 1.0" in report
