from collections.abc import Iterable

from models.event import Event


class WorldVisibilityPolicy:
    """Central visibility rules for world data returned to player-facing reads."""

    @staticmethod
    def is_event_visible_to_players(event: Event) -> bool:
        """Secret events are GM-only and must never enter player read models."""
        return not bool(getattr(event, "secret", False))

    @classmethod
    def player_visible_events(
        cls,
        events: Iterable[Event],
    ) -> tuple[Event, ...]:
        """Return player-visible events without exposing the source collection."""
        return tuple(
            event
            for event in events
            if cls.is_event_visible_to_players(event)
        )
