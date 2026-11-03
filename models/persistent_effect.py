"""Persistent effects attached to campaign entities, independent from encounters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from rules_engine.dnd5e_2014.combat.conditions import Condition


class EffectType(str, Enum):
    CONDITION = "condition"
    EXHAUSTION = "exhaustion"
    NARRATIVE = "narrative"


class EffectSourceType(str, Enum):
    CREATURE = "creature"
    ITEM = "item"
    SPELL = "spell"
    ENVIRONMENT = "environment"
    NARRATIVE = "narrative"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class EffectDurationType(str, Enum):
    PERMANENT = "permanent"
    CONDITIONAL = "conditional"


class EffectStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class PersistentEffect:
    campaign_id: int
    entity_id: int
    effect_type: EffectType
    effect_key: str
    name: str
    description: str = ""
    source_type: EffectSourceType = EffectSourceType.UNKNOWN
    source_entity_id: int | None = None
    source_reference: str | None = None
    duration_type: EffectDurationType = EffectDurationType.PERMANENT
    duration_condition: str | None = None
    level: int | None = None
    id: str = ""
    status: EffectStatus = EffectStatus.ACTIVE
    created_at: str | None = None
    updated_at: str | None = None
    removed_at: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.campaign_id, bool) or not isinstance(self.campaign_id, int) or self.campaign_id < 1:
            raise ValueError("campaign_id must be a positive integer")
        if isinstance(self.entity_id, bool) or not isinstance(self.entity_id, int) or self.entity_id < 1:
            raise ValueError("entity_id must be a positive integer")
        if self.source_entity_id is not None and (
            isinstance(self.source_entity_id, bool)
            or not isinstance(self.source_entity_id, int)
            or self.source_entity_id < 1
        ):
            raise ValueError("source_entity_id must be a positive integer or None")
        if not isinstance(self.effect_type, EffectType):
            object.__setattr__(self, "effect_type", EffectType(self.effect_type))
        if not isinstance(self.source_type, EffectSourceType):
            object.__setattr__(self, "source_type", EffectSourceType(self.source_type))
        if not isinstance(self.duration_type, EffectDurationType):
            object.__setattr__(self, "duration_type", EffectDurationType(self.duration_type))
        if not isinstance(self.status, EffectStatus):
            object.__setattr__(self, "status", EffectStatus(self.status))
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 120:
            raise ValueError("name must contain 1-120 characters")
        if not isinstance(self.description, str) or len(self.description) > 2000:
            raise ValueError("description must contain at most 2000 characters")
        if not isinstance(self.effect_key, str) or not self.effect_key.strip() or len(self.effect_key) > 80:
            raise ValueError("effect_key must contain 1-80 characters")
        if self.duration_type is EffectDurationType.CONDITIONAL:
            if not isinstance(self.duration_condition, str) or not self.duration_condition.strip():
                raise ValueError("conditional effects require a duration condition")
        elif self.duration_condition is not None:
            raise ValueError("permanent effects cannot define a duration condition")
        if self.effect_type is EffectType.CONDITION:
            try:
                Condition(self.effect_key)
            except ValueError as exc:
                raise ValueError("effect_key must be a canonical D&D 5e condition") from exc
            if self.level is not None:
                raise ValueError("conditions cannot define a level")
        elif self.effect_type is EffectType.EXHAUSTION:
            if self.effect_key != "exhaustion":
                raise ValueError("exhaustion effect_key must be 'exhaustion'")
            if isinstance(self.level, bool) or not isinstance(self.level, int) or not 1 <= self.level <= 6:
                raise ValueError("exhaustion level must be an integer from 1 to 6")
        else:
            if self.level is not None:
                raise ValueError("narrative effects cannot define a mechanical level")
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", self.effect_key):
                raise ValueError("narrative effect_key must be a simple slug")
        if not self.id:
            object.__setattr__(self, "id", uuid4().hex)
        if not re.fullmatch(r"[0-9a-f]{32}", self.id):
            raise ValueError("id must be a 32-character hexadecimal identifier")
        if self.status is EffectStatus.REMOVED and self.removed_at is None and self.created_at is not None:
            raise ValueError("persisted removed effects require removed_at")
