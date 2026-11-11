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
        with pytest.raises(ValueError, match="stop"):
            with bind_current_runtime(second):
                assert get_current_runtime() is second
                raise ValueError("stop")

        assert get_current_runtime() is first
