from __future__ import annotations

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
from api.routers.turns import _serialize_mechanics_result
from api.routers.turns import router as turns_router
from api.routers.world import router as world_router
from api.runtime_context import bind_current_runtime
from bootstrap.campaign_runtime import CampaignRuntimeFactory
from database import init_db
from services.context import ContextBuilder, MemorySearchService
from services.providers import LLMSettings
from services.world import WorldService

app = FastAPI(
    title="D&D Campaign Manager",
    version="0.1.0",
)
register_error_handlers(app)

DEFAULT_LLM_SETTINGS = LLMSettings.from_env()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def create_world_service() -> WorldService:
    """Create a WorldService and load its persisted WorldState."""
    init_db()
    service = WorldService()
    service.load()
    return service


def create_context_builder(
    memory_search_service: MemorySearchService,
) -> ContextBuilder:
    """Build the shared ContextBuilder for the supplied memory service."""
    if not isinstance(memory_search_service, MemorySearchService):
        raise TypeError(
            "memory_search_service must be a MemorySearchService"
        )

    return ContextBuilder(
        memory_search_service=memory_search_service,
    )


runtime_factory = CampaignRuntimeFactory(llm_settings=DEFAULT_LLM_SETTINGS)


@app.on_event("shutdown")
def shutdown_campaign_runtimes() -> None:
    """Libera el estado en memoria asociado a las campañas."""
    runtime_factory.shutdown()


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
    "_serialize_mechanics_result",
    "app",
    "create_context_builder",
    "create_world_service",
    "runtime_factory",
]
