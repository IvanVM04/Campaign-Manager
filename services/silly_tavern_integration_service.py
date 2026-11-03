from __future__ import annotations

from dataclasses import replace

from database import get_conn
from models.campaign_scope import CampaignScope
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.turn_resolution_result import TurnResolutionResult
from repositories.turn_repository import TurnRepository
from repositories.world_snapshot_repository import (
    WorldSnapshotRepository,
)
from services.campaign_state_service import (
    CampaignStateService,
    CampaignStateServiceError,
)
from services.context_builder import ContextBuilder
from services.llm_world_extractor import (
    LLMExtractionError,
    LLMWorldExtractor,
)
from services.turn_execution_lock import TurnExecutionLock
from services.world_service import WorldService


class SillyTavernIntegrationServiceError(RuntimeError):
    """
    Error base de la integración con SillyTavern.
    """


class SillyTavernIntegrationServiceConflictError(
    SillyTavernIntegrationServiceError
):
    """
    Conflicto de idempotencia.

    Ocurre cuando un external_turn_id ya existe pero
    pertenece a un payload diferente.
    """


class SillyTavernIntegrationService:
    """
    Integra SillyTavern con Campaign Manager.

    SillyTavern es responsable de generar la narrativa.

    Campaign Manager es responsable de:

        - proporcionar contexto persistente
        - proporcionar el estado actual de la campaña
        - extraer cambios persistentes de la narrativa
        - aplicar las operaciones al mundo
        - persistir el turno

    Flujo:

        SillyTavern
             |
             | contexto
             v
        ContextBuilder
             |
             | contexto
             v
        SillyTavern
             |
             | player_input + narrative
             v
        LLMWorldExtractor
             |
             v
        WorldService
             |
             v
        TurnRepository

    Este servicio NO:

        - genera narrativa
        - conoce Ollama
        - construye prompts narrativos
        - modifica directamente SQLite
        - implementa reglas de dominio
    """

    def __init__(
        self,
        *,
        campaign_state_service: CampaignStateService,
        context_builder: ContextBuilder,
        extractor: LLMWorldExtractor,
        world_service: WorldService,
        turn_repository: TurnRepository,
        turn_execution_lock: TurnExecutionLock,
    ) -> None:

        if not isinstance(
            campaign_state_service,
            CampaignStateService,
        ):
            raise TypeError(
                "campaign_state_service must be a "
                "CampaignStateService"
            )

        if not isinstance(
            context_builder,
            ContextBuilder,
        ):
            raise TypeError(
                "context_builder must be a ContextBuilder"
            )

        if not isinstance(
            extractor,
            LLMWorldExtractor,
        ):
            raise TypeError(
                "extractor must be a LLMWorldExtractor"
            )

        if not isinstance(
            world_service,
            WorldService,
        ):
            raise TypeError(
                "world_service must be a WorldService"
            )

        if not isinstance(
            turn_repository,
            TurnRepository,
        ):
            raise TypeError(
                "turn_repository must be a TurnRepository"
            )

        if not isinstance(
            turn_execution_lock,
            TurnExecutionLock,
        ):
            raise TypeError(
                "turn_execution_lock must be a TurnExecutionLock"
            )

        self.turn_execution_lock = turn_execution_lock

        self.campaign_state_service = (
            campaign_state_service
        )

        self.context_builder = context_builder

        self.extractor = extractor

        self.world_service = world_service

        self.turn_repository = turn_repository

        self.world_snapshot_repository = WorldSnapshotRepository()
        self.campaign_scope = CampaignScope(world_service.campaign_id)


    # ============================================================
    # CONTEXT
    # ============================================================

    def get_context(
        self,
        query: str,
    ) -> dict:
        """
        Construye el contexto que SillyTavern debe proporcionar
        al modelo antes de generar la narrativa.

        El contexto utiliza exactamente el mismo ContextBuilder
        empleado por el pipeline interno de Campaign Manager.
        """

        normalized_query = self._validate_text(
            query,
            "query",
        )

        try:
            turn_context = (
                self.campaign_state_service
                .get_turn_context()
            )

        except CampaignStateServiceError as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to obtain campaign context"
            ) from exc

        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "CampaignStateService failed to obtain "
                "campaign context"
            ) from exc

        if not isinstance(
            turn_context,
            TurnContext,
        ):
            raise SillyTavernIntegrationServiceError(
                "CampaignStateService returned an invalid "
                "TurnContext"
            )

        session_id = None

        if turn_context.current_session is not None:
            session_id = (
                turn_context.current_session.session_id
            )

        try:
            recent_turns = (
                self.turn_repository.list_recent_active_turns(
                    session_id=session_id,
                    limit=10,
                )
            )

        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to load recent active turn history"
            ) from exc

        try:
            context = self.context_builder.build(
                turn_context.world,
                normalized_query,
                recent_turns=recent_turns,
            )

        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "ContextBuilder failed to build context"
            ) from exc

        return {
            "campaign": {
                "id": turn_context.campaign.campaign_id,
                "name": turn_context.campaign.name,
                "system": turn_context.campaign.system,
                "tone": turn_context.campaign.tone,
                "summary": turn_context.campaign.summary,
            },
            "session": self._serialize_session(
                turn_context
            ),
            "active_character": (
                self._serialize_active_character(
                    turn_context
                )
            ),
            "query": normalized_query,
            "context": context,
        }

    def get_external_turn_state(
        self,
        external_turn_id: str,
    ) -> dict:
        """
        Devuelve el estado persistido de un turno externo.

        Este método permite que clientes como la extensión de
        SillyTavern reconstruyan su caché local de versionado
        después de una recarga o cambio de chat.

        El backend sigue siendo la fuente de verdad.
        """

        if not isinstance(
            external_turn_id,
            str,
        ):
            raise TypeError(
                "external_turn_id must be a string"
            )

        normalized_external_turn_id = (
            external_turn_id.strip()
        )

        if not normalized_external_turn_id:
            raise ValueError(
                "external_turn_id must not be empty"
            )

        if len(normalized_external_turn_id) > 500:
            raise ValueError(
                "external_turn_id must not be longer than 500 characters"
            )

        try:
            with get_conn() as conn:
                active_turn = (
                    self.turn_repository
                    .get_active_by_external_turn_id(
                        normalized_external_turn_id,
                        conn=conn,
                    )
                )

        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to obtain external turn state"
            ) from exc

        if active_turn is None:
            return {
                "external_turn_id":
                    normalized_external_turn_id,
                "exists": False,
                "active_version": 0,
                "narrative": None,
            }

        return {
            "external_turn_id":
                normalized_external_turn_id,
            "exists": True,
            "active_version":
                active_turn.version,
            "narrative":
                active_turn.narrative,
        }

    # ============================================================
    # EXTERNAL TURN
    # ============================================================

    def process_turn(
        self,
        player_input: str,
        narrative: str,
        external_turn_id: str | None = None,
        turn_version: int = 1,
    ) -> TurnResolutionResult:
        with self.turn_execution_lock.acquire():
            return self._process_turn_locked(
                player_input=player_input,
                narrative=narrative,
                external_turn_id=external_turn_id,
                turn_version=turn_version,
            )


    def _process_turn_locked(
        self,
        player_input: str,
        narrative: str,
        external_turn_id: str | None = None,
        turn_version: int = 1,
    ) -> TurnResolutionResult:
        """
        Procesa un turno cuya narrativa ya ha sido generada
        por SillyTavern.

        La persistencia del mundo y del TurnRecord es atómica.

        Cuando existe external_turn_id:

            - el ID se comprueba dentro de una transacción
              BEGIN IMMEDIATE.

            - mismo ID + mismo payload:
                devuelve el resultado persistido sin volver
                a ejecutar las operaciones.

            - mismo ID + payload diferente:
                produce un conflicto.

            - ID inexistente:
                procesa y persiste normalmente.

        BEGIN IMMEDIATE garantiza que dos peticiones concurrentes
        con el mismo external_turn_id no puedan ejecutar ambas
        las operaciones sobre el mundo.
        """

        if not isinstance(turn_version, int):
            raise TypeError(
                "turn_version must be an integer"
            )

        if turn_version < 1:
            raise ValueError(
                "turn_version must be >= 1"
            )
        
        normalized_input = self._validate_text(
            player_input,
            "player_input",
        )

        normalized_narrative = self._validate_text(
            narrative,
            "narrative",
        )

        normalized_external_turn_id = None

        if external_turn_id is not None:
            if not isinstance(
                external_turn_id,
                str,
            ):
                raise TypeError(
                    "external_turn_id must be a string or None"
                )

            normalized_external_turn_id = (
                external_turn_id.strip()
            )

            if not normalized_external_turn_id:
                raise ValueError(
                    "external_turn_id must not be empty"
                )

            if len(normalized_external_turn_id) > 500:
                raise ValueError(
                    "external_turn_id must not be longer than 500 characters"
                )

        existing_turn = None

        # --------------------------------------------------------
        # FAST IDEMPOTENCY CHECK
        # --------------------------------------------------------
        #
        # Si este turno ya está procesado, no tiene sentido
        # ejecutar el LLMWorldExtractor otra vez.
        #
        # Esta comprobación NO sustituye la comprobación
        # autoritativa dentro de BEGIN IMMEDIATE que aparece
        # más abajo. Solo evita trabajo innecesario.
        # --------------------------------------------------------

        if normalized_external_turn_id is not None:
            try:
                with get_conn() as conn:
                    existing_turn = (
                        self.turn_repository
                        .get_active_by_external_turn_id(
                            normalized_external_turn_id,
                            conn=conn,
                        )
                    )

            except Exception as exc:
                raise SillyTavernIntegrationServiceError(
                    "failed to check external turn idempotency"
                ) from exc

            if existing_turn is None and turn_version != 1:
                raise SillyTavernIntegrationServiceConflictError(
                    "first turn version must be 1: "
                    f"{turn_version}"
                )

            if existing_turn is not None:

                if turn_version == existing_turn.version:
                    same_input = (
                        existing_turn.player_input
                        == normalized_input
                    )

                    same_narrative = (
                        existing_turn.narrative
                        == normalized_narrative
                    )

                    if not (
                        same_input
                        and same_narrative
                    ):
                        raise (
                            SillyTavernIntegrationServiceConflictError(
                                "external_turn_id and version already "
                                "exist with different turn content: "
                                f"{normalized_external_turn_id}/"
                                f"{turn_version}"
                            )
                        )

                    return (
                        TurnResolutionResult
                        .from_persisted_turn(
                            existing_turn
                        )
                    )

                if turn_version < existing_turn.version:
                    raise (
                        SillyTavernIntegrationServiceConflictError(
                            "turn version is older than the active version: "
                            f"{turn_version} < "
                            f"{existing_turn.version}"
                        )
                    )
                
        # --------------------------------------------------------
        # CONTEXTO
        # --------------------------------------------------------

        try:
            turn_context = (
                self.campaign_state_service
                .get_turn_context()
            )

        except CampaignStateServiceError as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to obtain campaign turn context"
            ) from exc

        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "CampaignStateService failed to obtain "
                "campaign turn context"
            ) from exc

        if not isinstance(
            turn_context,
            TurnContext,
        ):
            raise SillyTavernIntegrationServiceError(
                "CampaignStateService returned an invalid "
                "TurnContext"
            )

        previous_world = self.world_service.get_world()

        # --------------------------------------------------------
        # CONTEXTO DE REGENERACIÓN
        # --------------------------------------------------------
        #
        # En una regeneración, el extractor debe trabajar contra
        # el estado existente ANTES de la versión que se está
        # regenerando.
        #
        # No restauramos SQLite aquí porque el extractor puede
        # tardar y no queremos mantener BEGIN IMMEDIATE abierto
        # durante el procesamiento LLM.
        # --------------------------------------------------------

        is_regeneration = (
            existing_turn is not None
            and turn_version == existing_turn.version + 1
        )

        if is_regeneration:
            if existing_turn.snapshot is None:
                raise SillyTavernIntegrationServiceError(
                    "cannot reconcile turn because the active "
                    "turn has no snapshot"
                )

            try:
                (
                    snapshot_world,
                    snapshot_characters,
                ) = (
                    self.world_snapshot_repository
                    .load_snapshot_state(
                        existing_turn.snapshot
                    )
                )

            except Exception as exc:
                raise SillyTavernIntegrationServiceError(
                    "failed to load previous turn snapshot "
                    "for regeneration context"
                ) from exc

            active_character = (
                turn_context.active_character
            )

            if active_character is not None:
                active_character = (
                    snapshot_characters.get(
                        active_character.entity_id,
                        active_character,
                    )
                )

            active_character_entity = (
                turn_context.active_character_entity
            )

            if active_character is not None:
                active_character_entity = (
                    snapshot_world.entities.get(
                        active_character.entity_id,
                        active_character_entity,
                    )
                )

            turn_context = replace(
                turn_context,
                world=snapshot_world,
                active_character=active_character,
                active_character_entity=(
                    active_character_entity
                ),
            )

        session_id = None

        if turn_context.current_session is not None:
            session_id = (
                turn_context.current_session.session_id
            )

        # --------------------------------------------------------
        # EXTRAER OPERACIONES
        # --------------------------------------------------------

        try:
            operations = self.extractor.extract(
                normalized_narrative,
                turn_context,
            )

        except LLMExtractionError as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to extract world operations"
            ) from exc

        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "LLMWorldExtractor failed to extract "
                "world operations"
            ) from exc

        if not isinstance(
            operations,
            list,
        ):
            raise SillyTavernIntegrationServiceError(
                "LLMWorldExtractor returned an invalid "
                "operations list"
            )

        # --------------------------------------------------------
        # SEPARAR OPERACIONES
        # --------------------------------------------------------

        from operations.character_operations import (
            CharacterOperation,
        )
        from operations.referenced_operation import (
            ReferencedOperation,
        )
        from operations.world_operations import (
            WorldOperation,
        )

        world_operations = []
        character_operations = []

        for operation in operations:

            if isinstance(
                operation,
                ReferencedOperation,
            ):
                inner_operation = (
                    operation.operation
                )

                if isinstance(
                    inner_operation,
                    WorldOperation,
                ):
                    world_operations.append(
                        operation
                    )

                elif isinstance(
                    inner_operation,
                    CharacterOperation,
                ):
                    character_operations.append(
                        operation
                    )

                else:
                    raise SillyTavernIntegrationServiceError(
                        "LLMWorldExtractor returned an invalid "
                        "referenced operation"
                    )

            elif isinstance(
                operation,
                WorldOperation,
            ):
                world_operations.append(
                    operation
                )

            elif isinstance(
                operation,
                CharacterOperation,
            ):
                character_operations.append(
                    operation
                )

            else:
                raise SillyTavernIntegrationServiceError(
                    "LLMWorldExtractor returned an invalid "
                    "operation"
                )

        normalized_operations = tuple(
            operations
        )

        # --------------------------------------------------------
        # APLICAR + PERSISTIR ATÓMICAMENTE
        # --------------------------------------------------------
        #
        # La extracción LLM ya ha terminado.
        #
        # A partir de aquí toda la reconciliación de SQLite ocurre
        # dentro de UNA única transacción:
        #
        #     BEGIN IMMEDIATE
        #          ↓
        #     restore snapshot (regeneración)
        #          ↓
        #     supersede turno anterior (regeneración)
        #          ↓
        #     aplicar operaciones
        #          ↓
        #     persistir turno
        #          ↓
        #     COMMIT
        #
        # Si cualquier paso lanza una excepción, get_conn() hace
        # rollback de TODA la transacción.
        # --------------------------------------------------------

        try:
            with get_conn() as conn:

                # ------------------------------------------------
                # ADQUIRIR LOCK DE ESCRITURA
                # ------------------------------------------------

                conn.execute(
                    "BEGIN IMMEDIATE"
                )

                # ------------------------------------------------
                # COMPROBACIÓN AUTORITATIVA DE IDEMPOTENCIA
                # ------------------------------------------------

                if normalized_external_turn_id is not None:

                    current_turn = (
                        self.turn_repository
                        .get_active_by_external_turn_id(
                            normalized_external_turn_id,
                            conn=conn,
                        )
                    )

                    if current_turn is not None:

                        # ----------------------------------------
                        # RETRY EXACTO
                        # ----------------------------------------

                        if turn_version == current_turn.version:

                            same_input = (
                                current_turn.player_input
                                == normalized_input
                            )

                            same_narrative = (
                                current_turn.narrative
                                == normalized_narrative
                            )

                            if not (
                                same_input
                                and same_narrative
                            ):
                                raise (
                                    SillyTavernIntegrationServiceConflictError(
                                        "external_turn_id and version "
                                        "already exist with different "
                                        "turn content: "
                                        f"{normalized_external_turn_id}/"
                                        f"{turn_version}"
                                    )
                                )

                            return (
                                TurnResolutionResult
                                .from_persisted_turn(
                                    current_turn
                                )
                            )

                        # ----------------------------------------
                        # VERSION ANTERIOR
                        # ----------------------------------------

                        if turn_version < current_turn.version:
                            raise (
                                SillyTavernIntegrationServiceConflictError(
                                    "turn version is older than the "
                                    "active version: "
                                    f"{turn_version} < "
                                    f"{current_turn.version}"
                                )
                            )

                        # ----------------------------------------
                        # VERSION NO SECUENCIAL
                        # ----------------------------------------

                        if turn_version > current_turn.version + 1:
                            raise (
                                SillyTavernIntegrationServiceConflictError(
                                    "turn version must be the next "
                                    "sequential version: "
                                    f"{turn_version} != "
                                    f"{current_turn.version + 1}"
                                )
                            )

                        # ----------------------------------------
                        # REGENERACIÓN
                        # ----------------------------------------

                        if current_turn.snapshot is None:
                            raise SillyTavernIntegrationServiceError(
                                "cannot reconcile turn because the "
                                "active turn has no snapshot"
                            )

                        self.world_snapshot_repository.restore_snapshot(
                            conn,
                            current_turn.snapshot,
                            scope=self.campaign_scope,
                        )

                        self.world_service.load(
                            conn=conn,
                        )

                        self.turn_repository.supersede_turn(
                            current_turn.id,
                            conn=conn,
                        )

                # ------------------------------------------------
                # SNAPSHOT DEL ESTADO SOBRE EL QUE SE APLICARÁ
                # LA NUEVA VERSIÓN
                # ------------------------------------------------

                snapshot = (
                    self.world_snapshot_repository.create_snapshot(
                        conn,
                        scope=self.campaign_scope,
                    )
                )

                # ------------------------------------------------
                # APLICAR OPERACIONES
                # ------------------------------------------------

                operation_results = (
                    self.world_service.apply_turn_operations(
                        world_operations,
                        character_operations,
                        campaign_id=self.campaign_scope.campaign_id,
                        conn=conn,
                        ordered_operations=normalized_operations,
                    )
                )

                result = TurnResolutionResult(
                    player_input=normalized_input,
                    narrative=normalized_narrative,
                    operations=tuple(
                        world_operations
                    ),
                    character_operations=tuple(
                        character_operations
                    ),
                    operation_results=tuple(
                        operation_results
                    ),
                )

                # ------------------------------------------------
                # FALLO DE OPERACIÓN
                # ------------------------------------------------
                #
                # IMPORTANTE:
                #
                # apply_turn_operations() devuelve resultados
                # inválidos sin lanzar excepción.
                #
                # En ese caso necesitamos deshacer las mutaciones
                # del mundo, PERO conservar el intento fallido.
                #
                # Para una regeneración, restore_snapshot() y
                # supersede_turn() también deben revertirse para
                # conservar el turno anterior como active.
                #
                # Por eso hacemos rollback explícito y después
                # iniciamos una NUEVA transacción únicamente para
                # guardar el TurnRecord failed.
                # ------------------------------------------------

                if not result.all_operations_succeeded:

                    conn.rollback()

                    self.world_service.world = previous_world

                    failed_turn = TurnRecord(
                        session_id=session_id,
                        player_input=result.player_input,
                        narrative=result.narrative,
                        operation_count=result.operation_count,
                        successful_operation_count=(
                            result.successful_operation_count
                        ),
                        failed_operation_count=(
                            result.failed_operation_count
                        ),
                        all_operations_succeeded=False,
                        world_changed=False,
                        external_turn_id=(
                            normalized_external_turn_id
                        ),
                        version=turn_version,
                        status="failed",
                        snapshot=snapshot,
                    )

                    self.turn_repository.save_turn(
                        failed_turn,
                    )

                    return result

                # ------------------------------------------------
                # PERSISTIR TURNO EXITOSO
                # ------------------------------------------------

                self.turn_repository.save_turn(
                    TurnRecord(
                        session_id=session_id,
                        player_input=result.player_input,
                        narrative=result.narrative,
                        operation_count=result.operation_count,
                        successful_operation_count=(
                            result.successful_operation_count
                        ),
                        failed_operation_count=(
                            result.failed_operation_count
                        ),
                        all_operations_succeeded=True,
                        world_changed=result.world_changed,
                        external_turn_id=(
                            normalized_external_turn_id
                        ),
                        version=turn_version,
                        status="active",
                        snapshot=snapshot,
                    ),
                    conn=conn,
                )

                return result

        except SillyTavernIntegrationServiceConflictError:
            raise

        except Exception as exc:
            # Si hemos llegado aquí desde dentro de get_conn(),
            # la excepción provoca automáticamente rollback de
            # toda la transacción.
            self.world_service.world = previous_world

            raise SillyTavernIntegrationServiceError(
                "failed to process and persist SillyTavern turn"
            ) from exc

        return result

    # ============================================================
    # SERIALIZATION
    # ============================================================

    @staticmethod
    def _serialize_session(
        context: TurnContext,
    ) -> dict | None:

        session = context.current_session

        if session is None:
            return None

        return {
            "id": session.session_id,
            "number": session.number,
            "title": session.title,
            "summary": session.summary,
            "start_location": session.start_location,
            "end_location": session.end_location,
            "notes": session.notes,
        }

    @staticmethod
    def _serialize_active_character(
        context: TurnContext,
    ) -> dict | None:

        character = context.active_character

        if character is None:
            return None

        return {
            "entity_id": character.entity_id,
            "level": character.level,
            "class_name": character.class_name,
            "current_hp": character.current_hp,
            "max_hp": character.max_hp,
            "armor_class": character.armor_class,
            "strength": character.strength,
            "dexterity": character.dexterity,
            "constitution": character.constitution,
            "intelligence": character.intelligence,
            "wisdom": character.wisdom,
            "charisma": character.charisma,
            "proficiency_bonus": (
                character.proficiency_bonus
            ),
        }

    # ============================================================
    # VALIDATION
    # ============================================================

    @staticmethod
    def _validate_text(
        value: str,
        field_name: str,
    ) -> str:

        if not isinstance(
            value,
            str,
        ):
            raise TypeError(
                f"{field_name} must be a string"
            )

        value = value.strip()

        if not value:
            raise ValueError(
                f"{field_name} must not be empty"
            )

        return value