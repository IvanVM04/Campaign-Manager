"""Validated API schemas for persistent campaign effects."""

import re
from enum import Enum

from pydantic import BaseModel, Field, StrictInt, model_validator


class EffectTypeInput(str, Enum):
    CONDITION = "condition"
    EXHAUSTION = "exhaustion"
    NARRATIVE = "narrative"


class EffectSourceInput(str, Enum):
    CREATURE = "creature"
    ITEM = "item"
    SPELL = "spell"
    ENVIRONMENT = "environment"
    NARRATIVE = "narrative"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class EffectDurationInput(str, Enum):
    PERMANENT = "permanent"
    CONDITIONAL = "conditional"
    CAMPAIGN_TIME = "campaign_time"
    ENCOUNTER_ROUNDS = "encounter_rounds"
    ENCOUNTER_TURNS = "encounter_turns"


class EffectStatusInput(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class PersistentEffectCreateIn(BaseModel):
    effect_type: EffectTypeInput
    effect_key: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    source_type: EffectSourceInput = EffectSourceInput.UNKNOWN
    source_entity_id: StrictInt | None = Field(default=None, ge=1)
    source_reference: str | None = Field(default=None, min_length=1, max_length=240)
    duration_type: EffectDurationInput = EffectDurationInput.PERMANENT
    duration_condition: str | None = Field(default=None, min_length=1, max_length=500)
    duration_minutes: StrictInt | None = Field(default=None, ge=1, le=525600)
    encounter_id: str | None = Field(default=None, min_length=1, max_length=120)
    duration_rounds: StrictInt | None = Field(default=None, ge=1, le=1000)
    duration_turns: StrictInt | None = Field(default=None, ge=1, le=10000)
    level: StrictInt | None = Field(default=None, ge=1, le=6)

    @model_validator(mode="after")
    def validate_effect_shape(self):
        if self.duration_condition is not None and not self.duration_condition.strip():
            raise ValueError("duration_condition must not be blank")
        timed_values = (
            self.duration_minutes, self.encounter_id,
            self.duration_rounds, self.duration_turns,
        )
        if self.duration_type == "permanent":
            if self.duration_condition is not None or any(value is not None for value in timed_values):
                raise ValueError("permanent effects cannot define a duration")
        elif self.duration_type == "conditional":
            if not self.duration_condition:
                raise ValueError("conditional effects require duration_condition")
            if any(value is not None for value in timed_values):
                raise ValueError("conditional effects cannot define timed duration fields")
        elif self.duration_type == "campaign_time":
            if self.duration_condition is not None or self.duration_minutes is None or any(
                value is not None for value in (self.encounter_id, self.duration_rounds, self.duration_turns)
            ):
                raise ValueError("campaign_time effects require duration_minutes only")
        elif self.duration_type in {"encounter_rounds", "encounter_turns"}:
            if not self.encounter_id or self.duration_condition is not None or self.duration_minutes is not None:
                raise ValueError("encounter-scoped effects require encounter_id and one encounter duration")
            if self.duration_type == "encounter_rounds":
                if self.duration_rounds is None or self.duration_turns is not None:
                    raise ValueError("encounter_rounds effects require duration_rounds only")
            elif self.duration_turns is None or self.duration_rounds is not None:
                raise ValueError("encounter_turns effects require duration_turns only")
        if self.effect_type == "condition":
            from rules_engine.dnd5e_2014.combat.conditions import Condition
            try:
                Condition(self.effect_key)
            except ValueError as exc:
                raise ValueError("effect_key must be a canonical D&D 5e condition") from exc
            if self.level is not None:
                raise ValueError("conditions cannot define a level")
        elif self.effect_type == "exhaustion":
            if self.effect_key != "exhaustion" or self.level is None:
                raise ValueError("exhaustion requires effect_key='exhaustion' and level 1-6")
        else:
            if self.level is not None:
                raise ValueError("narrative effects cannot define a mechanical level")
            if not re.fullmatch(
                r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}",
                self.effect_key,
            ):
                raise ValueError("narrative effect_key must be a simple slug")
        return self


class PersistentEffectStatusIn(BaseModel):
    status: EffectStatusInput
