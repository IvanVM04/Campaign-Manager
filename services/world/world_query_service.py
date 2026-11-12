from models.world_read_models import (
    WorldEntityPage,
    WorldEntityRead,
)
from models.world_state import WorldState


class WorldQueryService:
    """Build read-only projections from the in-memory campaign world."""

    def list_entities(
        self,
        world: WorldState,
        *,
        query: str | None = None,
        entity_type: str | None = None,
        active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> WorldEntityPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must not be negative")

        normalized_query = (query or "").strip().casefold()
        normalized_type = (entity_type or "").strip().casefold()

        entities = sorted(
            world.entities.values(),
            key=lambda entity: (
                entity.id is None,
                entity.id if entity.id is not None else 0,
                entity.name.casefold(),
            ),
        )

        filtered = []
        for entity in entities:
            searchable_text = (
                f"{entity.name} {entity.description} {entity.notes} {' '.join(entity.aliases)}"
            ).casefold()
            if normalized_query and normalized_query not in searchable_text:
                continue
            if normalized_type and entity.entity_type.casefold() != normalized_type:
                continue
            if active is not None and entity.active is not active:
                continue
            filtered.append(
                WorldEntityRead(
                    id=entity.id,
                    name=entity.name,
                    entity_type=entity.entity_type,
                    description=entity.description,
                    notes=entity.notes,
                    active=entity.active,
                    aliases=tuple(entity.aliases),
                )
            )

        return WorldEntityPage(
            items=tuple(filtered[offset : offset + limit]),
            total=len(filtered),
            limit=limit,
            offset=offset,
        )
