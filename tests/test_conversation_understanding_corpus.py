"""Corpus-driven tests for multi-turn conversation reference resolution."""

import json
from models.entity import Entity
from models.player_intent_analysis import PlayerIntentAnalysis
from models.world_state import WorldState
from pathlib import Path
from services.context.conversation_reference_resolver import (
    ConversationReferenceResolver,
)
from types import SimpleNamespace


FIXTURE = Path(__file__).parent / "fixtures" / "conversation_understanding_corpus_v2.json"


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


def test_conversation_reference_corpus_v2():
    corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert corpus["schema_version"] == 2
    assert len(corpus["scenarios"]) >= 6

    resolver = ConversationReferenceResolver()
    for scenario in corpus["scenarios"]:
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
        expected = scenario["expected"]

        assert bool(result.clarification_question) is expected["clarification"], scenario["id"]
        if "entity_id" in expected:
            assert len(result.references) == 1, scenario["id"]
            assert result.references[0].entity_id == expected["entity_id"], scenario["id"]
            assert result.references[0].entity_name == expected["entity_name"], scenario["id"]
