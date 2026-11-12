"""Validated request/transport schemas for the campaign API context."""

from pydantic import BaseModel, Field, field_validator

class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    system: str = Field(default="D&D 5e 2014", min_length=1, max_length=100)
    tone: str = Field(default="", max_length=100)
    summary: str = Field(default="", max_length=5000)

    @field_validator("name", "system")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value


class CampaignUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        max_length=200,
    )
    system: str | None = Field(
        default=None,
        max_length=100,
    )
    tone: str | None = Field(
        default=None,
        max_length=100,
    )
    summary: str | None = Field(
        default=None,
        max_length=5000,
    )

    @field_validator("name", "system")
    @classmethod
    def validate_optional_required_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")

        return value

    @field_validator("tone", "summary")
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        return value.strip() if value is not None else None


class CampaignSessionUpdate(BaseModel):
    session_id: int | None = None


class SessionIn(BaseModel):
    number: int = Field(
        ...,
        ge=1,
    )
    title: str = Field(
        default="",
        max_length=200,
    )
    summary: str = Field(
        default="",
        max_length=5000,
    )
    start_location: str = Field(
        default="",
        max_length=200,
    )
    end_location: str = Field(
        default="",
        max_length=200,
    )
    notes: str = Field(
        default="",
        max_length=5000,
    )


class ActiveCharacterUpdate(BaseModel):
    character_id: int | None = Field(
        default=None,
        ge=1,
    )
