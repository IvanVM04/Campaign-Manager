"""Read-only context and transcript-state adapter for SillyTavern."""

from __future__ import annotations

from database import get_conn
from models.campaign_scope import CampaignScope
from models.turn_context import TurnContext
from repositories.turn_repository import TurnRepository
from services.campaign import CampaignStateService, CampaignStateServiceError
from services.context import ContextBuilder

from .errors import SillyTavernIntegrationServiceError


class SillyTavernContextAdapter:
    """Translate campaign context and external-turn state to the client contract.

    This adapter is deliberately read-only. Durable turn mutation is owned
    by the turn application services and is never delegated to this adapter.
    """

    def __init__(
        self,
        *,
        campaign_scope: CampaignScope,
        campaign_state_service: CampaignStateService,
        context_builder: ContextBuilder,
        turn_repository: TurnRepository,
    ) -> None:
        if not isinstance(campaign_scope, CampaignScope):
            raise TypeError("campaign_scope must be a CampaignScope")
        if not isinstance(campaign_state_service, CampaignStateService):
            raise TypeError("campaign_state_service must be a CampaignStateService")
        if not isinstance(context_builder, ContextBuilder):
            raise TypeError("context_builder must be a ContextBuilder")
        if not isinstance(turn_repository, TurnRepository):
            raise TypeError("turn_repository must be a TurnRepository")

        self.campaign_scope = campaign_scope
        self.campaign_state_service = campaign_state_service
        self.context_builder = context_builder
        self.turn_repository = turn_repository

    def get_context(
        self,
        query: str,
        *,
        additional_queries: tuple[str, ...] | list[str] = (),
        exclude_external_turn_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict:
        """Build context from a primary action and independent supplemental signals."""
        normalized_query = self._validate_text(query, "query")
        if conversation_id is not None:
            conversation_id = self._validate_text(conversation_id, "conversation_id")
            if len(conversation_id) > 500:
                raise ValueError("conversation_id must not exceed 500 characters")
        normalized_additional_queries = self._validate_additional_queries(
            additional_queries,
            primary_query=normalized_query,
        )

        try:
            turn_context = self.campaign_state_service.get_turn_context(
                campaign_id=self.campaign_scope.campaign_id
            )
        except CampaignStateServiceError as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to obtain campaign context"
            ) from exc
        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "CampaignStateService failed to obtain campaign context"
            ) from exc

        if not isinstance(turn_context, TurnContext):
            raise SillyTavernIntegrationServiceError(
                "CampaignStateService returned an invalid TurnContext"
            )

        session_id = (
            turn_context.current_session.session_id
            if turn_context.current_session is not None
            else None
        )

        try:
            recent_turns = (
                self.turn_repository.list_recent_active_turns(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    limit=10,
                    scope=self.campaign_scope,
                )
                if conversation_id is not None
                else []
            )
            if exclude_external_turn_id is not None:
                recent_turns = [
                    turn
                    for turn in recent_turns
                    if turn.external_turn_id != exclude_external_turn_id
                ]
        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to load recent active turn history"
            ) from exc

        try:
            if normalized_additional_queries:
                context = self.context_builder.build(
                    turn_context.world,
                    normalized_query,
                    recent_turns=recent_turns,
                    supplemental_queries=normalized_additional_queries,
                    character_entity_id=(
                        turn_context.active_character.entity_id
                        if turn_context.active_character is not None
                        else None
                    ),
                )
            else:
                context = self.context_builder.build(
                    turn_context.world,
                    normalized_query,
                    recent_turns=recent_turns,
                    character_entity_id=(
                        turn_context.active_character.entity_id
                        if turn_context.active_character is not None
                        else None
                    ),
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
            "session": self._serialize_session(turn_context),
            "active_character": self._serialize_active_character(turn_context),
            "query": normalized_query,
            "context": context,
            "retrieval_diagnostics": {
                "query_count": 1 + len(normalized_additional_queries),
                "supplemental_query_count": len(normalized_additional_queries),
                "included_record_counts": {
                    category: len(context.get(category, []))
                    for category in (
                        "entities",
                        "items",
                        "item_instances",
                        "resources",
                        "resource_balances",
                        "relations",
                        "events",
                    )
                },
            },
        }

    def get_external_turn_state(self, external_turn_id: str) -> dict:
        """Return persisted transcript state so a client can recover its cache."""
        if not isinstance(external_turn_id, str):
            raise TypeError("external_turn_id must be a string")

        normalized_external_turn_id = external_turn_id.strip()
        if not normalized_external_turn_id:
            raise ValueError("external_turn_id must not be empty")
        if len(normalized_external_turn_id) > 500:
            raise ValueError("external_turn_id must not be longer than 500 characters")

        try:
            with get_conn() as conn:
                active_turn = self.turn_repository.get_active_by_external_turn_id(
                    normalized_external_turn_id,
                    scope=self.campaign_scope,
                    conn=conn,
                )
        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to obtain external turn state"
            ) from exc

        try:
            versions = self.turn_repository.get_versions_by_external_turn_id(
                normalized_external_turn_id,
                scope=self.campaign_scope,
            )
        except Exception as exc:
            raise SillyTavernIntegrationServiceError(
                "failed to obtain external turn version history"
            ) from exc

        next_version = max((turn.version for turn in versions), default=0) + 1
        if active_turn is None:
            return {
                "external_turn_id": normalized_external_turn_id,
                "exists": False,
                "active_version": 0,
                "next_version": next_version,
                "narrative": None,
            }

        return {
            "external_turn_id": normalized_external_turn_id,
            "exists": True,
            "active_version": active_turn.version,
            "next_version": next_version,
            "narrative": active_turn.narrative,
        }

    @staticmethod
    def _serialize_session(context: TurnContext) -> dict | None:
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
    def _serialize_active_character(context: TurnContext) -> dict | None:
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
            "proficiency_bonus": character.proficiency_bonus,
        }

    @staticmethod
    def _validate_additional_queries(
        queries: tuple[str, ...] | list[str],
        *,
        primary_query: str,
    ) -> tuple[str, ...]:
        if not isinstance(queries, (tuple, list)):
            raise TypeError("additional_queries must be a tuple or list")
        normalized: list[str] = []
        seen = {primary_query.casefold()}
        for query in queries:
            if not isinstance(query, str):
                raise TypeError("additional_queries must contain only strings")
            value = query.strip()
            if not value:
                continue
            key = value.casefold()
            if key not in seen:
                normalized.append(value)
                seen.add(key)
        return tuple(normalized)

    @staticmethod
    def _validate_text(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError(f"{field_name} must not be empty")
        return normalized_value
