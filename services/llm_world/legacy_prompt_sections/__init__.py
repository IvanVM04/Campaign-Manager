"""Ordered static instruction sections for legacy narrative extraction."""

from .character_and_consistency_rules import CHARACTER_AND_CONSISTENCY_RULES
from .entity_rules import ENTITY_RULES
from .event_rules import EVENT_RULES
from .item_rules import ITEM_RULES
from .output_contract_and_examples import OUTPUT_CONTRACT_AND_EXAMPLES
from .relation_rules import RELATION_RULES
from .resource_rules import RESOURCE_RULES
from .role_and_fact_rules import ROLE_AND_FACT_RULES

# This order mirrors the pre-decomposition prompt exactly. Dynamic campaign data
# remains the responsibility of LLMWorldContextRenderer.
STATIC_INSTRUCTIONS = "".join(
    (
        ROLE_AND_FACT_RULES,
        ENTITY_RULES,
        ITEM_RULES,
        RESOURCE_RULES,
        RELATION_RULES,
        EVENT_RULES,
        CHARACTER_AND_CONSISTENCY_RULES,
        OUTPUT_CONTRACT_AND_EXAMPLES,
    )
)

__all__ = ["STATIC_INSTRUCTIONS"]
