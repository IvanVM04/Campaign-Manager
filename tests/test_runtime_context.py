from typing import cast

import pytest

from api.runtime_context import bind_current_runtime, get_current_runtime
from bootstrap.campaign_runtime import CampaignRuntime


def test_get_current_runtime_requires_an_active_binding():
    with pytest.raises(
        RuntimeError,
        match="only available inside an HTTP request",
    ):
        get_current_runtime()


def test_bind_current_runtime_exposes_runtime_and_restores_previous_binding():
    first = cast(CampaignRuntime, object())
    second = cast(CampaignRuntime, object())

    with bind_current_runtime(first):
        assert get_current_runtime() is first

        with bind_current_runtime(second):
            assert get_current_runtime() is second

        assert get_current_runtime() is first

    with pytest.raises(RuntimeError, match="only available inside an HTTP request"):
        get_current_runtime()


def test_bind_current_runtime_restores_binding_after_exception():
    first = cast(CampaignRuntime, object())
    second = cast(CampaignRuntime, object())

    with bind_current_runtime(first):
        with pytest.raises(ValueError, match="stop"), bind_current_runtime(second):
            assert get_current_runtime() is second
            raise ValueError("stop")

        assert get_current_runtime() is first


def test_runtime_proxy_compatibility_exports_are_removed():
    import app
    from api import runtime_context

    legacy_names = (
        "campaign_repository",
        "character_repository",
        "entity_repository",
        "turn_repository",
        "world_service",
        "campaign_state_service",
        "memory_search_service",
        "context_builder",
        "turn_execution_lock",
        "character_creation_service",
        "combat_encounter_service",
        "silly_tavern_integration_service",
    )

    assert not hasattr(runtime_context, "RuntimeProxy")
    assert not any(hasattr(runtime_context, name) for name in legacy_names)
    assert not any(hasattr(app, name) for name in legacy_names)
    assert not any(name in app.__all__ for name in legacy_names)
