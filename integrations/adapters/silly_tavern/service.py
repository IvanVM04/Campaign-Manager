"""Thin façade that combines read adapters with the legacy turn processor port."""

from __future__ import annotations

from typing import Protocol

from models.turn_resolution_result import TurnResolutionResult

from .context_adapter import SillyTavernContextAdapter


class LegacyTurnProcessor(Protocol):
    """Application-owned use case exposed to the deprecated client contract."""

    def process_turn(
        self,
        player_input: str,
        narrative: str,
        external_turn_id: str | None = None,
        turn_version: int = 1,
    ) -> TurnResolutionResult: ...


class SillyTavernIntegrationService:
    """Preserve the runtime-facing adapter while keeping collaborators separate.

    Context/history reads are delegated to SillyTavernContextAdapter.
    The deprecated narrative-first endpoint is delegated to an injected turn
    processor. This façade owns no repository, snapshot, transaction or LLM
    construction.
    """

    def __init__(
        self,
        *,
        context_adapter: SillyTavernContextAdapter,
        legacy_turn_service: LegacyTurnProcessor,
    ) -> None:
        if not isinstance(context_adapter, SillyTavernContextAdapter):
            raise TypeError("context_adapter must be a SillyTavernContextAdapter")
        if not callable(getattr(legacy_turn_service, "process_turn", None)):
            raise TypeError("legacy_turn_service must expose process_turn()")

        self.context_adapter = context_adapter
        self.legacy_turn_service = legacy_turn_service

    def get_context(
        self,
        query: str,
        *,
        exclude_external_turn_id: str | None = None,
    ) -> dict:
        return self.context_adapter.get_context(
            query,
            exclude_external_turn_id=exclude_external_turn_id,
        )

    def get_external_turn_state(self, external_turn_id: str) -> dict:
        return self.context_adapter.get_external_turn_state(external_turn_id)

    def process_turn(
        self,
        player_input: str,
        narrative: str,
        external_turn_id: str | None = None,
        turn_version: int = 1,
    ) -> TurnResolutionResult:
        """Delegate only the deprecated narrative-first compatibility workflow."""
        return self.legacy_turn_service.process_turn(
            player_input=player_input,
            narrative=narrative,
            external_turn_id=external_turn_id,
            turn_version=turn_version,
        )
