"""Use cases for advancing fictional campaign time."""

from database import transaction
from models.campaign_clock import CampaignClock
from repositories.campaign_clock_repository import CampaignClockRepository
from repositories.campaign_repository import CampaignRepository
from repositories.persistent_effect_repository import PersistentEffectRepository


class CampaignClockService:
    def __init__(self, *, campaign_id: int, repository=None, campaign_repository=None, effect_repository=None):
        if isinstance(campaign_id, bool) or not isinstance(campaign_id, int) or campaign_id < 1:
            raise ValueError("campaign_id must be a positive integer")
        self.campaign_id = campaign_id
        self.repository = repository or CampaignClockRepository()
        self.campaign_repository = campaign_repository or CampaignRepository()
        self.effect_repository = effect_repository or PersistentEffectRepository()

    def get(self) -> CampaignClock:
        with transaction("IMMEDIATE") as conn:
            if self.campaign_repository.get_campaign(self.campaign_id, conn=conn) is None:
                raise LookupError("campaign does not exist")
            return self.repository.ensure(self.campaign_id, conn=conn)

    def advance(self, *, minutes: int, expected_elapsed_minutes: int) -> CampaignClock:
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 525600:
            raise ValueError("minutes must be an integer between 1 and 525600")
        if (
            isinstance(expected_elapsed_minutes, bool)
            or not isinstance(expected_elapsed_minutes, int)
            or expected_elapsed_minutes < 0
        ):
            raise ValueError("expected_elapsed_minutes must be a non-negative integer")
        with transaction("IMMEDIATE") as conn:
            if self.campaign_repository.get_campaign(self.campaign_id, conn=conn) is None:
                raise LookupError("campaign does not exist")
            self.repository.ensure(self.campaign_id, conn=conn)
            clock = self.repository.advance(
                self.campaign_id,
                minutes=minutes,
                expected_elapsed_minutes=expected_elapsed_minutes,
                conn=conn,
            )
            self.effect_repository.expire_due(
                self.campaign_id, clock.elapsed_minutes, conn=conn
            )
            return clock
