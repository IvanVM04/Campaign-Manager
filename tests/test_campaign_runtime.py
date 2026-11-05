from bootstrap.campaign_runtime import (
    CampaignRuntimeFactory as BootstrapCampaignRuntimeFactory,
)
from repositories.campaign_repository import CampaignRepository
from services.campaign_runtime import CampaignRuntimeFactory
from services.llm_settings import LLMSettings


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



def test_runtime_factory_uses_role_specific_llm_settings(isolated_database):
    settings = LLMSettings(
        narrative_model="narrator",
        extraction_model="extractor",
        mechanics_model="adjudicator",
        narrative_timeout_seconds=90,
        extraction_timeout_seconds=45,
        mechanics_timeout_seconds=30,
    )
    runtime = CampaignRuntimeFactory(llm_settings=settings).get_runtime(1)
    resolver = runtime.durable_native_turn_service.resolver

    assert resolver.dm_service.provider.model == "narrator"
    assert resolver.extractor.provider.model == "extractor"
    assert resolver.mechanics_adjudicator.provider.model == "adjudicator"
    assert resolver.dm_service.provider.timeout == 90.0
    assert resolver.extractor.provider.timeout == 45.0
    assert resolver.mechanics_adjudicator.provider.timeout == 30.0


def test_runtime_factory_rejects_invalid_llm_settings(isolated_database):
    try:
        CampaignRuntimeFactory(llm_settings="invalid")
    except TypeError as exc:
        assert "LLMSettings" in str(exc)
    else:
        raise AssertionError("invalid LLM settings should be rejected")


def test_legacy_runtime_import_is_compatible_with_bootstrap():
    assert CampaignRuntimeFactory is BootstrapCampaignRuntimeFactory
