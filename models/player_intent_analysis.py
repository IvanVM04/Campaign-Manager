"""Versioned, evidence-bound semantic interpretation of a player utterance."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any


SCHEMA_VERSION = 1
MAX_STEPS = 8
MAX_TARGETS_PER_STEP = 6


class UtteranceCategory(str, Enum):
    ACTION = "action"
    QUESTION = "question"
    DIALOGUE = "dialogue"
    REPORT = "report"
    PLAN = "plan"
    CORRECTION = "correction"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class IntentActor(str, Enum):
    PLAYER = "player"
    NPC = "npc"
    OTHER = "other"
    UNKNOWN = "unknown"


class IntentModality(str, Enum):
    ATTEMPTED = "attempted"
    COMPLETED = "completed"
    OBSERVED = "observed"
    PLANNED = "planned"
    CONDITIONAL = "conditional"
    QUESTION = "question"
    DIALOGUE = "dialogue"
    REPORTED = "reported"
    NEGATED = "negated"
    CORRECTION = "correction"
    UNKNOWN = "unknown"


class IntentPolarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNCERTAIN = "uncertain"


class PlayerReportedOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    NOT_CLAIMED = "not_claimed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class IntentStep:
    index: int
    source_excerpt: str
    actor: IntentActor
    action: str
    modality: IntentModality
    polarity: IntentPolarity
    reported_outcome: PlayerReportedOutcome
    target_mentions: tuple[str, ...] = ()
    attributed_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "source_excerpt": self.source_excerpt,
            "actor": self.actor.value,
            "action": self.action,
            "modality": self.modality.value,
            "polarity": self.polarity.value,
            "reported_outcome": self.reported_outcome.value,
            "target_mentions": list(self.target_mentions),
            "attributed_to": self.attributed_to,
        }


@dataclass(frozen=True, slots=True)
class PlayerIntentAnalysis:
    category: UtteranceCategory
    steps: tuple[IntentStep, ...]
    active_step_index: int | None
    requires_clarification: bool = False
    clarification_question: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported player intent schema version")
        if not isinstance(self.category, UtteranceCategory):
            raise TypeError("category must be an UtteranceCategory")
        if not isinstance(self.steps, tuple) or len(self.steps) > MAX_STEPS:
            raise ValueError("steps must be a tuple with at most 8 items")
        if any(not isinstance(step, IntentStep) for step in self.steps):
            raise TypeError("steps must contain IntentStep values")
        if tuple(step.index for step in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("step indices must be contiguous and ordered")
        if self.active_step_index is not None and (
            isinstance(self.active_step_index, bool)
            or not isinstance(self.active_step_index, int)
            or not 0 <= self.active_step_index < len(self.steps)
        ):
            raise ValueError("active_step_index must reference an existing step")
        if not isinstance(self.requires_clarification, bool):
            raise TypeError("requires_clarification must be a boolean")
        if self.requires_clarification:
            if not isinstance(self.clarification_question, str) or not self.clarification_question.strip() or len(self.clarification_question) > 300:
                raise ValueError("clarification requires a bounded question")
        elif self.clarification_question is not None:
            raise ValueError("clarification_question requires requires_clarification")

    @property
    def active_step(self) -> IntentStep | None:
        return None if self.active_step_index is None else self.steps[self.active_step_index]

    @property
    def is_actionable(self) -> bool:
        step = self.active_step
        return bool(
            step is not None
            and step.actor is IntentActor.PLAYER
            and step.modality is IntentModality.ATTEMPTED
            and step.polarity is IntentPolarity.POSITIVE
        )

    @property
    def allows_world_proposal(self) -> bool:
        if self.category not in {
            UtteranceCategory.ACTION, UtteranceCategory.CORRECTION,
            UtteranceCategory.MIXED, UtteranceCategory.REPORT,
        }:
            return False
        allowed = {
            IntentModality.ATTEMPTED, IntentModality.COMPLETED,
            IntentModality.OBSERVED, IntentModality.REPORTED,
            IntentModality.CORRECTION,
        }
        return any(
            step.polarity is IntentPolarity.POSITIVE
            and step.modality in allowed
            and (
                step.actor is IntentActor.PLAYER
                or (
                    step.modality is IntentModality.REPORTED
                    and step.actor in {IntentActor.NPC, IntentActor.OTHER}
                    and step.attributed_to is not None
                )
            )
            for step in self.steps
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "category": self.category.value,
            "steps": [step.to_dict() for step in self.steps],
            "active_step_index": self.active_step_index,
            "requires_clarification": self.requires_clarification,
            "clarification_question": self.clarification_question,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_payload(cls, payload: Any, *, source_text: str) -> "PlayerIntentAnalysis":
        if not isinstance(source_text, str) or not source_text.strip():
            raise ValueError("source_text must be non-empty")
        expected = {
            "schema_version", "category", "steps", "active_step_index",
            "requires_clarification", "clarification_question",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("intent_analysis has missing or unexpected fields")
        version = payload["schema_version"]
        if isinstance(version, bool) or version != SCHEMA_VERSION:
            raise ValueError("unsupported player intent schema version")
        raw_steps = payload["steps"]
        if not isinstance(raw_steps, list) or len(raw_steps) > MAX_STEPS:
            raise ValueError("steps must be a bounded array")
        steps = []
        for index, raw in enumerate(raw_steps):
            required = {
                "index", "source_excerpt", "actor", "action", "modality",
                "polarity", "reported_outcome", "target_mentions", "attributed_to",
            }
            if not isinstance(raw, dict) or set(raw) != required:
                raise ValueError("intent step has missing or unexpected fields")
            if isinstance(raw["index"], bool) or raw["index"] != index:
                raise ValueError("step indices must be contiguous and ordered")
            excerpt = _text(raw["source_excerpt"], "source_excerpt", 300)
            if not _evidence(source_text, excerpt):
                raise ValueError("source_excerpt is not grounded in player input")
            action = _text(raw["action"], "action", 500)
            targets = raw["target_mentions"]
            if not isinstance(targets, list) or len(targets) > MAX_TARGETS_PER_STEP:
                raise ValueError("target_mentions must be a bounded array")
            target_values = []
            for value in targets:
                value = _text(value, "target mention", 120)
                if not _evidence(source_text, value):
                    raise ValueError("target mention is not literal utterance evidence")
                target_values.append(value)
            attribution = raw["attributed_to"]
            if attribution is not None:
                attribution = _text(attribution, "attributed_to", 120)
                if not _evidence(source_text, attribution):
                    raise ValueError("attribution is not grounded in player input")
            steps.append(IntentStep(
                index=index, source_excerpt=excerpt, actor=_enum(IntentActor, raw["actor"]),
                action=action, modality=_enum(IntentModality, raw["modality"]),
                polarity=_enum(IntentPolarity, raw["polarity"]),
                reported_outcome=_enum(PlayerReportedOutcome, raw["reported_outcome"]),
                target_mentions=tuple(target_values), attributed_to=attribution,
            ))
        return cls(
            category=_enum(UtteranceCategory, payload["category"]),
            steps=tuple(steps),
            active_step_index=payload["active_step_index"],
            requires_clarification=payload["requires_clarification"],
            clarification_question=payload["clarification_question"],
            schema_version=version,
        )

    @classmethod
    def from_json(cls, payload: str | None, *, source_text: str) -> "PlayerIntentAnalysis | None":
        if payload is None:
            return None
        if not isinstance(payload, str):
            raise TypeError("intent JSON must be text or None")
        return cls.from_payload(json.loads(payload), source_text=source_text)

    @classmethod
    def conservative_legacy(cls, source_text: str) -> "PlayerIntentAnalysis":
        """Fail-safe compatibility for legacy providers without the v1 envelope."""
        text = source_text.strip()
        folded = unicodedata.normalize("NFKC", text).casefold()
        question = "?" in text or text.startswith("¿") or bool(re.match(r"^(qué|quién|como|cómo|cuando|cuándo|donde|dónde|por qué)\b", folded))
        conditional = bool(re.search(r"\b(si|cuando|en caso de que|if|when|suppose)\b", folded))
        planned = bool(re.search(r"\b(mañana|luego|después|planeo|pienso|quiero|me gustaría|voy a|haré|tomorrow|later|plan to|i will|i want to)\b", folded))
        quoted = any(mark in text for mark in ('"', "“", "”", "«", "»"))
        failure = bool(re.search(r"\b(no pude|no conseguí|no consegui|fallé|falle|fracasé|fracase|falló|fallo|failed|could not|couldn't)\b", folded))
        negated = bool(re.search(r"\b(no|nunca|jamás|jamas|not|never)\b", folded)) and not failure
        if question:
            category, modality = UtteranceCategory.QUESTION, IntentModality.QUESTION
        elif quoted:
            category, modality = UtteranceCategory.DIALOGUE, IntentModality.DIALOGUE
        elif conditional:
            category, modality = UtteranceCategory.PLAN, IntentModality.CONDITIONAL
        elif planned:
            category, modality = UtteranceCategory.PLAN, IntentModality.PLANNED
        elif negated:
            category, modality = UtteranceCategory.ACTION, IntentModality.NEGATED
        else:
            category, modality = UtteranceCategory.ACTION, IntentModality.ATTEMPTED
        polarity = IntentPolarity.NEGATIVE if negated or failure else IntentPolarity.POSITIVE
        active = 0 if modality is IntentModality.ATTEMPTED and polarity is IntentPolarity.POSITIVE else None
        return cls(
            category=category,
            steps=(IntentStep(
                index=0, source_excerpt=text[:300], actor=IntentActor.PLAYER,
                action=text[:500], modality=modality, polarity=polarity,
                reported_outcome=PlayerReportedOutcome.FAILURE if failure else PlayerReportedOutcome.NOT_CLAIMED,
            ),),
            active_step_index=active,
        )


def _text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{field} must not exceed {limit} characters")
    return value


def _enum(enum_type, value: Any):
    if not isinstance(value, str):
        raise TypeError("enum fields must be strings")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"unsupported {enum_type.__name__}: {value}") from exc


def _evidence(source: str, fragment: str) -> bool:
    normalize = lambda value: unicodedata.normalize("NFKC", value).casefold()
    return normalize(fragment) in normalize(source)
