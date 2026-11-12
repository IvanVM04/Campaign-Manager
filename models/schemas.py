"""Backward-compatible imports for API request schemas.

Production routers should import from their bounded-context modules.
"""

from .campaign_api_schemas import (
    ActiveCharacterUpdate,
    CampaignCreate,
    CampaignSessionUpdate,
    CampaignUpdate,
    SessionIn,
)
from .character_api_schemas import (
    CharacterCreate,
)
from .integration_api_schemas import (
    SillyTavernClarificationIn,
    SillyTavernContextIn,
    SillyTavernManualRollIn,
    SillyTavernTurnCompleteIn,
    SillyTavernTurnResolveIn,
)
from .turn_api_schemas import (
    ClarificationIn,
    DiceRollIn,
    ManualRollIn,
    TurnIn,
)
from .world_api_schemas import (
    WorldBootstrapIn,
    WorldEntityBootstrapIn,
)

__all__ = [
    "ActiveCharacterUpdate",
    "CampaignCreate",
    "CampaignSessionUpdate",
    "CampaignUpdate",
    "CharacterCreate",
    "ClarificationIn",
    "DiceRollIn",
    "ManualRollIn",
    "SessionIn",
    "SillyTavernClarificationIn",
    "SillyTavernContextIn",
    "SillyTavernManualRollIn",
    "SillyTavernTurnCompleteIn",
    "SillyTavernTurnResolveIn",
    "TurnIn",
    "WorldBootstrapIn",
    "WorldEntityBootstrapIn",
]
