"""Backward-compatible imports for API request schemas.

Production routers should import from their bounded-context modules.
"""

from .campaign_api_schemas import (
    CampaignCreate,
    CampaignUpdate,
    CampaignSessionUpdate,
    SessionIn,
    ActiveCharacterUpdate,
)
from .world_api_schemas import (
    WorldEntityBootstrapIn,
    WorldBootstrapIn,
)
from .turn_api_schemas import (
    TurnIn,
    ManualRollIn,
    DiceRollIn,
    ClarificationIn,
)
from .integration_api_schemas import (
    SillyTavernManualRollIn,
    SillyTavernClarificationIn,
    SillyTavernContextIn,
    SillyTavernTurnResolveIn,
    SillyTavernTurnCompleteIn,
)
from .character_api_schemas import (
    CharacterCreate,
)

__all__ = [
    "CampaignCreate",
    "CampaignUpdate",
    "CampaignSessionUpdate",
    "SessionIn",
    "ActiveCharacterUpdate",
    "WorldEntityBootstrapIn",
    "WorldBootstrapIn",
    "TurnIn",
    "ManualRollIn",
    "DiceRollIn",
    "ClarificationIn",
    "SillyTavernManualRollIn",
    "SillyTavernClarificationIn",
    "SillyTavernContextIn",
    "SillyTavernTurnResolveIn",
    "SillyTavernTurnCompleteIn",
    "CharacterCreate",
]
