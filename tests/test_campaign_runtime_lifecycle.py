from bootstrap.campaign_runtime import CampaignRuntimeFactory
from repositories.campaign_repository import CampaignRepository


def test_invalidate_rebuilds_only_the_selected_campaign_runtime(isolated_database):
    second = CampaignRepository().create_campaign(name="Second", system="D&D 5e 2014")
    factory = CampaignRuntimeFactory()
    first_runtime = factory.get_runtime(1)
    second_runtime = factory.get_runtime(second["id"])
    factory.invalidate(1)
    assert factory.get_runtime(1) is not first_runtime
    assert factory.get_runtime(second["id"]) is second_runtime


def test_shutdown_discards_cached_runtimes_and_allows_rebuilding(isolated_database):
    second = CampaignRepository().create_campaign(name="Second", system="D&D 5e 2014")
    factory = CampaignRuntimeFactory()
    first_runtime = factory.get_runtime(1)
    second_runtime = factory.get_runtime(second["id"])
    factory.shutdown()
    assert factory.get_runtime(1) is not first_runtime
    assert factory.get_runtime(second["id"]) is not second_runtime


def test_shutdown_is_idempotent_and_factory_remains_reusable(isolated_database):
    factory = CampaignRuntimeFactory()
    factory.shutdown()
    factory.shutdown()
    assert factory.get_runtime(1).campaign_id == 1
