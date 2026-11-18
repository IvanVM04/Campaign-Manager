from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.errors import error_response, register_error_handlers
from api.routers.campaign import router as campaign_router
from api.routers.character import router as character_router
from api.routers.clock import router as clock_router
from api.routers.combat import router as combat_router
from api.routers.dice import router as dice_router
from api.routers.effects import router as effects_router
from api.routers.integration import router as integration_router
from api.routers.memory import router as memory_router
from api.routers.system import router as system_router
from api.routers.turns import router as turns_router
from api.routers.world import router as world_router
from api.runtime_context import bind_current_runtime
from bootstrap.campaign_runtime import CampaignRuntimeFactory
from observability import configure_logging
from observability.middleware import RequestObservabilityMiddleware
from services.providers import LLMSettings

configure_logging()

DEFAULT_LLM_SETTINGS = LLMSettings.from_env()
runtime_factory = CampaignRuntimeFactory(llm_settings=DEFAULT_LLM_SETTINGS)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Release process-local campaign runtimes when the API shuts down."""
    try:
        yield
    finally:
        runtime_factory.shutdown()


app = FastAPI(
    title="D&D Campaign Manager",
    version="0.1.0",
    lifespan=lifespan,
)
register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def bind_campaign_runtime(request: Request, call_next):
    public_paths = {
        "/",
        "/health",
        "/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/docs/oauth2-redirect",
        "/campaigns",
    }
    if request.method == "OPTIONS" or request.url.path in public_paths:
        return await call_next(request)

    raw_campaign_id = request.headers.get("X-Campaign-Id")
    if raw_campaign_id is None:
        return error_response(
            status_code=400,
            code="bad_request",
            detail="X-Campaign-Id header is required",
        )

    try:
        campaign_id = int(raw_campaign_id)
        runtime = runtime_factory.get_runtime(campaign_id)
    except (TypeError, ValueError):
        return error_response(
            status_code=400,
            code="bad_request",
            detail="X-Campaign-Id must be a positive integer",
        )
    except LookupError:
        return error_response(
            status_code=404,
            code="not_found",
            detail="campaign does not exist",
        )

    with bind_current_runtime(runtime):
        return await call_next(request)


# Registered last so the request context wraps campaign selection and error handling.
app.add_middleware(RequestObservabilityMiddleware)

app.include_router(system_router)
app.include_router(campaign_router)
app.include_router(turns_router)
app.include_router(dice_router)
app.include_router(memory_router)
app.include_router(integration_router)
app.include_router(world_router)
app.include_router(character_router)
app.include_router(combat_router)
app.include_router(effects_router)
app.include_router(clock_router)


__all__ = [
    "app",
    "runtime_factory",
]
