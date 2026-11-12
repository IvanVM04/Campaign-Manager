"""Validated request/transport schemas for the world API context."""

from pydantic import BaseModel, Field, field_validator, model_validator


class WorldEntityBootstrapIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    entity_type: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=2000)
    aliases: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for alias in values:
            alias = alias.strip()
            if not alias:
                raise ValueError("entity aliases cannot be blank")
            if len(alias) > 100:
                raise ValueError("entity aliases must be at most 100 characters")
            key = alias.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(alias)
        return normalized

    @field_validator("name", "entity_type")
    @classmethod
    def validate_entity_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("entity text must not be empty")
        return value


class WorldBootstrapIn(BaseModel):
    entities: list[WorldEntityBootstrapIn] = Field(..., min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_unique_entity_names(self):
        names = [entity.name.casefold() for entity in self.entities]
        if len(names) != len(set(names)):
            raise ValueError("entity names must be unique")
        return self
