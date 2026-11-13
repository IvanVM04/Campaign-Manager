"""Versioned, evidence-bound semantic interpretation of a player utterance."""
from __future__ import annotations

import dataclasses
import enum
import json
import re
import typing
import unicodedata

from models.semantic_frames import (
    MAX_RELATION_CLAIMS,
    SemanticActionFrame,
    SemanticRelationClaim,
)

SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})
MAX_STEPS = 8
MAX_TARGETS_PER_STEP = 6


class UtteranceCategory(str, enum.Enum):
    ACTION = "action"
    QUESTION = "question"
    DIALOGUE = "dialogue"
    REPORT = "report"
    PLAN = "plan"
    CORRECTION = "correction"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class IntentActor(str, enum.Enum):
    PLAYER = "player"
    NPC = "npc"
    OTHER = "other"
    UNKNOWN = "unknown"


class IntentModality(str, enum.Enum):
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


class IntentPolarity(str, enum.Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNCERTAIN = "uncertain"


class PlayerReportedOutcome(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    NOT_CLAIMED = "not_claimed"
    UNCERTAIN = "uncertain"


@dataclasses.dataclass(frozen=True, slots=True)
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
    action_frame: SemanticActionFrame | None = None

    def to_dict(
        self,
        *,
        include_action_frame: bool = False,
    ) -> dict[str, typing.Any]:
        payload: dict[str, typing.Any] = {
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
        if include_action_frame:
            payload["action_frame"] = (
                None if self.action_frame is None else self.action_frame.to_dict()
            )
        return payload


@dataclasses.dataclass(frozen=True, slots=True)
class PlayerIntentAnalysis:
    category: UtteranceCategory
    steps: tuple[IntentStep, ...]
    active_step_index: int | None
    requires_clarification: bool = False
    clarification_question: str | None = None
    schema_version: int = 1
    relation_claims: tuple[SemanticRelationClaim, ...] = ()

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version not in SUPPORTED_SCHEMA_VERSIONS
        ):
            raise ValueError("unsupported player intent schema version")
        if not isinstance(self.category, UtteranceCategory):
            raise TypeError("category must be an UtteranceCategory")
        if not isinstance(self.steps, tuple) or len(self.steps) > MAX_STEPS:
            raise ValueError("steps must be a tuple with at most 8 items")
        if any(not isinstance(step, IntentStep) for step in self.steps):
            raise TypeError("steps must contain IntentStep values")
        if self.schema_version == 1 and (
            self.relation_claims
            or any(step.action_frame is not None for step in self.steps)
        ):
            raise ValueError("v1 intent analysis cannot contain semantic frames")
        if self.schema_version == 2 and any(
            not isinstance(step.action_frame, SemanticActionFrame)
            for step in self.steps
        ):
            raise TypeError("v2 intent steps require a SemanticActionFrame")
        if not isinstance(self.relation_claims, tuple) or len(self.relation_claims) > MAX_RELATION_CLAIMS:
            raise ValueError("relation_claims must be a tuple with at most 8 items")
        if any(
            not isinstance(claim, SemanticRelationClaim)
            or claim.step_index >= len(self.steps)
            for claim in self.relation_claims
        ):
            raise ValueError("relation_claims must reference an existing intent step")
        for claim in self.relation_claims:
            step_evidence = self.steps[claim.step_index].source_excerpt
            grounded_values = (
                claim.subject.text,
                claim.predicate,
                claim.object.text,
                claim.source_excerpt,
                (
                    claim.attributed_to.text
                    if claim.attributed_to is not None
                    else None
                ),
                claim.temporal_expression,
            )
            if any(
                value is not None and not _evidence(step_evidence, value)
                for value in grounded_values
            ):
                raise ValueError(
                    "relation claim is not grounded in its referenced intent step"
                )
        if tuple(step.index for step in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("step indices must be contiguous and ordered")
        if self.active_step_index is not None and (
            isinstance(self.active_step_index, bool)
            or not isinstance(self.active_step_index, int)
            or not 0 <= self.active_step_index < len(self.steps)
        ):
            raise ValueError("active_step_index must reference an existing step")
        resolved_modalities = {
            IntentModality.COMPLETED,
            IntentModality.OBSERVED,
            IntentModality.REPORTED,
            IntentModality.CORRECTION,
            IntentModality.DIALOGUE,
        }
        if self.active_step_index is not None and any(
            previous.modality not in resolved_modalities
            or previous.polarity is not IntentPolarity.POSITIVE
            for previous in self.steps[: self.active_step_index]
        ):
            raise ValueError("active step cannot skip an earlier unresolved step")
        active = (
            self.steps[self.active_step_index]
            if self.active_step_index is not None
            else None
        )
        if active is not None and active.reported_outcome not in {
            PlayerReportedOutcome.NOT_CLAIMED,
            PlayerReportedOutcome.UNCERTAIN,
        }:
            raise ValueError("a resolved reported outcome cannot be the active step")
        if active is not None and self.category not in {
            UtteranceCategory.ACTION,
            UtteranceCategory.MIXED,
        }:
            raise ValueError("only action or mixed utterances may have an active step")
        active_index = self.active_step_index
        if active_index is not None:
            future_resolved = {
                IntentModality.COMPLETED,
                IntentModality.OBSERVED,
                IntentModality.REPORTED,
                IntentModality.CORRECTION,
            }
            if any(
                later.modality in future_resolved
                and later.polarity is IntentPolarity.POSITIVE
                for later in self.steps[active_index + 1 :]
            ):
                raise ValueError("future steps cannot be reported as resolved evidence")
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
            and step.reported_outcome in {
                PlayerReportedOutcome.NOT_CLAIMED,
                PlayerReportedOutcome.UNCERTAIN,
            }
        )

    @property
    def allows_world_proposal(self) -> bool:
        if self.category not in {
            UtteranceCategory.ACTION, UtteranceCategory.CORRECTION,
            UtteranceCategory.MIXED, UtteranceCategory.REPORT,
            UtteranceCategory.DIALOGUE,
        }:
            return False
        allowed = {
            IntentModality.ATTEMPTED, IntentModality.COMPLETED,
            IntentModality.OBSERVED, IntentModality.REPORTED,
            IntentModality.CORRECTION, IntentModality.DIALOGUE,
        }
        return any(
            step.polarity is IntentPolarity.POSITIVE
            and step.modality in allowed
            and (
                step.modality is not IntentModality.ATTEMPTED
                or step.index == self.active_step_index
            )
            and (
                step.actor is IntentActor.PLAYER
                or (
                    step.modality in {
                        IntentModality.OBSERVED,
                        IntentModality.REPORTED,
                    }
                    and step.actor in {IntentActor.NPC, IntentActor.OTHER}
                    and step.attributed_to is not None
                )
            )
            for step in self.steps
        )

    def to_dict(self) -> dict[str, typing.Any]:
        payload: dict[str, typing.Any] = {
            "schema_version": self.schema_version,
            "category": self.category.value,
            "steps": [
                step.to_dict(include_action_frame=self.schema_version >= 2)
                for step in self.steps
            ],
            "active_step_index": self.active_step_index,
            "requires_clarification": self.requires_clarification,
            "clarification_question": self.clarification_question,
        }
        if self.schema_version >= 2:
            payload["relation_claims"] = [
                claim.to_dict() for claim in self.relation_claims
            ]
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_payload(
        cls,
        payload: typing.Any,
        *,
        source_text: str,
        evidence_text: str | None = None,
    ) -> PlayerIntentAnalysis:
        if not isinstance(source_text, str) or not source_text.strip():
            raise ValueError("source_text must be non-empty")
        if len(source_text) > 20000:
            raise ValueError("source_text must not exceed 20000 characters")
        evidence = source_text if evidence_text is None else evidence_text
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("evidence_text must be non-empty")
        if len(evidence) > 20000:
            raise ValueError("evidence_text must not exceed 20000 characters")
        base_expected = {
            "schema_version", "category", "steps", "active_step_index",
            "requires_clarification", "clarification_question",
        }
        if not isinstance(payload, dict) or not base_expected.issubset(payload):
            raise ValueError("intent_analysis has missing or unexpected fields")
        version = payload["schema_version"]
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version not in SUPPORTED_SCHEMA_VERSIONS
        ):
            raise ValueError("unsupported player intent schema version")
        expected = (
            base_expected
            if version == 1
            else base_expected | {"relation_claims"}
        )
        if set(payload) != expected:
            raise ValueError("intent_analysis has missing or unexpected fields")
        raw_steps = payload["steps"]
        if not isinstance(raw_steps, list) or len(raw_steps) > MAX_STEPS:
            raise ValueError("steps must be a bounded array")
        steps = []
        for index, raw in enumerate(raw_steps):
            required = {
                "index", "source_excerpt", "actor", "action", "modality",
                "polarity", "reported_outcome", "target_mentions", "attributed_to",
            }
            if version >= 2:
                required.add("action_frame")
            if not isinstance(raw, dict) or set(raw) != required:
                raise ValueError("intent step has missing or unexpected fields")
            if isinstance(raw["index"], bool) or raw["index"] != index:
                raise ValueError("step indices must be contiguous and ordered")
            excerpt = _text(raw["source_excerpt"], "source_excerpt", 300)
            if not _evidence(evidence, excerpt):
                raise ValueError("source_excerpt is not grounded in player input")
            action = _text(raw["action"], "action", 500)
            targets = raw["target_mentions"]
            if not isinstance(targets, list) or len(targets) > MAX_TARGETS_PER_STEP:
                raise ValueError("target_mentions must be a bounded array")
            target_values = []
            for value in targets:
                value = _text(value, "target mention", 120)
                if not _evidence(evidence, value):
                    raise ValueError("target mention is not literal utterance evidence")
                if version >= 2 and not _evidence(excerpt, value):
                    raise ValueError("target mention is not grounded in its intent step")
                target_values.append(value)
            attribution = raw["attributed_to"]
            if attribution is not None:
                attribution = _text(attribution, "attributed_to", 120)
                if not _evidence(evidence, attribution):
                    raise ValueError("attribution is not grounded in player input")
                if version >= 2 and not _evidence(excerpt, attribution):
                    raise ValueError("attribution is not grounded in its intent step")
            action_frame = None
            if version >= 2:
                raw_frame = raw["action_frame"]
                if raw_frame is None:
                    raise ValueError("v2 intent step requires an action_frame")
                action_frame = SemanticActionFrame.from_payload(
                    raw_frame,
                    evidence_text=evidence,
                )
                if not _evidence(excerpt, action_frame.predicate):
                    raise ValueError("action predicate is not grounded in its intent step")
                if any(
                    not _evidence(excerpt, argument.mention.text)
                    for argument in action_frame.arguments
                ):
                    raise ValueError(
                        "action argument is not grounded in its intent step"
                    )
            steps.append(IntentStep(
                index=index, source_excerpt=excerpt, actor=_enum(IntentActor, raw["actor"]),
                action=action, modality=_enum(IntentModality, raw["modality"]),
                polarity=_enum(IntentPolarity, raw["polarity"]),
                reported_outcome=_enum(PlayerReportedOutcome, raw["reported_outcome"]),
                target_mentions=tuple(target_values), attributed_to=attribution,
                action_frame=action_frame,
            ))
        relation_claims: tuple[SemanticRelationClaim, ...] = ()
        if version >= 2:
            raw_claims = payload["relation_claims"]
            if not isinstance(raw_claims, list) or len(raw_claims) > MAX_RELATION_CLAIMS:
                raise ValueError("relation_claims must be a bounded array")
            relation_claims = tuple(
                SemanticRelationClaim.from_payload(item, evidence_text=evidence)
                for item in raw_claims
            )
        return cls(
            category=_enum(UtteranceCategory, payload["category"]),
            steps=tuple(steps),
            active_step_index=payload["active_step_index"],
            requires_clarification=payload["requires_clarification"],
            clarification_question=payload["clarification_question"],
            schema_version=version,
            relation_claims=relation_claims,
        )

    @classmethod
    def from_json(
        cls,
        payload: str | None,
        *,
        source_text: str,
        evidence_text: str | None = None,
    ) -> PlayerIntentAnalysis | None:
        if payload is None:
            return None
        if not isinstance(payload, str):
            raise TypeError("intent JSON must be text or None")
        return cls.from_payload(
            json.loads(payload),
            source_text=source_text,
            evidence_text=evidence_text,
        )

    @classmethod
    def unrecognized(cls) -> PlayerIntentAnalysis:
        """Fail closed when a provider does not return the required v1 contract."""
        return cls(
            category=UtteranceCategory.UNKNOWN,
            steps=(),
            active_step_index=None,
            requires_clarification=True,
            clarification_question=(
                "No he podido identificar con seguridad la acción. "
                "¿Puedes reformular qué intentas hacer ahora?"
            ),
            schema_version=2,
            relation_claims=(),
        )

    @classmethod
    def conservative_legacy(cls, source_text: str) -> PlayerIntentAnalysis:
        """Fail-safe compatibility for legacy providers without the v1 envelope."""
        text = source_text.strip()
        folded = unicodedata.normalize("NFKC", text).casefold()
        question = "?" in text or text.startswith("¿") or bool(re.match(r"^(qué|quién|como|cómo|cuando|cuándo|donde|dónde|por qué)\b", folded))
        indirect_question = bool(
            re.search(
                r"\b(pregunt\w*|averigu\w*|comprobar\w*|confirmar\w*|saber)\b.{0,120}\bsi\b",
                folded,
            )
        )
        conditional = bool(
            re.search(r"\b(si|cuando|en caso de que|if|when|suppose)\b", folded)
        ) and not indirect_question
        planned = bool(re.search(r"\b(mañana|luego|después|planeo|pienso|me gustaría|voy a|haré|tomorrow|later|plan to|i will)\b", folded))
        quoted = any(mark in text for mark in ('"', "“", "”", "«", "»"))
        # An initial first-person speech verb makes "si" an indirect-question
        # complement ("le pregunto si sabe"), not a conditional clause.
        player_speech_act = bool(re.match(
            r"^(?:le\s+)?(?:pregunto|pregunt[eé]|consulto|consult[eé]|hablo|habl[eé]|digo|dije|cuento|cont[eé]|pido|ped[ií]|respondo|respond[ií])\b",
            folded,
        ))
        failure = bool(re.search(r"\b(no pude|no consigo|no logré|no logre|no conseguí|no consegui|fallé|falle|fracasé|fracase|falló|fallo|failed|could not|couldn't)\b", folded))
        negated = bool(re.search(r"\b(no|nunca|jamás|jamas|not|never)\b", folded)) and not failure
        if question:
            category, modality = UtteranceCategory.QUESTION, IntentModality.QUESTION
        elif quoted or player_speech_act:
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
                index=0,
                source_excerpt=text[:300],
                actor=IntentActor.OTHER if quoted else IntentActor.PLAYER,
                action=text[:500], modality=modality, polarity=polarity,
                reported_outcome=PlayerReportedOutcome.FAILURE if failure else PlayerReportedOutcome.NOT_CLAIMED,
            ),),
            active_step_index=active,
            schema_version=1,
        )


def _text(value: typing.Any, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{field} must not exceed {limit} characters")
    return value


def _enum(enum_type, value: typing.Any):
    if not isinstance(value, str):
        raise TypeError("enum fields must be strings")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"unsupported {enum_type.__name__}: {value}") from exc


def _evidence(source: str, fragment: str) -> bool:
    normalize = lambda value: unicodedata.normalize("NFKC", value).casefold()
    return normalize(fragment) in normalize(source)
