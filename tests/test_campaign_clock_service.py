from contextlib import contextmanager

import pytest

from repositories.campaign_repository import CampaignRepository
from services.campaign.campaign_clock_service import CampaignClockService


def test_campaign_clock_starts_at_zero_and_persists(isolated_database):
    campaign = CampaignRepository().create_campaign(name="Clock test")
    service = CampaignClockService(campaign_id=campaign["id"])

    first = service.get()
    assert first.elapsed_minutes == 0
    assert first.version == 1

    advanced = service.advance(minutes=90, expected_elapsed_minutes=0)
    assert advanced.elapsed_minutes == 90
    assert advanced.version == 2

    recreated = CampaignClockService(campaign_id=campaign["id"]).get()
    assert recreated == advanced


def test_campaign_clock_uses_optimistic_concurrency(isolated_database):
    campaign = CampaignRepository().create_campaign(name="Clock concurrency")
    service = CampaignClockService(campaign_id=campaign["id"])
    service.get()
    service.advance(minutes=30, expected_elapsed_minutes=0)

    with pytest.raises(RuntimeError, match="clock changed"):
        service.advance(minutes=15, expected_elapsed_minutes=0)


def test_campaign_clocks_are_isolated(isolated_database):
    campaigns = CampaignRepository()
    first = campaigns.create_campaign(name="First")
    second = campaigns.create_campaign(name="Second")
    CampaignClockService(campaign_id=first["id"]).advance(
        minutes=60, expected_elapsed_minutes=0
    )
    assert CampaignClockService(campaign_id=first["id"]).get().elapsed_minutes == 60
    assert CampaignClockService(campaign_id=second["id"]).get().elapsed_minutes == 0


def test_campaign_clock_rejects_invalid_advances(isolated_database):
    campaign = CampaignRepository().create_campaign(name="Validation")
    service = CampaignClockService(campaign_id=campaign["id"])
    with pytest.raises(ValueError):
        service.advance(minutes=0, expected_elapsed_minutes=0)
    with pytest.raises(ValueError):
        service.advance(minutes=True, expected_elapsed_minutes=0)

def test_campaign_clock_get_uses_immediate_transaction_for_lazy_initialization(
    isolated_database,
    monkeypatch,
):
    from database import transaction as real_transaction

    modes = []

    @contextmanager
    def tracked_transaction(mode):
        modes.append(mode)
        with real_transaction(mode) as conn:
            yield conn

    monkeypatch.setattr(
        "services.campaign.campaign_clock_service.transaction",
        tracked_transaction,
    )

    campaign = CampaignRepository().create_campaign(name="Clock initialization")
    clock = CampaignClockService(campaign_id=campaign["id"]).get()

    assert clock.elapsed_minutes == 0
    assert modes == ["IMMEDIATE"]
