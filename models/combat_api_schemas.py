"""Validated request schemas for the combat encounter API."""

from typing import Literal

from pydantic import BaseModel, Field, StrictInt, model_validator


class EncounterParticipantIn(BaseModel):
    character_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    max_hp: int | None = Field(default=None, ge=1, le=10000)
    current_hp: int | None = Field(default=None, ge=0, le=10000)
    armor_class: int | None = Field(default=None, ge=0, le=100)
    dexterity: int | None = Field(default=None, ge=1, le=30)
    is_player_character: bool = False

    @model_validator(mode="after")
    def validate_source(self):
        if self.character_id is not None:
            if any(value is not None for value in (
                self.name, self.max_hp, self.current_hp,
                self.armor_class, self.dexterity,
            )):
                raise ValueError("character_id cannot be combined with manual combatant stats")
            return self
        required = {
            "name": self.name,
            "max_hp": self.max_hp,
            "armor_class": self.armor_class,
            "dexterity": self.dexterity,
        }
        missing = [key for key, value in required.items() if value is None]
        if missing:
            raise ValueError(f"manual combatant is missing: {', '.join(missing)}")
        if self.current_hp is not None and self.max_hp is not None and self.current_hp > self.max_hp:
            raise ValueError("current_hp cannot exceed max_hp")
        if self.is_player_character:
            raise ValueError("manual combatants cannot be marked as player characters")
        return self


class EncounterCreateIn(BaseModel):
    encounter_id: str | None = Field(default=None, min_length=1, max_length=100)
    participants: list[EncounterParticipantIn] = Field(..., min_length=1, max_length=30)


class EncounterStartIn(BaseModel):
    dice_mode: Literal["automatic", "manual"] = "automatic"
    manual_rolls: dict[str, StrictInt] = Field(default_factory=dict)
    initiative_order: list[str] | None = None

    @model_validator(mode="after")
    def validate_manual_rolls(self):
        if any(isinstance(value, bool) or not 1 <= value <= 20 for value in self.manual_rolls.values()):
            raise ValueError("manual initiative rolls must be integers from 1 to 20")
        return self


class EncounterTurnIn(BaseModel):
    expected_round: int | None = Field(default=None, ge=1)
    expected_turn_index: int | None = Field(default=None, ge=0)
