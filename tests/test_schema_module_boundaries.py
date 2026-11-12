from models import schemas
from models.campaign_api_schemas import CampaignCreate
from models.character_api_schemas import CharacterCreate as ContextCharacterCreate
from models.integration_api_schemas import SillyTavernTurnResolveIn
from models.turn_api_schemas import ManualRollIn
from models.world_api_schemas import WorldBootstrapIn


def test_legacy_schema_facade_reexports_the_context_owned_classes():
    assert schemas.CampaignCreate is CampaignCreate
    assert schemas.CharacterCreate is ContextCharacterCreate
    assert schemas.SillyTavernTurnResolveIn is SillyTavernTurnResolveIn
    assert schemas.ManualRollIn is ManualRollIn
    assert schemas.WorldBootstrapIn is WorldBootstrapIn


def test_schema_facade_exports_only_the_supported_public_request_types():
    assert set(schemas.__all__) == {
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
    }
