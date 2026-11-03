"""Request schemas for campaign-clock operations."""

from pydantic import BaseModel, Field, StrictInt


class CampaignClockAdvanceIn(BaseModel):
    minutes: StrictInt = Field(..., ge=1, le=525600)
    expected_elapsed_minutes: StrictInt = Field(..., ge=0)
