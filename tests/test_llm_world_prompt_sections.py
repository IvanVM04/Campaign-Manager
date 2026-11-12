"""Regression tests for the legacy narrative prompt decomposition."""

from __future__ import annotations  # noqa: I001

import hashlib
from unittest.mock import patch

from models.campaign_state import CampaignState
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.llm_world.legacy_prompt_sections import STATIC_INSTRUCTIONS
from services.llm_world.llm_world_context_renderer import LLMWorldContextRenderer
from services.llm_world.llm_world_prompt_builder import LLMWorldPromptBuilder


# SHA-256 of the complete pre-decomposition prompt produced by the fixed
# narrative/context fixture below. SHA-256 avoids a weak-hash CodeQL alert.
_PRE_DECOMPOSITION_PROMPT_SHA256 = (
    "4854ebbe815cbc81f9cf59a02090da017ebcc663c57a5684acbff260ff02f07f"
)


def _prompt_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_legacy_prompt_matches_pre_decomposition_output_byte_for_byte() -> None:
    context_blocks = {
        "character_block": "CHARACTER BLOCK FIXTURE",
        "known_entities": "KNOWN ENTITIES FIXTURE",
        "known_items": "KNOWN ITEMS FIXTURE",
        "known_item_instances": "KNOWN ITEM INSTANCES FIXTURE",
        "known_resources": "KNOWN RESOURCES FIXTURE",
        "known_relations": "KNOWN RELATIONS FIXTURE",
        "known_events": "KNOWN EVENTS FIXTURE",
    }

    def render_fixture(_context: TurnContext) -> dict[str, str]:
        return context_blocks

    context = TurnContext(
        campaign=CampaignState(),
        current_session=None,
        active_character=None,
        world=WorldState(),
        active_character_entity=None,
    )
    with patch.object(
        LLMWorldContextRenderer,
        "build_context",
        staticmethod(render_fixture),
    ):
        prompt = LLMWorldPromptBuilder.build_prompt(
            "Aldric entrega una llave de plata al personaje.",
            context,
        )

    assert prompt.startswith(STATIC_INSTRUCTIONS)
    assert _prompt_sha256(prompt) == _PRE_DECOMPOSITION_PROMPT_SHA256
