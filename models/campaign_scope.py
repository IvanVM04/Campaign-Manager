from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CampaignScope:
    """Identidad inmutable de la campaña que delimita una operación."""

    campaign_id: int

    def __post_init__(self) -> None:
        if not isinstance(self.campaign_id, int) or isinstance(
            self.campaign_id, bool
        ):
            raise TypeError("campaign_id must be an integer")
        if self.campaign_id <= 0:
            raise ValueError("campaign_id must be greater than zero")
