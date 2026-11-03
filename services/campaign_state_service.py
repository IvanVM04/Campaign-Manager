from __future__ import annotations

from database import get_conn
from models.campaign_scope import CampaignScope
from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.session_state import SessionState
from models.turn_context import TurnContext
from models.world_state import WorldState
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from services.world_service import WorldService


class CampaignStateServiceError(RuntimeError):
    """
    Error base del servicio de estado de campaña.
    """


class CampaignStateService:
    """
    Ensambla el estado completo necesario para ejecutar la campaña.

    Responsabilidad:

        CampaignRepository
              |
              +--> campaign
              +--> current session
              +--> active character id
                    |
                    v
              CharacterRepository
                    |
                    v
              active character

        WorldService
              |
              v
          WorldState

                    ↓

             CampaignState

    Este servicio NO:
        - genera narrativa
        - resuelve turnos
        - aplica operaciones
        - modifica WorldState
        - accede directamente a SQLite

    Su única responsabilidad es ensamblar el estado actual.
    """

    def __init__(
        self,
        *,
        campaign_repository: CampaignRepository,
        character_repository: CharacterRepository,
        entity_repository: EntityRepository,
        world_service: WorldService,
        campaign_id: int | None = None,
    ) -> None:

        if not isinstance(
            campaign_repository,
            CampaignRepository,
        ):
            raise TypeError(
                "campaign_repository must be a CampaignRepository"
            )

        if not isinstance(
            character_repository,
            CharacterRepository,
        ):
            raise TypeError(
                "character_repository must be a CharacterRepository"
            )

        if not isinstance(
            world_service,
            WorldService,
        ):
            raise TypeError(
                "world_service must be a WorldService"
            )

        if not isinstance(
            entity_repository,
            EntityRepository,
        ):
            raise TypeError(
                "entity_repository must be an EntityRepository"
            )

        self.campaign_repository = campaign_repository
        self.character_repository = character_repository
        self.world_service = world_service
        self.entity_repository = entity_repository
        self.campaign_id = world_service.campaign_id if campaign_id is None else campaign_id
        CampaignScope(self.campaign_id)

    # ============================================================
    # PUBLIC API
    # ============================================================

    def _resolve_campaign_id(self, campaign_id: int | None) -> int:
        resolved = self.campaign_id if campaign_id is None else campaign_id
        CampaignScope(resolved)
        return resolved

    def get_state(
        self,
        campaign_id: int | None = None,
    ) -> CampaignState:
        """
        Devuelve el estado persistido de alto nivel
        de la campaña.
        """

        campaign_id = self._resolve_campaign_id(campaign_id)
        campaign = self.campaign_repository.get_campaign(
            campaign_id
        )

        if campaign is None:
            raise CampaignStateServiceError(
                "campaign does not exist"
            )

        return CampaignState(
            campaign_id=campaign["id"],
            name=campaign["name"],
            system=campaign["system"],
            tone=campaign["tone"] or "",
            current_location_id=campaign[
                "current_location_id"
            ],
            current_session_id=campaign[
                "current_session_id"
            ],
            active_character_id=campaign[
                "active_character_id"
            ],
            summary=campaign["summary"] or "",
        )
    
    # ============================================================
    # ACTIVE CHARACTER
    # ============================================================

    def set_active_character(
        self,
        character_id: int | None,
        campaign_id: int | None = None,
    ) -> CampaignState:
        """
        Establece o elimina el personaje activo.

        Si se proporciona un ID, el personaje debe existir.
        """

        campaign_id = self._resolve_campaign_id(campaign_id)
        if character_id is not None:

            character = self.character_repository.get_character(
                character_id,
                campaign_id=campaign_id,
            )

            if character is None:
                raise CampaignStateServiceError(
                    "cannot activate a character that does not exist"
                )

        self.campaign_repository.update_active_character(
            campaign_id=campaign_id,
            character_id=character_id,
        )

        return self.get_state(campaign_id)

    # ============================================================
    # CURRENT SESSION
    # ============================================================

    def set_current_session(
        self,
        session_id: int | None,
        campaign_id: int | None = None,
    ) -> CampaignState:
        """
        Establece o elimina la sesión actual.

        Si se proporciona un ID, la sesión debe existir.
        """

        campaign_id = self._resolve_campaign_id(campaign_id)
        if session_id is not None:

            session = (
                self.campaign_repository.get_session(
                    session_id,
                    campaign_id=campaign_id,
                )
            )

            if session is None:
                raise CampaignStateServiceError(
                    "cannot activate a session that does not exist"
                )

        self.campaign_repository.update_current_session(
            campaign_id=campaign_id,
            session_id=session_id,
        )

        return self.get_state(campaign_id)

    # ============================================================
    # WORLD
    # ============================================================

    def get_world(
        self,
    ) -> WorldState:
        """
        Devuelve únicamente el WorldState actual.
        """

        world = self.world_service.get_world()

        if not isinstance(
            world,
            WorldState,
        ):
            raise CampaignStateServiceError(
                "WorldService returned an invalid WorldState"
            )

        return world

    def load_world(
        self,
    ) -> WorldState:
        """
        Carga el WorldState desde persistencia.
        """

        try:
            world = self.world_service.load()

        except Exception as exc:
            raise CampaignStateServiceError(
                "failed to load campaign world"
            ) from exc

        if not isinstance(
            world,
            WorldState,
        ):
            raise CampaignStateServiceError(
                "WorldService returned an invalid WorldState"
            )

        return world

    def save_world(
        self,
    ) -> None:
        """
        Persiste explícitamente el WorldState actual.
        """

        try:
            self.world_service.save()

        except Exception as exc:
            raise CampaignStateServiceError(
                "failed to save campaign world"
            ) from exc

    def get_turn_context(
        self,
        campaign_id: int | None = None,
        *,
        conn=None,
    ) -> TurnContext:

        campaign_id = self._resolve_campaign_id(campaign_id)
        if conn is None:
            with get_conn() as owned_conn:
                return self._get_turn_context(
                    campaign_id,
                    conn=owned_conn,
                )

        return self._get_turn_context(
            campaign_id,
            conn=conn,
        )

    def _get_turn_context(
        self,
        campaign_id: int,
        *,
        conn,
    ) -> TurnContext:
        """
        Construye el contexto completo necesario para
        resolver un turno.
        """

        campaign = self.campaign_repository.get_campaign(
            campaign_id,
            conn=conn,
        )

        if campaign is None:
            raise CampaignStateServiceError(
                "campaign does not exist"
            )

        campaign_state = CampaignState(
            campaign_id=campaign["id"],
            name=campaign["name"],
            system=campaign["system"],
            tone=campaign["tone"] or "",
            current_location_id=campaign[
                "current_location_id"
            ],
            current_session_id=campaign[
                "current_session_id"
            ],
            active_character_id=campaign[
                "active_character_id"
            ],
            summary=campaign["summary"] or "",
        )

        current_session = (
            self.campaign_repository.get_current_session(
                campaign_id,
                conn=conn,
            )
        )

        session_state = None

        if current_session is not None:
            session_state = SessionState(
                session_id=current_session["id"],
                number=current_session["number"],
                title=current_session["title"] or "",
                summary=current_session["summary"] or "",
                start_location=(
                    current_session["start_location"]
                    or ""
                ),
                end_location=(
                    current_session["end_location"]
                    or ""
                ),
                notes=current_session["notes"] or "",
            )

        active_character_id = (
            self.campaign_repository.get_active_character_id(
                campaign_id,
                conn=conn,
            )
        )

        active_character = None
        active_character_entity = None

        if active_character_id is not None:
            active_character = self.character_repository.get_character(
                active_character_id,
                campaign_id=campaign_id,
                conn=conn,
            )

            if active_character is None:
                raise CampaignStateServiceError(
                    "active character does not exist"
                )

            if not isinstance(
                active_character,
                CharacterState,
            ):
                raise CampaignStateServiceError(
                    "CharacterRepository returned an invalid CharacterState"
                )

            active_character_entity = self.entity_repository.get_entity(
                active_character.entity_id,
                campaign_id=campaign_id,
                conn=conn,
            )

            if active_character_entity is None:
                raise CampaignStateServiceError(
                    "active character entity does not exist"
                )

        world = self.world_service.get_world()

        if not isinstance(
            world,
            WorldState,
        ):
            raise CampaignStateServiceError(
                "WorldService returned an invalid WorldState"
            )

        return TurnContext(
            campaign=campaign_state,
            current_session=session_state,
            active_character=active_character,
            active_character_entity=active_character_entity,
            world=world,
        )
