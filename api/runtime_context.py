from __future__ import annotations

from contextvars import ContextVar

from bootstrap.campaign_runtime import CampaignRuntime

_current_runtime: ContextVar[CampaignRuntime | None] = ContextVar(
    "campaign_runtime",
    default=None,
)


def get_current_runtime() -> CampaignRuntime:
    """Return the campaign runtime bound to the current HTTP request."""
    runtime = _current_runtime.get()
    if runtime is None:
        raise RuntimeError(
            "campaign runtime is only available inside an HTTP request"
        )
    return runtime


class RuntimeProxy:
    """Compatibility adapter resolving a service from the request runtime."""

    def __init__(self, attribute: str) -> None:
        self._attribute = attribute

    def __getattr__(self, name: str):
        def dispatch(*args, **kwargs):
            runtime = get_current_runtime()
            target = getattr(getattr(runtime, self._attribute), name)
            return target(*args, **kwargs)

        return dispatch


campaign_repository = RuntimeProxy("campaign_repository")
character_repository = RuntimeProxy("character_repository")
entity_repository = RuntimeProxy("entity_repository")
turn_repository = RuntimeProxy("turn_repository")
world_service = RuntimeProxy("world_service")
campaign_state_service = RuntimeProxy("campaign_state_service")
memory_search_service = RuntimeProxy("memory_search_service")
context_builder = RuntimeProxy("context_builder")
turn_execution_lock = RuntimeProxy("turn_execution_lock")
character_creation_service = RuntimeProxy("character_creation_service")
combat_encounter_service = RuntimeProxy("combat_encounter_service")
campaign_turn_service = RuntimeProxy("campaign_turn_service")
silly_tavern_integration_service = RuntimeProxy(
    "silly_tavern_integration_service"
)
