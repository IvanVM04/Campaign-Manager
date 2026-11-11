"""Regression tests for the legacy narrative prompt decomposition."""

import hashlib
from unittest.mock import patch

from models.campaign_state import CampaignState
from models.turn_context import TurnContext
from models.world_state import WorldState
from services.llm_world.legacy_prompt_sections import STATIC_INSTRUCTIONS
from services.llm_world.llm_world_context_renderer import LLMWorldContextRenderer
from services.llm_world.llm_world_prompt_builder import LLMWorldPromptBuilder


# Git's content-addressed blob ID for the complete pre-decomposition prompt
# produced by the fixed narrative/context fixture below.
_PRE_DECOMPOSITION_PROMPT_BLOB_SHA = "d1b3a5e3fbd93180cc05a9e8deb77389c9e6a4cc"


def _git_blob_sha(content: str) -> str:
    encoded = content.encode("utf-8")
    header = f"blob {len(encoded)}\0".encode("ascii")
    return hashlib.sha1(header + encoded).hexdigest()


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
    assert _git_blob_sha(prompt) == _PRE_DECOMPOSITION_PROMPT_BLOB_SHA
