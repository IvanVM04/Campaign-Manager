from pydantic import BaseModel, ConfigDict


class SessionRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    number: int
    title: str
    summary: str
    start_location: str
    end_location: str
    turn_count: int
    last_turn_at: str | None


class SessionPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[SessionRead, ...]
    total: int
    limit: int
    offset: int
