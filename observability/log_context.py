"""Context-local correlation identifiers for request and turn diagnostics."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("campaign_manager_request_id", default=None)
_campaign_id: ContextVar[str | None] = ContextVar("campaign_manager_campaign_id", default=None)
_resolution_id: ContextVar[str | None] = ContextVar("campaign_manager_resolution_id", default=None)


def current_request_id() -> str | None:
    return _request_id.get()


def current_campaign_id() -> str | None:
    return _campaign_id.get()


def current_resolution_id() -> str | None:
    return _resolution_id.get()


@contextmanager
def bind_log_context(
    *,
    request_id: str | None = None,
    campaign_id: str | None = None,
    resolution_id: str | None = None,
) -> Iterator[None]:
    """Bind only supplied values and restore prior context even on failure."""
    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    if request_id is not None:
        tokens.append((_request_id, _request_id.set(request_id)))
    if campaign_id is not None:
        tokens.append((_campaign_id, _campaign_id.set(campaign_id)))
    if resolution_id is not None:
        tokens.append((_resolution_id, _resolution_id.set(resolution_id)))
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


@contextmanager
def bind_resolution_context(resolution_id: str) -> Iterator[None]:
    """Temporarily bind a durable resolution ID to logs in this execution."""
    token = _resolution_id.set(resolution_id)
    try:
        yield
    finally:
        _resolution_id.reset(token)
