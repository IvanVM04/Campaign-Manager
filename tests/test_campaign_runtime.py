from repositories.campaign_repository import CampaignRepository
from services.campaign_runtime import CampaignRuntimeFactory


def test_runtime_factory_builds_independent_runtime_per_campaign(
    isolated_database,
):
    repository = CampaignRepository()
    campaign_two = repository.create_campaign(
        name="Second Campaign",
        system="D&D 5e 2014",
    )

    factory = CampaignRuntimeFactory()
    first = factory.get_runtime(1)
    second = factory.get_runtime(campaign_two["id"])

    assert first is factory.get_runtime(1)
    assert second is factory.get_runtime(campaign_two["id"])
    assert first is not second
    assert first.scope.campaign_id == 1
    assert second.scope.campaign_id == campaign_two["id"]
    assert first.world_service is not second.world_service
    assert first.campaign_state_service is not second.campaign_state_service
    assert first.turn_execution_lock is not second.turn_execution_lock
    assert first.turn_repository is not second.turn_repository


def test_runtime_factory_rejects_unknown_campaign(isolated_database):
    factory = CampaignRuntimeFactory()

    try:
        factory.get_runtime(999)
    except LookupError as exc:
        assert "999" in str(exc)
    else:
        raise AssertionError("unknown campaign should be rejected")


def test_runtime_factory_invalidate_rebuilds_campaign_runtime(
    isolated_database,
):
    factory = CampaignRuntimeFactory()
    first = factory.get_runtime(1)

    factory.invalidate(1)
    second = factory.get_runtime(1)

    assert second is not first
    assert second.campaign_id == 1
