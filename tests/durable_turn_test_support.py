"""Shared deterministic providers for durable turn application tests."""

from bootstrap.campaign_runtime import CampaignRuntimeFactory


def service_with_fake_models():
    """Return the real durable turn service with deterministic in-memory providers."""
    runtime = CampaignRuntimeFactory().get_runtime(1)
    service = runtime.durable_native_turn_service
    service.resolver.mechanics_adjudicator = None
    proposal_calls = []
    service.resolver.extractor.provider = lambda prompt: (
        proposal_calls.append(prompt) or '{"operations": []}'
    )
    narrative_calls = []
    service.resolver.dm_service.provider.generate = lambda prompt: (
        narrative_calls.append(prompt) or "El personaje observa su entorno."
    )
    return service, proposal_calls, narrative_calls
