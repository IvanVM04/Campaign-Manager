from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from bootstrap.campaign_runtime import CampaignRuntime

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


@contextmanager
def bind_current_runtime(runtime: CampaignRuntime) -> Iterator[None]:
    """Bind a runtime for the current context and always restore its predecessor."""
    token = _current_runtime.set(runtime)
    try:
        yield
    finally:
        _current_runtime.reset(token)
