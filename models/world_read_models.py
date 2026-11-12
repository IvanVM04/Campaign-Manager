from pydantic import BaseModel, ConfigDict


class WorldEntityRead(BaseModel):
    """Immutable API projection of a campaign world entity."""

    model_config = ConfigDict(frozen=True)

    id: int | None
    name: str
    entity_type: str
    description: str
    notes: str
    active: bool
    aliases: tuple[str, ...] = ()


class WorldEntityPage(BaseModel):
    """Immutable paginated result for world entity browsing."""

    model_config = ConfigDict(frozen=True)

    items: tuple[WorldEntityRead, ...]
    total: int
    limit: int
    offset: int
