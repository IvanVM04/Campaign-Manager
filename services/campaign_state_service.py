"""Backward-compatible imports for campaign state services."""

from services.campaign.campaign_state_service import (
    CampaignStateService,
    CampaignStateServiceError,
)

__all__ = ["CampaignStateService", "CampaignStateServiceError"]
