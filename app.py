from api.runtime_context import (
    _current_runtime,
    campaign_repository,
    campaign_state_service,
    campaign_turn_service,
    character_creation_service,
    character_repository,
    combat_encounter_service,
    context_builder,
    entity_repository,
    memory_search_service,
    silly_tavern_integration_service,
    turn_execution_lock,
    turn_repository,
    world_service,
)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers.campaign import router as campaign_router
from api.routers.system import router as system_router
from api.routers.turns import router as turns_router
from api.routers.memory import router as memory_router
from api.routers.integration import router as integration_router
from api.routers.world import router as world_router
from api.routers.character import router as character_router
from api.routers.combat import router as combat_router
from api.routers.effects import router as effects_router
from api.routers.clock import router as clock_router

from database import init_db
from repositories.turn_repository import TurnRepository
from services.campaign_runtime import CampaignRuntimeFactory
from services.campaign_state_service import CampaignStateService
from services.campaign_turn_service import CampaignTurnService
from services.context_builder import ContextBuilder
from services.dm_service import DMService
from services.llm_world_extractor import LLMWorldExtractor
from services.mechanics_adjudicator import MechanicsAdjudicator
from services.memory_search_service import MemorySearchService
from services.ollama_provider import OllamaProvider
from services.operation_parser import (
    OperationParser,
)
from services.turn_execution_lock import TurnExecutionLock
from services.turn_resolution_service import (
    TurnResolutionService,
)
from services.world_service import WorldService

__all__ = [
    "app",
    "runtime_factory",
    "create_world_service",
    "create_context_builder",
    "create_campaign_turn_service",
    "campaign_repository",
    "campaign_state_service",
    "campaign_turn_service",
    "character_creation_service",
    "character_repository",
    "combat_encounter_service",
    "context_builder",
    "entity_repository",
    "memory_search_service",
    "silly_tavern_integration_service",
    "turn_execution_lock",
    "turn_repository",
    "world_service",
]

app = FastAPI(
    title="D&D Campaign Manager",
    version="0.1.0",
)


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


# ============================================================
# APPLICATION SERVICES
# ============================================================


def create_world_service() -> WorldService:
    """
    Crea el WorldService y carga el WorldState persistido.
    """

    init_db()

    service = WorldService()

    service.load()

    return service

def create_context_builder(
    memory_search_service: MemorySearchService,
) -> ContextBuilder:
    """
    Construye el único ContextBuilder compartido por la aplicación.

    ContextBuilder es responsable de transformar candidatos de
    memoria en contexto relevante para el LLM.
    """

    if not isinstance(
        memory_search_service,
        MemorySearchService,
    ):
        raise TypeError(
            "memory_search_service must be a MemorySearchService"
        )

    return ContextBuilder(
        memory_search_service=memory_search_service,
    )


def create_campaign_turn_service(
    world_service: WorldService,
    context_builder: ContextBuilder,
    campaign_state_service: CampaignStateService,
    turn_repository: TurnRepository | None = None,
    *,
    turn_execution_lock: TurnExecutionLock,
) -> CampaignTurnService:
    """
    Construye el pipeline completo de resolución de turnos.

    Dependencias compartidas:

        MemorySearchService
                ↓
        ContextBuilder
                ↓
            DMService

    Flujo del turno:

        jugador
        ↓
        CampaignTurnService
        ↓
        TurnResolutionService
        ↓
        DMService
        ↓
        ContextBuilder
        ↓
        Ollama
        ↓
        narrativa
        ↓
        LLMWorldExtractor
        ↓
        operaciones
        ↓
        WorldService
        ↓
        SQLite
    """

    if not isinstance(
        world_service,
        WorldService,
    ):
        raise TypeError(
            "world_service must be a WorldService"
        )

    if not isinstance(
        context_builder,
        ContextBuilder,
    ):
        raise TypeError(
            "context_builder must be a ContextBuilder"
        )

    if not isinstance(
        campaign_state_service,
        CampaignStateService,
    ):
        raise TypeError(
            "campaign_state_service must be a CampaignStateService"
        )

    if turn_repository is not None and not isinstance(
        turn_repository,
        TurnRepository,
    ):
        raise TypeError(
            "turn_repository must be a TurnRepository"
        )

    provider = OllamaProvider()

    operation_parser = OperationParser()

    dm_service = DMService(
        provider=provider,
        context_builder=context_builder,
    )

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=operation_parser,
    )

    turn_resolution_service = TurnResolutionService(
        dm_service=dm_service,
        world_service=world_service,
        extractor=extractor,
        mechanics_adjudicator=MechanicsAdjudicator(provider, context_builder),
    )

    return CampaignTurnService(
        turn_resolution_service=turn_resolution_service,
        world_service=world_service,
        campaign_state_service=campaign_state_service,
        turn_repository=turn_repository,
        turn_execution_lock=turn_execution_lock,
    )


# ============================================================
# CAMPAIGN RUNTIME / REQUEST SCOPE
# ============================================================

runtime_factory = CampaignRuntimeFactory()
@app.middleware("http")
async def bind_campaign_runtime(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in {"/", "/health", "/ready", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect", "/campaigns"}:
        return await call_next(request)

    raw_campaign_id = request.headers.get("X-Campaign-Id")
    if raw_campaign_id is None:
        return JSONResponse(
            status_code=400,
            content={"detail": "X-Campaign-Id header is required"},
        )

    try:
        campaign_id = int(raw_campaign_id)
        runtime = runtime_factory.get_runtime(campaign_id)
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={"detail": "X-Campaign-Id must be a positive integer"},
        )
    except LookupError:
        return JSONResponse(
            status_code=404,
            content={"detail": "campaign does not exist"},
        )

    token = _current_runtime.set(runtime)
    try:
        return await call_next(request)
    finally:
        _current_runtime.reset(token)


# API capability routers
app.include_router(system_router)
app.include_router(campaign_router)
app.include_router(turns_router)
app.include_router(memory_router)
app.include_router(integration_router)
app.include_router(world_router)
app.include_router(character_router)
app.include_router(combat_router)
app.include_router(effects_router)
app.include_router(clock_router)


from api.runtime_context import (
    _current_runtime,
    campaign_repository,
    campaign_state_service,
    campaign_turn_service,
    character_creation_service,
    character_repository,
    combat_encounter_service,
    context_builder,
    entity_repository,
    memory_search_service,
    silly_tavern_integration_service,
    turn_execution_lock,
    turn_repository,
    world_service,
)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers.campaign import router as campaign_router
from api.routers.system import router as system_router
from api.routers.turns import router as turns_router
from api.routers.memory import router as memory_router

from database import init_db
from models.campaign_clock_api_schemas import CampaignClockAdvanceIn
from models.combat_api_schemas import (
    EncounterAttackIn,
    EncounterCreateIn,
    EncounterStartIn,
    EncounterTurnIn,
)
from models.persistent_effect_api_schemas import (
    PersistentEffectCreateIn,
    PersistentEffectStatusIn,
)
from models.schemas import (
    CharacterCreate,
    SillyTavernContextIn,
    SillyTavernTurnIn,
)
from repositories.turn_repository import TurnRepository
from services.campaign_runtime import CampaignRuntime, CampaignRuntimeFactory
from services.campaign_state_service import CampaignStateService
from services.campaign_turn_service import (
    CampaignTurnService,
    CampaignTurnServiceError,
)
from services.context_builder import ContextBuilder
from services.dm_service import DMService
from services.llm_world_extractor import LLMWorldExtractor
from services.mechanics_adjudicator import MechanicsAdjudicator
from services.memory_search_service import MemorySearchService
from services.ollama_provider import OllamaProvider
from services.operation_parser import (
    OperationParser,
)
from services.silly_tavern_integration_service import (
    SillyTavernIntegrationServiceConflictError,
    SillyTavernIntegrationServiceError,
)
from services.turn_execution_lock import TurnExecutionLock
from services.turn_resolution_service import (
    TurnResolutionService,
)
from services.world_service import WorldService

app = FastAPI(
    title="D&D Campaign Manager",
    version="0.1.0",
)


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


# ============================================================
# APPLICATION SERVICES
# ============================================================


def create_world_service() -> WorldService:
    """
    Crea el WorldService y carga el WorldState persistido.
    """

    init_db()

    service = WorldService()

    service.load()

    return service

def create_context_builder(
    memory_search_service: MemorySearchService,
) -> ContextBuilder:
    """
    Construye el único ContextBuilder compartido por la aplicación.

    ContextBuilder es responsable de transformar candidatos de
    memoria en contexto relevante para el LLM.
    """

    if not isinstance(
        memory_search_service,
        MemorySearchService,
    ):
        raise TypeError(
            "memory_search_service must be a MemorySearchService"
        )

    return ContextBuilder(
        memory_search_service=memory_search_service,
    )


def create_campaign_turn_service(
    world_service: WorldService,
    context_builder: ContextBuilder,
    campaign_state_service: CampaignStateService,
    turn_repository: TurnRepository | None = None,
    *,
    turn_execution_lock: TurnExecutionLock,
) -> CampaignTurnService:
    """
    Construye el pipeline completo de resolución de turnos.

    Dependencias compartidas:

        MemorySearchService
                ↓
        ContextBuilder
                ↓
            DMService

    Flujo del turno:

        jugador
        ↓
        CampaignTurnService
        ↓
        TurnResolutionService
        ↓
        DMService
        ↓
        ContextBuilder
        ↓
        Ollama
        ↓
        narrativa
        ↓
        LLMWorldExtractor
        ↓
        operaciones
        ↓
        WorldService
        ↓
        SQLite
    """

    if not isinstance(
        world_service,
        WorldService,
    ):
        raise TypeError(
            "world_service must be a WorldService"
        )

    if not isinstance(
        context_builder,
        ContextBuilder,
    ):
        raise TypeError(
            "context_builder must be a ContextBuilder"
        )

    if not isinstance(
        campaign_state_service,
        CampaignStateService,
    ):
        raise TypeError(
            "campaign_state_service must be a CampaignStateService"
        )

    if turn_repository is not None and not isinstance(
        turn_repository,
        TurnRepository,
    ):
        raise TypeError(
            "turn_repository must be a TurnRepository"
        )

    provider = OllamaProvider()

    operation_parser = OperationParser()

    dm_service = DMService(
        provider=provider,
        context_builder=context_builder,
    )

    extractor = LLMWorldExtractor(
        provider=provider,
        operation_parser=operation_parser,
    )

    turn_resolution_service = TurnResolutionService(
        dm_service=dm_service,
        world_service=world_service,
        extractor=extractor,
        mechanics_adjudicator=MechanicsAdjudicator(provider, context_builder),
    )

    return CampaignTurnService(
        turn_resolution_service=turn_resolution_service,
        world_service=world_service,
        campaign_state_service=campaign_state_service,
        turn_repository=turn_repository,
        turn_execution_lock=turn_execution_lock,
    )


# ============================================================
# CAMPAIGN RUNTIME / REQUEST SCOPE
# ============================================================

runtime_factory = CampaignRuntimeFactory()
def _get_active_runtime() -> CampaignRuntime:
    runtime = _current_runtime.get()
    if runtime is None:
        raise RuntimeError(
            "campaign runtime is only available inside an HTTP request"
        )
    return runtime




@app.middleware("http")
async def bind_campaign_runtime(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in {"/", "/health", "/ready", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect", "/campaigns"}:
        return await call_next(request)

    raw_campaign_id = request.headers.get("X-Campaign-Id")
    if raw_campaign_id is None:
        return JSONResponse(
            status_code=400,
            content={"detail": "X-Campaign-Id header is required"},
        )

    try:
        campaign_id = int(raw_campaign_id)
        runtime = runtime_factory.get_runtime(campaign_id)
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={"detail": "X-Campaign-Id must be a positive integer"},
        )
    except LookupError:
        return JSONResponse(
            status_code=404,
            content={"detail": "campaign does not exist"},
        )

    token = _current_runtime.set(runtime)
    try:
        return await call_next(request)
    finally:
        _current_runtime.reset(token)


# API capability routers
app.include_router(system_router)
app.include_router(campaign_router)
app.include_router(turns_router)
app.include_router(memory_router)
