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

# ============================================================
# D&D COMBAT ENCOUNTERS
# ============================================================


def _encounter_payload(encounter):
    active = encounter.active_combatant
    return {
        "encounter_id": encounter.encounter_id,
        "status": encounter.status.value,
        "round_number": encounter.round_number,
        "turn_index": encounter.turn_index,
        "initiative_order": list(encounter.initiative_order),
        "active_combatant_id": active.combatant_id if active else None,
        "tied_initiative_groups": [
            list(group) for group in encounter.tied_initiative_groups
        ],
        "combatants": {
            combatant_id: {
                "combatant_id": combatant.combatant_id,
                "name": combatant.name,
                "initiative": combatant.initiative,
                "current_hp": combatant.current_hp,
                "max_hp": combatant.max_hp,
                "armor_class": combatant.armor_class,
                "dexterity": combatant.dexterity,
                "action_used": combatant.action_used,
                "entity_id": combatant.entity_id,
                "is_player_character": combatant.is_player_character,
                "conscious": combatant.conscious,
                "defeated": combatant.defeated,
                "conditions": sorted(
                    condition.value for condition in combatant.conditions.conditions
                ),
                "exhaustion_level": combatant.conditions.exhaustion_level,
            }
            for combatant_id, combatant in encounter.combatants.items()
        },
    }


@app.get("/encounters")
def list_combat_encounters():
    return [
        _encounter_payload(encounter)
        for encounter in combat_encounter_service.list(
            _current_runtime.get().campaign_id
        )
    ]


@app.post("/encounters", status_code=201)
def create_combat_encounter(data: EncounterCreateIn):
    try:
        with turn_execution_lock.acquire():
            encounter = combat_encounter_service.create(
                _current_runtime.get().campaign_id,
                data.participants,
                data.encounter_id,
            )
        return _encounter_payload(encounter)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/encounters/{encounter_id}")
def get_combat_encounter(encounter_id: str):
    try:
        encounter = combat_encounter_service.get(
            _current_runtime.get().campaign_id,
            encounter_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if encounter is None:
        raise HTTPException(status_code=404, detail="encounter not found")
    return _encounter_payload(encounter)


@app.post("/encounters/{encounter_id}/start")
def start_combat_encounter(encounter_id: str, data: EncounterStartIn):
    try:
        with turn_execution_lock.acquire():
            encounter = combat_encounter_service.start(
                _current_runtime.get().campaign_id,
                encounter_id,
                dice_mode=data.dice_mode,
                manual_rolls=data.manual_rolls,
                initiative_order=(
                    tuple(data.initiative_order)
                    if data.initiative_order is not None
                    else None
                ),
            )
        return _encounter_payload(encounter)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/encounters/{encounter_id}/advance")
def advance_combat_encounter(encounter_id: str, data: EncounterTurnIn):
    try:
        with turn_execution_lock.acquire():
            encounter = combat_encounter_service.advance_turn(
                _current_runtime.get().campaign_id,
                encounter_id,
                expected_round=data.expected_round,
                expected_turn_index=data.expected_turn_index,
            )
        return _encounter_payload(encounter)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/encounters/{encounter_id}/complete")
def complete_combat_encounter(encounter_id: str, data: EncounterTurnIn):
    try:
        with turn_execution_lock.acquire():
            encounter = combat_encounter_service.complete(
                _current_runtime.get().campaign_id,
                encounter_id,
                expected_round=data.expected_round,
                expected_turn_index=data.expected_turn_index,
            )
        return _encounter_payload(encounter)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc




@app.post("/encounters/{encounter_id}/attack")
def attack_in_combat_encounter(encounter_id: str, data: EncounterAttackIn):
    try:
        with turn_execution_lock.acquire():
            result = _current_runtime.get().combat_attack_service.attack(
                campaign_id=_current_runtime.get().campaign_id,
                encounter_id=encounter_id,
                target_combatant_id=data.target_combatant_id,
                expected_round=data.expected_round,
                expected_turn_index=data.expected_turn_index,
                dice_mode=data.dice_mode,
                manual_attack_rolls=(
                    tuple(data.manual_attack_rolls)
                    if data.manual_attack_rolls is not None else None
                ),
                manual_damage_rolls=(
                    tuple(data.manual_damage_rolls)
                    if data.manual_damage_rolls is not None else None
                ),
                target_within_5_feet=data.target_within_5_feet,
                versatile_two_handed=data.versatile_two_handed,
                finesse_ability=data.finesse_ability,
            )
        attack = result["result"]
        damage_roll = attack.damage_roll
        return {
            "encounter": _encounter_payload(result["encounter"]),
            "attacker_combatant_id": result["attacker_combatant_id"],
            "target_combatant_id": result["target_combatant_id"],
            "weapon_key": result["weapon_key"],
            "attack_ability": result["attack_ability"],
            "attack_bonus": result["attack_bonus"],
            "proficient": result["proficient"],
            "advantage": result["advantage"],
            "disadvantage": result["disadvantage"],
            "attack": {
                "rolls": list(attack.attack_roll.rolls),
                "selected": attack.attack_roll.selected,
                "total": attack.attack_roll.total,
                "target_ac": attack.target_ac,
                "hit": attack.hit,
                "critical": attack.critical,
            },
            "damage": {
                "type": attack.damage_type.value,
                "rolls": list(damage_roll.rolls) if damage_roll else [],
                "raw": attack.raw_damage,
                "after_defenses": attack.damage_after_defenses,
                "target_current_hp": result["target_current_hp"],
            },
        }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc



# ============================================================
# PERSISTENT CAMPAIGN EFFECTS
# ============================================================


def _persistent_effect_payload(effect):
    return {
        "id": effect.id,
        "campaign_id": effect.campaign_id,
        "entity_id": effect.entity_id,
        "effect_type": effect.effect_type.value,
        "effect_key": effect.effect_key,
        "name": effect.name,
        "description": effect.description,
        "source_type": effect.source_type.value,
        "source_entity_id": effect.source_entity_id,
        "source_reference": effect.source_reference,
        "duration_type": effect.duration_type.value,
        "duration_condition": effect.duration_condition,
        "duration_minutes": effect.duration_minutes,
        "expires_at_minute": effect.expires_at_minute,
        "expired_at_minute": effect.expired_at_minute,
        "level": effect.level,
        "status": effect.status.value,
        "created_at": effect.created_at,
        "updated_at": effect.updated_at,
        "removed_at": effect.removed_at,
    }


@app.get("/entities/{entity_id}/effects")
def list_entity_effects(
    entity_id: int,
    include_removed: bool = False,
):
    try:
        effects = _current_runtime.get().persistent_effect_service.list_for_entity(
            entity_id,
            include_removed=include_removed,
        )
        return [_persistent_effect_payload(effect) for effect in effects]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/entities/{entity_id}/effects", status_code=201)
def create_entity_effect(entity_id: int, data: PersistentEffectCreateIn):
    try:
        with turn_execution_lock.acquire():
            effect = _current_runtime.get().persistent_effect_service.create(
                entity_id=entity_id,
                effect_type=data.effect_type,
                effect_key=data.effect_key,
                name=data.name,
                description=data.description,
                source_type=data.source_type,
                source_entity_id=data.source_entity_id,
                source_reference=data.source_reference,
                duration_type=data.duration_type,
                duration_condition=data.duration_condition,
                duration_minutes=data.duration_minutes,
                level=data.level,
            )
        return _persistent_effect_payload(effect)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/effects/{effect_id}/status")
def update_persistent_effect_status(
    effect_id: str,
    data: PersistentEffectStatusIn,
):
    try:
        with turn_execution_lock.acquire():
            effect = _current_runtime.get().persistent_effect_service.set_status(
                effect_id,
                data.status,
            )
        return _persistent_effect_payload(effect)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/effects/{effect_id}")
def remove_persistent_effect(effect_id: str):
    try:
        with turn_execution_lock.acquire():
            effect = _current_runtime.get().persistent_effect_service.remove(
                effect_id
            )
        return _persistent_effect_payload(effect)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ============================================================
# CAMPAIGN CLOCK
# ============================================================

def _campaign_clock_payload(clock):
    return {
        "campaign_id": clock.campaign_id,
        "elapsed_minutes": clock.elapsed_minutes,
        "version": clock.version,
        "updated_at": clock.updated_at,
    }


@app.get("/campaign/clock")
def get_campaign_clock():
    from services.campaign_clock_service import CampaignClockService

    try:
        clock = CampaignClockService(
            campaign_id=_current_runtime.get().campaign_id
        ).get()
        return _campaign_clock_payload(clock)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/campaign/clock/advance")
def advance_campaign_clock(data: CampaignClockAdvanceIn):
    from services.campaign_clock_service import CampaignClockService

    try:
        with turn_execution_lock.acquire():
            clock = CampaignClockService(
                campaign_id=_current_runtime.get().campaign_id
            ).advance(
                minutes=data.minutes,
                expected_elapsed_minutes=data.expected_elapsed_minutes,
            )
        return _campaign_clock_payload(clock)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
