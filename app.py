from contextvars import ContextVar

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import init_db
from models.campaign_scope import CampaignScope
from models.schemas import (
    ActiveCharacterUpdate,
    CampaignCreate,
    CampaignSessionUpdate,
    CampaignUpdate,
    CharacterCreate,
    SessionIn,
    SillyTavernContextIn,
    SillyTavernTurnIn,
    TurnIn,
)
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from repositories.turn_repository import TurnRepository
from services.campaign_runtime import CampaignRuntime, CampaignRuntimeFactory
from services.campaign_state_service import CampaignStateService
from services.campaign_turn_service import (
    CampaignTurnService,
    CampaignTurnServiceError,
)
from services.character_creation_service import CharacterCreationService
from services.context_builder import ContextBuilder
from services.dm_service import DMService
from services.llm_world_extractor import LLMWorldExtractor
from services.memory_search_service import MemorySearchService
from services.ollama_provider import OllamaProvider
from services.operation_parser import (
    OperationParser,
)
from services.silly_tavern_integration_service import (
    SillyTavernIntegrationService,
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
_current_runtime: ContextVar[CampaignRuntime | None] = ContextVar(
    "campaign_runtime",
    default=None,
)


def _get_active_runtime() -> CampaignRuntime:
    runtime = _current_runtime.get()
    if runtime is None:
        return runtime_factory.get_runtime(1)
    return runtime


class _RuntimeProxy:
    """Compatibilidad temporal: delega cada acceso al runtime de la petición."""

    def __init__(self, attribute: str) -> None:
        self._attribute = attribute

    def __getattr__(self, name: str):
        runtime = _get_active_runtime()
        return getattr(getattr(runtime, self._attribute), name)


campaign_repository = _RuntimeProxy("campaign_repository")
character_repository = _RuntimeProxy("character_repository")
entity_repository = _RuntimeProxy("entity_repository")
turn_repository = _RuntimeProxy("turn_repository")
world_service = _RuntimeProxy("world_service")
campaign_state_service = _RuntimeProxy("campaign_state_service")
memory_search_service = _RuntimeProxy("memory_search_service")
context_builder = _RuntimeProxy("context_builder")
turn_execution_lock = _RuntimeProxy("turn_execution_lock")
character_creation_service = _RuntimeProxy("character_creation_service")
campaign_turn_service = _RuntimeProxy("campaign_turn_service")
silly_tavern_integration_service = _RuntimeProxy(
    "silly_tavern_integration_service"
)


@app.middleware("http")
async def bind_campaign_runtime(request: Request, call_next):
    if request.url.path in {"/", "/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect", "/campaigns"}:
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


# ============================================================
# BASIC
# ============================================================


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "D&D Campaign Manager",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {
        "ok": True,
    }


# ============================================================
# CAMPAIGN
# ============================================================

@app.get("/campaigns")
def list_campaigns():
    return campaign_repository.list_campaigns()


@app.post("/campaigns", status_code=201)
def create_campaign(data: CampaignCreate):
    try:
        return campaign_repository.create_campaign(
            name=data.name,
            system=data.system,
            tone=data.tone,
            summary=data.summary,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="failed to create campaign",
        ) from exc



@app.patch("/campaign")
def update_campaign(data: CampaignUpdate):

    with turn_execution_lock.acquire():

        current = campaign_repository.get_campaign(_current_runtime.get().campaign_id)

        values = {
            "name": (
                data.name
                if data.name is not None
                else current["name"]
            ),
            "system": (
                data.system
                if data.system is not None
                else current["system"]
            ),
            "tone": (
                data.tone
                if data.tone is not None
                else current["tone"]
            ),
            "summary": (
                data.summary
                if data.summary is not None
                else current["summary"]
            ),
        }

        return campaign_repository.update_campaign(
            campaign_id=_current_runtime.get().campaign_id,
            **values,
        )


@app.patch("/campaign/session")
def update_campaign_session(
    data: CampaignSessionUpdate,
):

    try:
        with turn_execution_lock.acquire():
            state = (
                campaign_state_service.set_current_session(
                    data.session_id
                )
            )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "campaign_id": state.campaign_id,
        "current_session_id": (
            state.current_session_id
        ),
    }


@app.post("/sessions")
def create_session(data: SessionIn):

    with turn_execution_lock.acquire():
        return campaign_repository.create_session(
            **data.model_dump(),
            campaign_id=_current_runtime.get().campaign_id,
        )

@app.get("/campaign/state")
def get_campaign_state():

    try:
        state = campaign_state_service.get_state()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    return {
        "campaign_id": state.campaign_id,
        "name": state.name,
        "system": state.system,
        "tone": state.tone,
        "current_location_id": state.current_location_id,
        "current_session_id": state.current_session_id,
        "active_character_id": state.active_character_id,
        "summary": state.summary,
    }

@app.patch("/campaign/active-character")
def update_active_character(
    data: ActiveCharacterUpdate,
):

    try:
        with turn_execution_lock.acquire():
            state = (
                campaign_state_service.set_active_character(
                    data.character_id
                )
            )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "campaign_id": state.campaign_id,
        "active_character_id": (
            state.active_character_id
        ),
    }

# ============================================================
# TURN
# ============================================================


@app.post("/turn")
def play_turn(data: TurnIn):

    try:
        result = campaign_turn_service.play_turn(
            data.player_input
        )

    except CampaignTurnServiceError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "narrative": result.narrative,
        "player_input": result.player_input,
        "operation_count": result.operation_count,
        "successful_operation_count": (
            result.successful_operation_count
        ),
        "failed_operation_count": (
            result.failed_operation_count
        ),
        "all_operations_succeeded": (
            result.all_operations_succeeded
        ),
        "world_changed": result.world_changed,
        "operations": [
            type(operation).__name__
            for operation in result.operations
        ],
        "operation_results": [
            _serialize_operation_result(
                operation_result
            )
            for operation_result
            in result.operation_results
        ],
    }

@app.get("/turns")
def get_turns(
    session_id: int | None = Query(
        default=None,
        ge=1,
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
):
    turns = turn_repository.list_turns(
        session_id=session_id,
        limit=limit,
        scope=_current_runtime.get().scope,
    )

    return [
        {
            "id": turn.id,
            "session_id": turn.session_id,
            "player_input": turn.player_input,
            "narrative": turn.narrative,
            "operation_count": (
                turn.operation_count
            ),
            "successful_operation_count": (
                turn.successful_operation_count
            ),
            "failed_operation_count": (
                turn.failed_operation_count
            ),
            "all_operations_succeeded": (
                turn.all_operations_succeeded
            ),
            "world_changed": (
                turn.world_changed
            ),
            "created_at": turn.created_at,
        }
        for turn in turns
    ]


# ============================================================
# MEMORY
# ============================================================


@app.get("/memory/search")
def search_memory(
    q: str = Query(
        ...,
        min_length=1,
        max_length=1000,
    ),
):

    with turn_execution_lock.acquire():

        world = world_service.get_world()

        return memory_search_service.search(
            world,
            q.strip(),
        )


@app.get("/memory/context")
def memory_context(
    q: str = Query(
        ...,
        min_length=1,
        max_length=1000,
    ),
):

    with turn_execution_lock.acquire():

        world = world_service.get_world()

        return context_builder.build(
            world,
            q.strip(),
        )


# ============================================================
# SILLYTAVERN INTEGRATION
# ============================================================


@app.post("/integration/context")
def get_silly_tavern_context(
    data: SillyTavernContextIn,
):
    """
    Devuelve el contexto persistente necesario para que
    SillyTavern genere la siguiente respuesta narrativa.
    """

    try:
        with turn_execution_lock.acquire():
            result = (
                silly_tavern_integration_service
                .get_context(
                    data.query
                )
            )

    except SillyTavernIntegrationServiceError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to build SillyTavern context",
        ) from exc

    return result


@app.get(
    "/integration/turn/{external_turn_id}"
)
def get_silly_tavern_turn_state(
    external_turn_id: str,
):
    """
    Devuelve la versión activa persistida de un turno externo.

    La extensión de SillyTavern utiliza este endpoint para
    reconstruir su caché local después de una recarga o cambio
    de chat.
    """

    try:
        with turn_execution_lock.acquire():
            result = (
                silly_tavern_integration_service
                .get_external_turn_state(
                    external_turn_id
                )
            )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except SillyTavernIntegrationServiceError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "failed to obtain "
                "SillyTavern turn state"
            ),
        ) from exc

    return result


@app.post("/integration/turn")
def process_silly_tavern_turn(
    data: SillyTavernTurnIn,
):
    """
    Procesa una narrativa que ya ha sido generada
    por SillyTavern.

    Campaign Manager:

        narrativa
            ↓
        extracción
            ↓
        operaciones
            ↓
        WorldService
            ↓
        SQLite
    """

    try:
        result = (
            silly_tavern_integration_service
            .process_turn(
                player_input=data.player_input,
                narrative=data.narrative,
                external_turn_id=data.external_turn_id,
                turn_version=data.turn_version,
            )
        )

    except SillyTavernIntegrationServiceConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except SillyTavernIntegrationServiceError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="failed to process SillyTavern turn",
        ) from exc

    return {
        "narrative": result.narrative,
        "player_input": result.player_input,
        "external_turn_id": data.external_turn_id,
        "turn_version": data.turn_version,
        "operation_count": (
            result.operation_count
        ),
        "successful_operation_count": (
            result.successful_operation_count
        ),
        "failed_operation_count": (
            result.failed_operation_count
        ),
        "all_operations_succeeded": (
            result.all_operations_succeeded
        ),
        "world_changed": (
            result.world_changed
        ),
        "operations": [
            type(operation).__name__
            for operation
            in (
                result.operations
                + result.character_operations
            )
        ],
        "operation_results": [
            _serialize_operation_result(
                operation_result
            )
            for operation_result
            in result.operation_results
        ],
    }

# ============================================================
# WORLD
# ============================================================

@app.get("/world")
def get_world():

    with turn_execution_lock.acquire():

        world = world_service.get_world()

        return {
            "entities": list(
                world.entities.values()
            ),
            "items": list(
                world.items.values()
            ),
            "item_instances": list(
                world.item_instances.values()
            ),
            "resources": list(
                world.resources.values()
            ),
            "resource_balances": list(
                world.resource_balances.values()
            ),
            "relations": list(
                world.relations.values()
            ),
            "events": list(
                world.events.values()
            ),
        }
# ============================================================
# EXPORT
# ============================================================


@app.get("/export")
def export_memory():
    """
    Exporta la representación pública actual de la campaña.

    WorldState es la fuente de verdad y MemorySearchService
    es responsable de aplicar las reglas de visibilidad y
    construir la representación estructurada exportable.
    """

    with turn_execution_lock.acquire():

        world = world_service.get_world()

        return memory_search_service.export(world)


# ============================================================
# SERIALIZATION
# ============================================================


def _serialize_operation_result(
    result,
):
    return {
        "status": result.status.value,
        "message": result.message,
        "operation": (
            type(result.operation).__name__
            if result.operation is not None
            else None
        ),
    }

@app.post("/characters")
def create_character(
    data: CharacterCreate,
    activate: bool = True,
):
    try:
        character = character_creation_service.create_character(
            campaign_id=_current_runtime.get().campaign_id,
            data=data,
            activate=activate,
        )

        return {
            "character": character,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

@app.post("/campaign/bootstrap")
def bootstrap_campaign(
    data: CharacterCreate,
):
    try:
        character = character_creation_service.create_character(
            campaign_id=_current_runtime.get().campaign_id,
            data=data,
            activate=True,
        )

        return {
            "campaign_id": _current_runtime.get().campaign_id,
            "character": character,
            "active_character_id": character.entity_id,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )