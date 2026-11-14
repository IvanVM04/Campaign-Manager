from __future__ import annotations

import json
import os
from time import perf_counter

import pytest

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.entity import Entity
from models.mechanics import MechanicsDecisionType
from models.player_intent_analysis import PlayerIntentAnalysis
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.providers import OllamaProvider
from services.turns.mechanics_adjudicator import MechanicsAdjudicator

pytestmark = pytest.mark.real_llm


def _provider() -> OllamaProvider:
    return OllamaProvider(
        model=os.getenv("CAMPAIGN_MANAGER_REAL_LLM_MODEL", "gemma4:26b"),
        base_url=os.getenv(
            "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL",
            OllamaProvider.DEFAULT_BASE_URL,
        ),
        timeout=float(os.getenv("CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT", "120")),
    )


def _active_climbing_context() -> TurnContext:
    world = WorldState(
        entities={
            42: Entity(
                id=42,
                name="Pared lisa de piedra",
                entity_type="obstacle",
                description=(
                    "Pared vertical de piedra completamente lisa, de cuatro "
                    "metros de altura y sin asideros visibles."
                ),
            )
        }
    )
    return TurnContext(
        campaign=CampaignState(campaign_id=1, name="Mechanics live probe"),
        current_session=None,
        active_character=CharacterState(entity_id=99003),
        world=world,
    )


def _climbing_intent() -> tuple[str, PlayerIntentAnalysis]:
    source = (
        "Intento escalar la pared lisa de piedra de cuatro metros para "
        "alcanzar el tejado; no hay asideros visibles."
    )
    payload = {
        "schema_version": 2,
        "category": "action",
        "steps": [{
            "index": 0,
            "source_excerpt": source,
            "actor": "player",
            "action": "escalar la pared lisa de piedra para alcanzar el tejado",
            "modality": "attempted",
            "polarity": "positive",
            "reported_outcome": "not_claimed",
            "target_mentions": ["la pared lisa de piedra", "el tejado"],
            "attributed_to": None,
            "action_frame": {
                "predicate": "escalar",
                "family": "movement",
                "arguments": [
                    {
                        "role": "theme",
                        "mention": {
                            "text": "la pared lisa de piedra",
                            "kind_hint": "world_entity",
                        },
                    },
                    {
                        "role": "destination",
                        "mention": {
                            "text": "el tejado",
                            "kind_hint": "location",
                        },
                    },
                ],
            },
        }],
        "active_step_index": 0,
        "requires_clarification": False,
        "clarification_question": None,
        "relation_claims": [],
    }
    return source, PlayerIntentAnalysis.from_payload(
        payload,
        source_text=source,
    )


def test_real_ollama_mechanics_only_adjudicates_the_validated_active_step(record_property):
    """Exercise the new mechanics-only contract independently of intent parsing."""
    context = _active_climbing_context()
    source, analysis = _climbing_intent()
    adjudicator = MechanicsAdjudicator(_provider())
    started = perf_counter()

    decision = adjudicator.adjudicate_analysis(context, analysis)

    elapsed = perf_counter() - started
    assert decision.decision in {
        MechanicsDecisionType.ABILITY_CHECK,
        MechanicsDecisionType.SKILL_CHECK,
    }
    assert decision.dc is not None and 1 <= decision.dc <= 30
    record_property("mechanics_model", adjudicator.provider.model)
    record_property("mechanics_decision", decision.decision.value)
    record_property("mechanics_dc", decision.dc)
    record_property("mechanics_duration_seconds", round(elapsed, 3))
    record_property("mechanics_prompt_bytes", len(adjudicator.provider.last_prompt.encode("utf-8")) if hasattr(adjudicator.provider, "last_prompt") else None)
    print(
        "Mechanics-only probe: "
        f"model={adjudicator.provider.model}; decision={decision.decision.value}; "
        f"dc={decision.dc}; elapsed_seconds={elapsed:.3f}; "
        f"source_chars={len(source)}"
    )
