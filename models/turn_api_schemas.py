"""Validated request/transport schemas for the turn API context."""

from typing import Literal
from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator

class TurnIn(BaseModel):
    player_input: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )
    dice_mode: Literal["automatic", "manual"] = "automatic"

    @field_validator("player_input")
    @classmethod
    def validate_player_input(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "player_input must not be empty"
            )

        return value


class ManualRollIn(BaseModel):
    pending_roll_id: str = Field(..., min_length=20, max_length=200)
    rolls: list[StrictInt] = Field(..., min_length=1, max_length=2)

    @field_validator("rolls")
    @classmethod
    def validate_d20_results(cls, values: list[int]) -> list[int]:
        if any(isinstance(value, bool) or value < 1 or value > 20 for value in values):
            raise ValueError("each manual d20 result must be between 1 and 20")
        return values


class DiceRollIn(BaseModel):
    """Validated input for a standalone dice-tray roll."""

    count: int = Field(default=1, ge=1, le=100)
    sides: int = Field(default=20, ge=2, le=1000)
    modifier: int = Field(default=0, ge=-10000, le=10000)
    advantage: bool = False
    disadvantage: bool = False

    @model_validator(mode="after")
    def validate_d20_modes(self):
        if (self.advantage or self.disadvantage) and (
            self.sides != 20 or self.count != 1
        ):
            raise ValueError(
                "advantage and disadvantage require exactly one d20"
            )
        return self


class ClarificationIn(BaseModel):
    pending_clarification_id: str = Field(..., min_length=20, max_length=200)
    answer: str = Field(..., min_length=1, max_length=5000)

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("answer must not be empty")
        return value
