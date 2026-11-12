from collections.abc import Iterable

from models.event import Event


class WorldVisibilityPolicy:
    """Central event-visibility and temporal-currentness policy for player reads."""

    @staticmethod
    def is_event_visible_to_players(
        event: Event,
        *,
        character_entity_id: int | None = None,
    ) -> bool:
        """Fail closed for GM-only and character-scoped knowledge without a matching character."""
        if bool(getattr(event, "secret", False)):
            return False
        scope = getattr(event, "visibility_scope", "public")
        if scope == "public":
            return True
        if scope == "character":
            if (
                isinstance(character_entity_id, bool)
                or not isinstance(character_entity_id, int)
                or character_entity_id < 1
            ):
                return False
            known_by = getattr(event, "known_by_entity_ids", ())
            return character_entity_id in known_by
        return False

    @classmethod
    def player_visible_events(
        cls,
        events: Iterable[Event],
        *,
        character_entity_id: int | None = None,
    ) -> tuple[Event, ...]:
        """Return a detached tuple of events visible to this player-character perspective."""
        return tuple(
            event
            for event in events
            if cls.is_event_visible_to_players(
                event,
                character_entity_id=character_entity_id,
            )
        )

    @staticmethod
    def superseded_event_ids(events: Iterable[Event]) -> frozenset[str]:
        """IDs of historical events explicitly replaced by a later event."""
        superseded_ids: set[str] = set()
        for event in events:
            superseded_event_id = event.supersedes_event_id
            if isinstance(superseded_event_id, str):
                superseded_ids.add(superseded_event_id)
        return frozenset(superseded_ids)

    @classmethod
    def is_event_current(cls, event: Event, events: Iterable[Event]) -> bool:
        return event.id not in cls.superseded_event_ids(events)
