"""Thin read-oriented façade over the active SillyTavern context adapter."""

from __future__ import annotations

from .context_adapter import SillyTavernContextAdapter


class SillyTavernIntegrationService:
    """Preserve the runtime-facing adapter while keeping collaborators separate.

    Context/history reads are delegated to SillyTavernContextAdapter.
    This façade exposes only active context and transcript-state reads.
    """

    def __init__(
        self,
        *,
        context_adapter: SillyTavernContextAdapter,
    ) -> None:
        if not isinstance(context_adapter, SillyTavernContextAdapter):
            raise TypeError("context_adapter must be a SillyTavernContextAdapter")
        self.context_adapter = context_adapter

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
