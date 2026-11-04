from __future__ import annotations

import copy
import secrets
import time

from database import get_conn, transaction
from models.campaign_scope import CampaignScope
from models.campaign_state import CampaignState
from models.mechanics import MechanicsDecision
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.turn_resolution_result import TurnResolutionResult
from models.world_state import WorldState
from repositories.campaign_state_version_repository import (
    CampaignStateVersionRepository,
)
from repositories.turn_repository import TurnRepository
from rules_engine.dnd5e_2014.character_checks import (
    ability_check_modifier_for_character,
)
from rules_engine.dnd5e_2014.core.skills import ability_for_skill
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
        self.state_version_repository = CampaignStateVersionRepository()

        if not isinstance(
            turn_execution_lock,
            TurnExecutionLock,
        ):
            raise TypeError(
                "turn_execution_lock must be a TurnExecutionLock"
            )

        self.turn_execution_lock = turn_execution_lock
        self._pending_manual_rolls: dict[str, dict] = {}

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
        *,
        dice_mode: str = "automatic",
    ) -> TurnResolutionResult:
        if dice_mode not in {"automatic", "manual"}:
            raise ValueError("dice_mode must be 'automatic' or 'manual'")
        with self.turn_execution_lock.acquire():
            if dice_mode == "manual":
                return self._play_turn_planned_locked(
                    player_input, manual_mode=True
                )
            return self._play_turn_locked(player_input)

    def submit_manual_roll(
        self,
        pending_roll_id: str,
        rolls: tuple[int, ...],
    ) -> TurnResolutionResult:
        if not isinstance(pending_roll_id, str) or not pending_roll_id:
            raise ValueError("pending_roll_id is required")
        if not isinstance(rolls, tuple):
            raise TypeError("rolls must be a tuple")
        with self.turn_execution_lock.acquire():
            pending = self._pending_manual_rolls.get(pending_roll_id)
            if pending is None:
                raise CampaignTurnServiceError("manual roll request not found or expired")
            if time.monotonic() - pending["created_at"] > 900:
                self._pending_manual_rolls.pop(pending_roll_id, None)
                raise CampaignTurnServiceError("manual roll request expired; retry the action")
            result = self._play_turn_planned_locked(
                pending["player_input"],
                decision_override=pending["decision"],
                manual_rolls=rolls,
                expected_context=pending["context"],
                expected_recent_turns=pending["recent_turns"],
                expected_revision=pending["state_revision"],
            )
            self._pending_manual_rolls.pop(pending_roll_id, None)
            return result


    def _play_turn_locked(
        self,
        player_input: str,
    ) -> TurnResolutionResult:
        # Keep compatibility with test doubles and downstream custom
        # resolvers that override the original all-in-one API.
        if (
            type(self.turn_resolution_service).resolve_turn
            is not TurnResolutionService.resolve_turn
        ):
            return self._play_turn_legacy_locked(player_input)

        return self._play_turn_planned_locked(player_input)

    def _load_fresh_turn_context(self, conn) -> TurnContext:
        if self.campaign_state_service is None:
            world = self.world_service.repository.load_world(
                campaign_id=self.campaign_scope.campaign_id,
                conn=conn,
            )
            self.world_service.world = world
            return TurnContext(
                campaign=CampaignState(
                    campaign_id=self.campaign_scope.campaign_id
                ),
                current_session=None,
                active_character=None,
                world=world,
            )

        context = self.campaign_state_service.get_turn_context(
            campaign_id=self.campaign_scope.campaign_id,
            conn=conn,
        )
        if not isinstance(context, TurnContext):
            raise CampaignTurnServiceError(
                "CampaignStateService returned an invalid TurnContext"
            )

        # get_turn_context assembles campaign/character data but currently
        # reads the world's in-memory object. Reload it using this connection
        # so the plan is based on the same database snapshot as the metadata.
        world = self.world_service.repository.load_world(
            campaign_id=self.campaign_scope.campaign_id,
            conn=conn,
        )
        self.world_service.world = world
        return TurnContext(
            campaign=context.campaign,
            current_session=context.current_session,
            active_character=context.active_character,
            world=world,
            active_character_entity=context.active_character_entity,
            active_character_conditions=context.active_character_conditions,
        )

    def _play_turn_planned_locked(
        self,
        player_input: str,
        *,
        manual_mode: bool = False,
        decision_override: MechanicsDecision | None = None,
        manual_rolls: tuple[int, ...] | None = None,
        expected_context: TurnContext | None = None,
        expected_recent_turns=None,
        expected_revision: int | None = None,
    ) -> TurnResolutionResult:
        """
        Execute LLM planning outside SQLite transactions, then re-read and
        validate the complete context inside a short BEGIN IMMEDIATE write
        transaction before applying the plan and recording the turn.
        """
        if not isinstance(player_input, str):
            raise TypeError("player_input must be a string")
        normalized_input = player_input.strip()
        if not normalized_input:
            raise CampaignTurnServiceError(
                "player_input must not be empty"
            )

        world = self.world_service.get_world()
        world_snapshot = copy.deepcopy(world)

        try:
            # Read a consistent prompt context and history, then release the
            # connection before any provider/LLM work begins.
            with transaction("DEFERRED") as read_conn:
                initial_revision = self.state_version_repository.get_revision(
                    self.campaign_scope.campaign_id,
                    conn=read_conn,
                )
                initial_context = self._load_fresh_turn_context(read_conn)
                recent_turns = None
                if self.turn_repository is not None:
                    session_id = (
                        initial_context.current_session.session_id
                        if initial_context.current_session is not None
                        else None
                    )
                    recent_turns = self.turn_repository.list_recent_turns(
                        session_id=session_id,
                        limit=10,
                        scope=self.campaign_scope,
                        conn=read_conn,
                    )

            world = initial_context.world
            world_snapshot = copy.deepcopy(world)

            if expected_revision is not None and initial_revision != expected_revision:
                raise CampaignTurnServiceError(
                    "campaign state changed while waiting for the manual roll"
                )

            if expected_context is not None and initial_context != expected_context:
                raise CampaignTurnServiceError(
                    "campaign state changed while waiting for the manual roll"
                )
            if expected_context is not None and recent_turns != expected_recent_turns:
                raise CampaignTurnServiceError(
                    "turn history changed while waiting for the manual roll"
                )

            plan = self.turn_resolution_service.prepare_turn(
                initial_context,
                normalized_input,
                recent_turns=recent_turns,
                manual_mode=manual_mode,
                manual_rolls=manual_rolls,
                decision_override=decision_override,
            )

            if plan.awaiting_manual_roll:
                token = secrets.token_urlsafe(24)
                decision = plan.mechanics_decision
                character = initial_context.active_character
                if decision is None or character is None:
                    raise CampaignTurnServiceError(
                        "manual roll is missing its decision or character"
                    )
                ability = decision.ability or (
                    ability_for_skill(decision.skill)
                    if decision.skill is not None
                    else None
                )
                if ability is None:
                    raise CampaignTurnServiceError("manual roll has no governing ability")
                proficient = (
                    decision.decision.value == "skill_check"
                    and decision.skill in character.skill_proficiencies
                ) or (
                    decision.decision.value == "saving_throw"
                    and ability in character.saving_throw_proficiencies
                )
                expertise = (
                    decision.decision.value == "skill_check"
                    and decision.skill in character.skill_expertise
                )
                modifier = ability_check_modifier_for_character(
                    character=character,
                    ability=ability,
                    proficient=proficient,
                    expertise=expertise,
                    situational_modifier=decision.situational_modifier,
                )
                request = {
                    "dice": "d20",
                    "count": 1 if decision.advantage == decision.disadvantage else 2,
                    "modifier": modifier,
                    "dc": decision.dc,
                    "kind": decision.decision.value,
                    "skill": decision.skill.value if decision.skill else None,
                    "ability": ability.value,
                    "advantage": decision.advantage,
                    "disadvantage": decision.disadvantage,
                }
                now = time.monotonic()
                self._pending_manual_rolls = {
                    key: value
                    for key, value in self._pending_manual_rolls.items()
                    if now - value["created_at"] <= 900
                }
                if len(self._pending_manual_rolls) >= 100:
                    raise CampaignTurnServiceError("too many pending manual rolls")
                self._pending_manual_rolls[token] = {
                    "created_at": now,
                    "player_input": normalized_input,
                    "decision": decision,
                    "context": initial_context,
                    "recent_turns": recent_turns,
                    "state_revision": initial_revision,
                }
                return TurnResolutionResult(
                    player_input=normalized_input,
                    narrative="",
                    pending_roll_id=token,
                    pending_roll=request,
                )

            # No DB connection is held during model generation/extraction.
            # BEGIN IMMEDIATE ensures no other writer can change campaign
            # state between our fresh read, validation and persistence.
            with transaction("IMMEDIATE") as write_conn:
                current_revision = self.state_version_repository.get_revision(
                    self.campaign_scope.campaign_id,
                    conn=write_conn,
                )
                if current_revision != initial_revision:
                    raise CampaignTurnServiceError(
                        "campaign state changed while the turn was being prepared; retry"
                    )

                current_context = self._load_fresh_turn_context(write_conn)

                current_recent_turns = None
                if self.turn_repository is not None:
                    session_id = (
                        current_context.current_session.session_id
                        if current_context.current_session is not None
                        else None
                    )
                    current_recent_turns = self.turn_repository.list_recent_turns(
                        session_id=session_id,
                        limit=10,
                        scope=self.campaign_scope,
                        conn=write_conn,
                    )

                if current_context != initial_context:
                    raise CampaignTurnServiceError(
                        "campaign state changed while the turn was being prepared; retry"
                    )
                if current_recent_turns != recent_turns:
                    raise CampaignTurnServiceError(
                        "turn history changed while the turn was being prepared; retry"
                    )

                result = self.turn_resolution_service.apply_plan(
                    current_context,
                    plan,
                    conn=write_conn,
                )

                if not isinstance(result, TurnResolutionResult):
                    raise CampaignTurnServiceError(
                        "TurnResolutionService returned an invalid TurnResolutionResult"
                    )

                if not result.all_operations_succeeded:
                    self._restore_world_state(world, world_snapshot)
                    self.world_service.world = world
                    write_conn.rollback()

                if self.turn_repository is not None:
                    session_id = (
                        current_context.current_session.session_id
                        if current_context.current_session is not None
                        else None
                    )
                    self.turn_repository.save_turn(
                        TurnRecord(
                            session_id=session_id,
                            player_input=result.player_input,
                            narrative=result.narrative,
                            operation_count=result.operation_count,
                            successful_operation_count=(
                                result.successful_operation_count
                            ),
                            failed_operation_count=result.failed_operation_count,
                            all_operations_succeeded=(
                                result.all_operations_succeeded
                            ),
                            world_changed=result.world_changed,
                        ),
                        scope=self.campaign_scope,
                        conn=write_conn,
                    )

                return result

        except CampaignTurnServiceError:
            self._restore_world_state(world, world_snapshot)
            self.world_service.world = world
            raise
        except TurnResolutionServiceError as exc:
            self._restore_world_state(world, world_snapshot)
            self.world_service.world = world
            raise CampaignTurnServiceError(
                "turn resolution failed"
            ) from exc
        except Exception as exc:
            self._restore_world_state(world, world_snapshot)
            self.world_service.world = world
            raise CampaignTurnServiceError(
                "unexpected error while resolving turn"
            ) from exc

    def _play_turn_legacy_locked(
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
                                campaign_id=self.campaign_scope.campaign_id,
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
                    self.campaign_state_service.get_turn_context(campaign_id=self.campaign_scope.campaign_id)
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