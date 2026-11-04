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
        return error_response(
            status_code=exc.status_code,
            code=_code_for_status(exc.status_code),
            detail=exc.detail,
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
