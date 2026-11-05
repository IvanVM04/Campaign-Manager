from typing import Protocol, runtime_checkable

from models.world_state import WorldState


@runtime_checkable
class WorldStatePort(Protocol):
    """Minimal world-state operations required by campaign state assembly."""

    campaign_id: int

    def get_world(self) -> WorldState:
        ...

    def load(self) -> WorldState:
        ...

    def save(self) -> None:
        ...
