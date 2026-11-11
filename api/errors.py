from __future__ import annotations

HTTP_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    502: "upstream_invalid_response",
    503: "service_unavailable",
}


class APIError(Exception):
    """An application-facing error with a stable public code and HTTP status."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.headers = headers


def api_error_for_exception(
    exc: Exception,
    *,
    fallback_status: int = 500,
    fallback_code: str | None = None,
    fallback_detail: str = "Internal server error",
) -> APIError:
    """Map a wrapped application failure to a stable public API error.

    The exception chain is inspected from the outermost error inward so
    orchestration wrappers do not hide provider or model-response failures.
    """
    from services.llm_world import LLMExtractionError
    from services.turns.mechanics_adjudicator import MechanicsAdjudicatorError
    from services.providers import LLMProviderError
    from services.turns.turn_resolution_service import TurnResolutionServiceError

    chain: list[BaseException] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__

    # Provider outages take precedence over wrappers such as
    # TurnResolutionServiceError and DurableNativeTurnError.
    if any(isinstance(item, LLMProviderError) for item in chain):
        return APIError(
            status_code=503,
            code="llm_provider_unavailable",
            detail="The language model provider is temporarily unavailable.",
        )
    if any(
        isinstance(item, (LLMExtractionError, MechanicsAdjudicatorError))
        for item in chain
    ):
        return APIError(
            status_code=502,
            code="invalid_llm_response",
            detail="The language model returned a response that could not be safely processed.",
        )
    if any(isinstance(item, TurnResolutionServiceError) for item in chain):
        return APIError(
            status_code=500,
            code="turn_resolution_failed",
            detail="The turn could not be resolved because of an internal error.",
        )

    return APIError(
        status_code=fallback_status,
        code=fallback_code or _code_for_status(fallback_status),
        detail=fallback_detail,
    )


def error_response(
    *,
    status_code: int,
    code: str,
    detail: object,
    headers: dict[str, str] | None = None,
):
    """Build the backwards-compatible, machine-readable API error body."""
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status_code,
        content={
            "detail": jsonable_encoder(detail),
            "code": code,
        },
        headers=headers,
    )


def _code_for_status(status_code: int) -> str:
    if status_code in HTTP_ERROR_CODES:
        return HTTP_ERROR_CODES[status_code]
    if status_code >= 500:
        return "internal_error"
    return "http_error"


def register_error_handlers(app: object) -> None:
    """Install consistent error responses without exposing internal failures."""
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(APIError)
    async def handle_api_error(
        request: Request,
        exc: APIError,
    ) -> JSONResponse:
        detail = exc.detail
        if exc.status_code >= 500 and exc.status_code != 503:
            detail = "Internal server error"
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            detail=detail,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        public_errors = [
            {
                "loc": error["loc"],
                "msg": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return error_response(
            status_code=422,
            code="validation_error",
            detail=public_errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        detail = exc.detail
        if exc.status_code >= 500 and exc.status_code != 503:
            detail = (
                "Bad gateway"
                if exc.status_code == 502
                else "Internal server error"
            )
        return error_response(
            status_code=exc.status_code,
            code=_code_for_status(exc.status_code),
            detail=detail,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        import logging

        logging.getLogger(__name__).exception(
            "Unhandled API exception",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return error_response(
            status_code=500,
            code="internal_error",
            detail="Internal server error",
        )
