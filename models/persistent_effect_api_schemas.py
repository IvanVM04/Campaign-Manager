"""Validated API schemas for persistent campaign effects."""

from typing import Literal

from pydantic import BaseModel, Field, StrictInt, model_validator


EffectTypeInput = Literal["condition", "exhaustion", "narrative"]
EffectSourceInput = Literal[
    "creature", "item", "spell", "environment", "narrative", "system", "unknown"
]
EffectDurationInput = Literal["permanent", "conditional"]
EffectStatusInput = Literal["active", "suspended"]


class PersistentEffectCreateIn(BaseModel):
    effect_type: EffectTypeInput
    effect_key: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    source_type: EffectSourceInput = "unknown"
    source_entity_id: StrictInt | None = Field(default=None, ge=1)
    source_reference: str | None = Field(default=None, min_length=1, max_length=240)
    duration_type: EffectDurationInput = "permanent"
    duration_condition: str | None = Field(default=None, min_length=1, max_length=500)
    level: StrictInt | None = Field(default=None, ge=1, le=6)

    @model_validator(mode="after")
    def validate_effect_shape(self):
        if self.duration_type == "conditional" and not self.duration_condition:
            raise ValueError("conditional effects require duration_condition")
        if self.duration_type == "permanent" and self.duration_condition is not None:
            raise ValueError("permanent effects cannot define duration_condition")
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
            if not self.effect_key.replace("-", "").replace("_", "").isalnum():
                raise ValueError("narrative effect_key must be a simple slug")
        return self


class PersistentEffectStatusIn(BaseModel):
    status: EffectStatusInput
