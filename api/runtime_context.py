from __future__ import annotations

from contextvars import ContextVar

from services.campaign_runtime import CampaignRuntime


_current_runtime: ContextVar[CampaignRuntime | None] = ContextVar(
    "campaign_runtime",
    default=None,
)


def get_current_runtime() -> CampaignRuntime:
    """Return the campaign runtime bound to the current HTTP request."""
    runtime = _current_runtime.get()
    if runtime is None:
        raise RuntimeError(
            "campaign runtime is only available inside an HTTP request"
        )
    return runtime
