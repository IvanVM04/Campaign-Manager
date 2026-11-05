"""Deprecated narrative-first SillyTavern turn processing.

This service isolates the pre-durable compatibility workflow. New integrations
must use DurableNativeTurnService and must not add gameplay behavior here.
"""

from __future__ import annotations

import copy
import sqlite3
from dataclasses import replace

from database import get_conn, transaction
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.turn_resolution_result import TurnResolutionResult
from services.campaign_state_service import CampaignStateServiceError
from services.llm_world_extractor import LLMExtractionError


class LegacySillyTavernTurnService:
    """Owns the deprecated narrative-first snapshot-reconciliation workflow."""

    def __init__(
        self,
        *,
        campaign_scope,
        campaign_state_service,
        extractor,
        world_service,
        turn_repository,
        turn_execution_lock,
        state_version_repository,
        world_snapshot_repository,
        error_type=RuntimeError,
        conflict_error_type=RuntimeError,
        transaction_context=transaction,
    ) -> None:
        self.campaign_scope = campaign_scope
        self.campaign_state_service = campaign_state_service
        self.extractor = extractor
        self.world_service = world_service
        self.turn_repository = turn_repository
        self.turn_execution_lock = turn_execution_lock
        self.state_version_repository = state_version_repository
        self.world_snapshot_repository = world_snapshot_repository
        self.error_type = error_type
        self.conflict_error_type = conflict_error_type
        self.transaction_context = transaction_context

    def process_turn(
        self,
        player_input: str,
        narrative: str,
        external_turn_id: str | None = None,
        turn_version: int = 1,
    ) -> TurnResolutionResult:
        """Process a legacy narrative-first turn.

        New clients use the durable resolve/complete workflow.
        """
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
                            scope=self.campaign_scope,
                            conn=conn,
                        )
                    )

            except Exception as exc:
                raise self.error_type(
                    "failed to check external turn idempotency"
                ) from exc

            if existing_turn is None and turn_version != 1:
                raise self.conflict_error_type(
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
                            self.conflict_error_type(
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
                        self.conflict_error_type(
                            "turn version is older than the active version: "
                            f"{turn_version} < "
                            f"{existing_turn.version}"
                        )
                    )
                
        # --------------------------------------------------------
        # CONTEXTO
        # --------------------------------------------------------

        previous_world = self.world_service.get_world()
        previous_world_snapshot = copy.deepcopy(previous_world)

        try:
            with self.transaction_context("DEFERRED") as read_conn:
                state_revision = self.state_version_repository.get_revision(
                    self.campaign_scope.campaign_id,
                    conn=read_conn,
                )
                turn_context = (
                    self.campaign_state_service
                    .get_turn_context(
                        campaign_id=self.campaign_scope.campaign_id,
                        conn=read_conn,
                    )
                )
                fresh_world = self.world_service.repository.load_world(
                    campaign_id=self.campaign_scope.campaign_id,
                    conn=read_conn,
                )
                turn_context = replace(
                    turn_context,
                    world=fresh_world,
                )

        except CampaignStateServiceError as exc:
            raise self.error_type(
                "failed to obtain campaign turn context"
            ) from exc

        except Exception as exc:
            raise self.error_type(
                "CampaignStateService failed to obtain "
                "campaign turn context"
            ) from exc

        if not isinstance(
            turn_context,
            TurnContext,
        ):
            raise self.error_type(
                "CampaignStateService returned an invalid "
                "TurnContext"
            )

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
                raise self.error_type(
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
                raise self.error_type(
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
            raise self.error_type(
                "failed to extract world operations"
            ) from exc

        except Exception as exc:
            raise self.error_type(
                "LLMWorldExtractor failed to extract "
                "world operations"
            ) from exc

        if not isinstance(
            operations,
            list,
        ):
            raise self.error_type(
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
                    raise self.error_type(
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
                raise self.error_type(
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
            with self.transaction_context("IMMEDIATE") as conn:

                # ------------------------------------------------
                # COMPROBACIÓN AUTORITATIVA DE IDEMPOTENCIA
                # ------------------------------------------------

                current_turn = None

                if normalized_external_turn_id is not None:

                    current_turn = (
                        self.turn_repository
                        .get_active_by_external_turn_id(
                            normalized_external_turn_id,
                            scope=self.campaign_scope,
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
                                    self.conflict_error_type(
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
                                self.conflict_error_type(
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
                                self.conflict_error_type(
                                    "turn version must be the next "
                                    "sequential version: "
                                    f"{turn_version} != "
                                    f"{current_turn.version + 1}"
                                )
                            )

                current_revision = self.state_version_repository.get_revision(
                    self.campaign_scope.campaign_id,
                    conn=conn,
                )
                if current_revision != state_revision:
                    raise self.conflict_error_type(
                        "campaign state changed while turn operations were being extracted; retry"
                    )

                if current_turn is not None:
                    # ----------------------------------------
                    # REGENERACIÓN
                    # ----------------------------------------

                    if current_turn.snapshot is None:
                        raise self.error_type(
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
                        scope=self.campaign_scope,
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

                    self._restore_world_state(
                        previous_world,
                        previous_world_snapshot,
                    )
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
                        scope=self.campaign_scope,
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
                    scope=self.campaign_scope,
                    conn=conn,
                )

                return result

        except self.conflict_error_type:
            try:
                fresh_world = self.world_service.repository.load_world(
                    campaign_id=self.campaign_scope.campaign_id,
                )
            except (sqlite3.Error, ValueError):
                self._restore_world_state(
                    previous_world,
                    previous_world_snapshot,
                )
            else:
                self._restore_world_state(previous_world, fresh_world)
            self.world_service.world = previous_world
            raise

        except Exception as exc:
            # Si hemos llegado aquí desde dentro de get_conn(),
            # la excepción provoca automáticamente rollback de
            # toda la transacción.
            self._restore_world_state(
                previous_world,
                previous_world_snapshot,
            )
            self.world_service.world = previous_world

            raise self.error_type(
                "failed to process and persist SillyTavern turn"
            ) from exc

        return result

    @staticmethod
    def _restore_world_state(target, snapshot) -> None:
        """
        Restaura el contenido de un WorldState sin cambiar su identidad.

        WorldService publica las operaciones sobre la instancia original
        antes de que get_conn() confirme la transacción exterior. Si el
        guardado del turno o el COMMIT fallan, reasignar únicamente la
        referencia no revierte esa mutación: hay que restaurar también
        las colecciones compartidas.
        """
        target.entities = copy.deepcopy(snapshot.entities)
        target.items = copy.deepcopy(snapshot.items)
        target.item_instances = copy.deepcopy(snapshot.item_instances)
        target.resources = copy.deepcopy(snapshot.resources)
        target.resource_balances = copy.deepcopy(snapshot.resource_balances)
        target.relations = copy.deepcopy(snapshot.relations)
        target.events = copy.deepcopy(snapshot.events)

    @staticmethod
    def _validate_text(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must not be empty")
        return value
