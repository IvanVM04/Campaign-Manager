"""Fictional campaign time, independent from server wall-clock time."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CampaignClock:
    campaign_id: int
    elapsed_minutes: int
    version: int
    updated_at: str

    def __post_init__(self) -> None:
        if self.campaign_id < 1:
            raise ValueError("campaign_id must be positive")
        if self.elapsed_minutes < 0:
            raise ValueError("elapsed_minutes cannot be negative")
        if self.version < 1:
            raise ValueError("version must be positive")
