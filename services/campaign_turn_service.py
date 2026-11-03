from __future__ import annotations

import copy

from database import get_conn
from models.campaign_scope import CampaignScope
from models.campaign_state import CampaignState
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.turn_resolution_result import TurnResolutionResult
from models.world_state import WorldState
from repositories.turn_repository import TurnRepository
from services.campaign_state_service import (
    CampaignStateService,
    CampaignStateServiceError,
)
from services.turn_execution_lock import TurnExecutionLock
from services.turn_resolution_service import (
    TurnResolutionService,
    TurnResolutionServiceError,
)
from services.world_service import WorldService


class CampaignTurnServiceError(RuntimeError):
    """
    Error base del servicio de turno de campaña.
    """


class CampaignTurnService:
    """
    Fachada de alto nivel para ejecutar un turno de campaña.

    Arquitectura:

        CampaignTurnService
                |
                v
        CampaignStateService
                |
                +--> CampaignRepository
                +--> CharacterRepository
                +--> WorldService
                |
                v
          CampaignState
                |
                v
        TurnResolutionService

    CampaignTurnService coordina el flujo de campaña.

    No accede directamente a SQLite.

    CampaignStateService es la fachada para obtener y persistir
    el estado de campaña.
    """

    def __init__(
        self,
        *,
        turn_resolution_service: TurnResolutionService,
        world_service: WorldService,
        campaign_state_service: CampaignStateService | None = None,
        turn_repository: TurnRepository | None = None,
        turn_execution_lock: TurnExecutionLock,
    ) -> None:

        if not isinstance(
            turn_resolution_service,
            TurnResolutionService,
        ):
            raise TypeError(
                "turn_resolution_service must be a "
                "TurnResolutionService"
            )

        if not isinstance(
            world_service,
            WorldService,
        ):
            raise TypeError(
                "world_service must be a WorldService"
            )

        if campaign_state_service is not None and not isinstance(
            campaign_state_service,
            CampaignStateService,
        ):
            raise TypeError(
                "campaign_state_service must be a "
                "CampaignStateService"
            )

        self.turn_resolution_service = (
            turn_resolution_service
        )

        self.world_service = world_service
        self.campaign_scope = CampaignScope(world_service.campaign_id)

        self.campaign_state_service = (
            campaign_state_service
        )

        if turn_repository is not None and not isinstance(
            turn_repository,
            TurnRepository,
        ):
            raise TypeError(
                "turn_repository must be a TurnRepository"
            )

        self.turn_repository = turn_repository

        if not isinstance(
            turn_execution_lock,
            TurnExecutionLock,
        ):
            raise TypeError(
                "turn_execution_lock must be a TurnExecutionLock"
            )

        self.turn_execution_lock = turn_execution_lock

    @staticmethod
    def _restore_world_state(
        target: WorldState,
        snapshot: WorldState,
    ) -> None:
        """
        Restaura el contenido de un WorldState manteniendo
        exactamente la misma instancia.

        Esto es importante porque TurnContext y WorldService
        pueden compartir la misma referencia al WorldState.
        """

        target.entities = snapshot.entities
        target.items = snapshot.items
        target.item_instances = (
            snapshot.item_instances
        )
        target.resources = snapshot.resources
        target.resource_balances = (
            snapshot.resource_balances
        )
        target.relations = snapshot.relations
        target.events = snapshot.events

    # ============================================================
    # PLAY TURN
    # ============================================================

    def play_turn(
        self,
        player_input: str,
    ) -> TurnResolutionResult:
        with self.turn_execution_lock.acquire():
            return self._play_turn_locked(
                player_input
            )


    def _play_turn_locked(
        self,
        player_input: str,
    ) -> TurnResolutionResult:
        """
        Ejecuta un turno completo.

        Cuando CampaignStateService está disponible, obtiene el
        contexto de campaña y resuelve el turno.

        La resolución y la persistencia del turno comparten la
        misma conexión cuando los servicios soportan conn.

        Si las operaciones del turno fallan, se revierten los
        cambios de la resolución, pero el resultado del turno
        se persiste igualmente.
        """

        if not isinstance(
            player_input,
            str,
        ):
            raise TypeError(
                "player_input must be a string"
            )

        normalized_input = player_input.strip()

        if not normalized_input:
            raise CampaignTurnServiceError(
                "player_input must not be empty"
            )

        world_snapshot = None

        try:

            with get_conn() as conn:

                # ------------------------------------------------
                # Obtener contexto de campaña
                # ------------------------------------------------

                if self.campaign_state_service is not None:
                    try:
                        turn_context = (
                            self.campaign_state_service
                            .get_turn_context(
                                conn=conn,
                            )
                        )

                    except CampaignStateServiceError as exc:
                        raise CampaignTurnServiceError(
                            "failed to obtain campaign turn context"
                        ) from exc

                    except Exception as exc:
                        raise CampaignTurnServiceError(
                            "CampaignStateService failed to get "
                            "turn context"
                        ) from exc

                    if not isinstance(
                        turn_context,
                        TurnContext,
                    ):
                        raise CampaignTurnServiceError(
                            "CampaignStateService returned an invalid "
                            "TurnContext"
                        )

                    world = turn_context.world

                else:

                    try:
                        world = (
                            self.world_service.get_world()
                        )

                    except Exception as exc:
                        raise CampaignTurnServiceError(
                            "WorldService failed to get world"
                        ) from exc

                    if not isinstance(
                        world,
                        WorldState,
                    ):
                        raise CampaignTurnServiceError(
                            "WorldService returned an invalid "
                            "WorldState"
                        )

                    turn_context = TurnContext(
                        campaign=CampaignState(),
                        current_session=None,
                        active_character=None,
                        world=world,
                    )

                # ------------------------------------------------
                # Snapshot del mundo
                # ------------------------------------------------

                world_snapshot = copy.deepcopy(
                    world
                )

                # ------------------------------------------------
                # Historial reciente
                # ------------------------------------------------

                recent_turns = None

                if self.turn_repository is not None:

                    session_id = None

                    if (
                        turn_context.current_session
                        is not None
                    ):
                        session_id = (
                            turn_context.current_session.session_id
                        )

                    try:
                        recent_turns = (
                            self.turn_repository.list_recent_turns(
                                session_id=session_id,
                                limit=10,
                                scope=self.campaign_scope,
                                conn=conn,
                            )
                        )

                    except Exception as exc:
                        raise CampaignTurnServiceError(
                            "failed to load recent turn history"
                        ) from exc

                # ------------------------------------------------
                # Resolver turno
                # ------------------------------------------------

                try:

                    if recent_turns is None:

                        result = (
                            self.turn_resolution_service
                            .resolve_turn(
                                turn_context,
                                normalized_input,
                                conn=conn,
                            )
                        )

                    else:

                        result = (
                            self.turn_resolution_service
                            .resolve_turn(
                                turn_context,
                                normalized_input,
                                recent_turns=recent_turns,
                                conn=conn,
                            )
                        )

                except TurnResolutionServiceError as exc:

                    self._restore_world_state(
                        world,
                        world_snapshot,
                    )

                    raise CampaignTurnServiceError(
                        "turn resolution failed"
                    ) from exc

                except CampaignTurnServiceError:

                    self._restore_world_state(
                        world,
                        world_snapshot,
                    )

                    raise

                except Exception as exc:

                    self._restore_world_state(
                        world,
                        world_snapshot,
                    )

                    raise CampaignTurnServiceError(
                        "unexpected error while resolving turn"
                    ) from exc

                # ------------------------------------------------
                # Validar resultado
                # ------------------------------------------------

                if not isinstance(
                    result,
                    TurnResolutionResult,
                ):
                    self._restore_world_state(
                        world,
                        world_snapshot,
                    )

                    raise CampaignTurnServiceError(
                        "TurnResolutionService returned an invalid "
                        "TurnResolutionResult"
                    )

                # ------------------------------------------------
                # Si alguna operación ha fallado:
                #
                # - restauramos WorldState
                # - hacemos rollback de la DB
                # - PERO guardamos el TurnRecord después del rollback
                # ------------------------------------------------

                if not result.all_operations_succeeded:

                    self._restore_world_state(
                        world,
                        world_snapshot,
                    )

                    conn.rollback()

                # ------------------------------------------------
                # Persistir turno
                # ------------------------------------------------

                if self.turn_repository is not None:

                    session_id = None

                    if (
                        turn_context.current_session
                        is not None
                    ):
                        session_id = (
                            turn_context.current_session.session_id
                        )

                    self.turn_repository.save_turn(
                        TurnRecord(
                            session_id=session_id,
                            player_input=result.player_input,
                            narrative=result.narrative,
                            operation_count=(
                                result.operation_count
                            ),
                            successful_operation_count=(
                                result.successful_operation_count
                            ),
                            failed_operation_count=(
                                result.failed_operation_count
                            ),
                            all_operations_succeeded=(
                                result.all_operations_succeeded
                            ),
                            world_changed=(
                                result.world_changed
                            ),
                        ),
                        scope=self.campaign_scope,
                        conn=conn,
                    )

                return result

        except CampaignTurnServiceError:
            if world_snapshot is not None:
                self._restore_world_state(
                    world,
                    world_snapshot,
                )

            raise

        except Exception as exc:

            if world_snapshot is not None:
                self._restore_world_state(
                    world,
                    world_snapshot,
                )

            raise CampaignTurnServiceError(
                "unexpected error while resolving turn"
            ) from exc

    # ============================================================
    # LOAD
    # ============================================================

    def load(self) -> WorldState:
        """
        Carga el WorldState persistido.

        CampaignStateService es la fachada principal.
        """

        if self.campaign_state_service is not None:

            try:
                world = (
                    self.campaign_state_service.load_world()
                )

            except CampaignStateServiceError as exc:
                raise CampaignTurnServiceError(
                    "failed to obtain campaign state"
                ) from exc

            except Exception as exc:
                raise CampaignTurnServiceError(
                    "failed to load campaign world"
                ) from exc

        else:

            try:
                world = self.world_service.load()

            except Exception as exc:
                raise CampaignTurnServiceError(
                    "failed to load campaign world"
                ) from exc

        if not isinstance(
            world,
            WorldState,
        ):
            raise CampaignTurnServiceError(
                "WorldService returned an invalid WorldState"
            )

        return world

    # ============================================================
    # SAVE
    # ============================================================

    def save(self) -> None:
        """
        Persiste explícitamente el estado actual.

        CampaignStateService es la fachada principal.
        """

        if self.campaign_state_service is not None:

            try:
                self.campaign_state_service.save_world()

            except CampaignStateServiceError as exc:
                raise CampaignTurnServiceError(
                    "failed to save campaign world"
                ) from exc

            except Exception as exc:
                raise CampaignTurnServiceError(
                    "failed to save campaign world"
                ) from exc

            return

        try:
            self.world_service.save()

        except Exception as exc:
            raise CampaignTurnServiceError(
                "failed to save campaign world"
            ) from exc

    # ============================================================
    # GET WORLD
    # ============================================================

    def get_world(self) -> WorldState:
        """
        Devuelve el WorldState actual.

        Cuando existe CampaignStateService, delega en él.
        """

        if self.campaign_state_service is not None:

            try:
                turn_context = (
                    self.campaign_state_service.get_turn_context()
                )

            except CampaignStateServiceError as exc:
                raise CampaignTurnServiceError(
                    "failed to obtain campaign turn context"
                ) from exc

            except Exception as exc:
                raise CampaignTurnServiceError(
                    "CampaignStateService failed to get "
                    "turn context"
                ) from exc

            if not isinstance(
                turn_context,
                TurnContext,
            ):
                raise CampaignTurnServiceError(
                    "CampaignStateService returned an invalid "
                    "TurnContext"
                )

            world = turn_context.world

        else:

            try:
                world = (
                    self.world_service.get_world()
                )

            except Exception as exc:
                raise CampaignTurnServiceError(
                    "WorldService failed to get world"
                ) from exc

            if not isinstance(
                world,
                WorldState,
            ):
                raise CampaignTurnServiceError(
                    "WorldService returned an invalid WorldState"
                )

        return world