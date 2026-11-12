"""ASGI request correlation and request-completion logging middleware."""

from __future__ import annotations

import re
import time
import uuid
import logging
from typing import Any

from observability.log_context import bind_log_context

logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_REQUEST_ID_HEADER = b"x-request-id"
_CAMPAIGN_ID_HEADER = b"x-campaign-id"


def _decode_header(headers: list[tuple[bytes, bytes]], name: bytes) -> str | None:
    for key, value in headers:
        if key.lower() == name:
            try:
                return value.decode("ascii").strip()
            except UnicodeDecodeError:
                return None
    return None


def _campaign_id_from_header(headers: list[tuple[bytes, bytes]]) -> str | None:
    raw_value = _decode_header(headers, _CAMPAIGN_ID_HEADER)
    if raw_value is None or not raw_value.isdigit():
        return None
    value = int(raw_value)
    return str(value) if value > 0 else None


class RequestObservabilityMiddleware:
    """Assign a safe request ID, bind context and append it to the response."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers", []))
        supplied_id = _decode_header(headers, _REQUEST_ID_HEADER)
        request_id = (
            supplied_id
            if supplied_id is not None and _REQUEST_ID_PATTERN.fullmatch(supplied_id)
            else uuid.uuid4().hex
        )
        campaign_id = _campaign_id_from_header(headers)
        state = scope.setdefault("state", {})
        if not isinstance(state, dict):
            state = {}
            scope["state"] = state
        state["request_id"] = request_id
        state["campaign_id"] = campaign_id

        status_code = 500
        started_at = time.perf_counter()
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "")

        async def send_with_request_id(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                response_headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != _REQUEST_ID_HEADER
                ]
                response_headers.append(
                    (_REQUEST_ID_HEADER, request_id.encode("ascii"))
                )
                message = {**message, "headers": response_headers}
            await send(message)

        with bind_log_context(
            request_id=request_id,
            campaign_id=campaign_id,
        ):
            try:
                await self.app(scope, receive, send_with_request_id)
            finally:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
                logger.info(
                    "api.request.completed",
                    extra={
                        "http_method": method,
                        "http_path": path,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                        "error_type": None,
                    },
                )
