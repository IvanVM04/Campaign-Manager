"""Versioned, evidence-bound v3 interpretation contracts (not a runtime route).

The model-facing payload represents communicative acts, events/propositions,
discourse links and world-fact candidates. GameplayActionCandidate is a
separate backend-only derived record and is deliberately absent from the
untrusted payload decoder.
"""
from __future__ import annotations

import dataclasses
import enum
import json
import re
import unicodedata
from typing import Any

from models.semantic_frames import (
    SemanticActionFamily,
    SemanticArgument,
    SemanticMention,
    SemanticPolarity,
    SemanticRelationFamily,
)

SCHEMA_VERSION = 3
MAX_SOURCE_CHARS = 20_000
MAX_LOCAL_ID_CHARS = 32
MAX_UTTERANCE_ACTS = 8
MAX_EVENT_FRAMES = 12
MAX_DISCOURSE_LINKS = 16
MAX_WORLD_FACT_CANDIDATES = 12
MAX_CLARIFICATION_CANDIDATES = 8
MAX_EVIDENCE_SPANS_PER_RECORD = 4
MAX_QUOTE_SPANS_PER_ACT = 4
MAX_EVENT_ARGUMENTS = 12
MAX_FACT_TEXT_CHARS = 160
_LOCAL_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_REFERENCE_RE = re.compile(r"^(act|event|fact):([a-z][a-z0-9_]{0,31})$")
_NORMALIZED_RELATION_RE = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){0,3}$"
)


class TurnInterpretationV3ValidationError(ValueError):
    """Safe decoder failure; exposes only a fixed code and field path."""

    def __init__(self, code: str, field_path: str) -> None:
        self.code = code
        self.field_path = field_path
        super().__init__(f"Invalid v3 interpretation ({code}) at {field_path}")


class UtteranceForce(str, enum.Enum):
    ASSERTION = "assertion"
    QUESTION = "question"
    IN_CHARACTER_DIALOGUE = "in_character_dialogue"
    WARNING = "warning"
    REQUEST = "request"
    REFUSAL = "refusal"
    CORRECTION = "correction"
    HYPOTHESIS = "hypothesis"
    REPORT = "report"
    OTHER = "other"
    UNKNOWN = "unknown"


class SpeakerRole(str, enum.Enum):
    PLAYER = "player"
    NPC = "npc"
    OTHER = "other"
    UNKNOWN = "unknown"


class EpistemicStatus(str, enum.Enum):
    ASSERTED = "asserted"
    OBSERVED = "observed"
    REPORTED = "reported"
    RUMOR = "rumor"
    HYPOTHETICAL = "hypothetical"
    UNCERTAIN = "uncertain"
    NOT_ESTABLISHED = "not_established"


class ActionPhase(str, enum.Enum):
    PLANNED = "planned"
    ATTEMPTED = "attempted"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    STATE = "state"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class DiscourseLinkType(str, enum.Enum):
    BEFORE_AFTER = "before_after"
    CONTINUATION = "continuation"
    CONDITION_ON_SUCCESS = "condition_on_success"
    RESPONSE_TO = "response_to"
    CORRECTION_OF = "correction_of"
    ELABORATION = "elaboration"
    CONTRAST = "contrast"
    REPORTS = "reports"
    QUOTES = "quotes"
    CALLBACK = "callback"


class WorldFactKind(str, enum.Enum):
    RELATION = "relation"
    ENTITY_ATTRIBUTE = "entity_attribute"
    OTHER = "other"


class RelationDirection(str, enum.Enum):
    SUBJECT_TO_OBJECT = "subject_to_object"
    OBJECT_TO_SUBJECT = "object_to_subject"
    SYMMETRIC = "symmetric"


class FactTemporalScope(str, enum.Enum):
    PERMANENT = "permanent"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class ClarificationKind(str, enum.Enum):
    REFERENT = "referent"
    ROLE = "role"
    EVENT = "event"
    RELATION = "relation"
    SEQUENCE = "sequence"
    TEMPORAL = "temporal"
    OTHER = "other"


class GameplayActionEligibility(str, enum.Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    REQUIRES_CLARIFICATION = "requires_clarification"
    BLOCKED_BY_DEPENDENCY = "blocked_by_dependency"


class GameplayActionReason(str, enum.Enum):
    ELIGIBLE = "eligible"
    NON_PLAYER_ACTOR = "non_player_actor"
    NOT_AN_ATTEMPT = "not_an_attempt"
    NEGATED = "negated"
    CONDITIONAL = "conditional"
    DEPENDENCY_PENDING = "dependency_pending"
    UNSUPPORTED_ACTION = "unsupported_action"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"
    UNRESOLVED_REFERENCE = "unresolved_reference"
    CLARIFICATION_REQUIRED = "clarification_required"
    ALREADY_PROCESSED = "already_processed"
    OUTSIDE_PLAYER_SCOPE = "outside_player_scope"


class GameplayWorkflow(str, enum.Enum):
    NONE = "none"
    DIALOGUE = "dialogue"
    MECHANICS = "mechanics"
    CLARIFICATION = "clarification"


class GameplayUnlockCondition(str, enum.Enum):
    NONE = "none"
    DEPENDENCY_SUCCESS = "dependency_success"
    DEPENDENCY_RESOLVED = "dependency_resolved"
    CLARIFICATION_RESOLVED = "clarification_resolved"


class GameplayProcessingState(str, enum.Enum):
    PENDING = "pending"
    ADJUDICATING = "adjudicating"
    AWAITING_INPUT = "awaiting_input"
    RESOLVED = "resolved"
    FAILED = "failed"
    BLOCKED = "blocked"


class GameplayResolvedReferenceKind(str, enum.Enum):
    ENTITY = "entity"
    ITEM_DEFINITION = "item_definition"
    ITEM_INSTANCE = "item_instance"
    RESOURCE = "resource"
    EVENT = "event"


def _text(value: Any, name: str, maximum: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if len(value) > maximum or (not allow_empty and not value.strip()):
        raise ValueError(f"{name} is outside its text bounds")
    return value


def _local_id(value: Any, name: str = "local_id") -> str:
    text = _text(value, name, MAX_LOCAL_ID_CHARS)
    if _LOCAL_ID_RE.fullmatch(text) is None:
        raise ValueError(f"{name} must be a bounded local identifier")
    return text


def _prefixed_id(value: Any, prefix: str, name: str = "local_id") -> str:
    text = _local_id(value, name)
    if not text.startswith(prefix):
        raise ValueError(f"{name} must use the {prefix} local namespace")
    return text


def _enum(enum_type: type[enum.Enum], value: Any, name: str) -> Any:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be an enum string")
    try:
        return enum_type(value)
    except ValueError:
        raise ValueError(f"{name} contains an unsupported value") from None


def _keys(payload: Any, expected: set[str], name: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ValueError(f"{name} has missing or unexpected fields")
    return payload


def _sequence(
    value: Any,
    name: str,
    maximum: int,
    *,
    minimum: int = 0,
) -> tuple[Any, ...]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{name} must be a bounded array")
    return tuple(value)


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _require_in_spans(spans: tuple[EvidenceSpan, ...], value: str, name: str) -> None:
    normalized = _fold(value)
    if not any(normalized in _fold(span.text) for span in spans):
        raise ValueError(f"{name} is not grounded in its evidence spans")


@dataclasses.dataclass(frozen=True, slots=True)
class EvidenceSpan:
    """Exact half-open Unicode-code-point span in the current player utterance.

    Offsets are Python string indices, not UTF-8 byte offsets. The model may
    not reference transcript history, narration or a canonical turn ID here.
    """

    start: int
    end: int
    text: str
    source: str = "current_utterance"

    def __post_init__(self) -> None:
        for name, value in (("start", self.start), ("end", self.end)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("evidence span must be a non-empty half-open range")
        _text(self.text, "evidence span text", 500)
        if self.source != "current_utterance":
            raise ValueError("evidence span source must be current_utterance")

    def validate_source(self, source_text: str) -> None:
        if self.end > len(source_text) or source_text[self.start:self.end] != self.text:
            raise ValueError("evidence span offsets do not match the current utterance")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "source": self.source,
        }

    @classmethod
    def from_payload(cls, payload: Any, *, source_text: str) -> EvidenceSpan:
        raw = _keys(payload, {"start", "end", "text", "source"}, "evidence_span")
        span = cls(
            start=raw["start"],
            end=raw["end"],
            text=_text(raw["text"], "evidence span text", 500),
            source=raw["source"],
        )
        span.validate_source(source_text)
        return span


def _parse_spans(payload: Any, *, source_text: str, name: str, minimum: int = 1) -> tuple[EvidenceSpan, ...]:
    raw = _sequence(
        payload,
        name,
        MAX_EVIDENCE_SPANS_PER_RECORD,
        minimum=minimum,
    )
    return tuple(EvidenceSpan.from_payload(item, source_text=source_text) for item in raw)


def _parse_mention(
    payload: Any,
    *,
    spans: tuple[EvidenceSpan, ...],
    name: str,
) -> SemanticMention:
    mention = SemanticMention.from_payload(
        payload,
        evidence_text="\n".join(span.text for span in spans),
        field_name=name,
    )
    _require_in_spans(spans, mention.text, name)
    return mention


@dataclasses.dataclass(frozen=True, slots=True)
class UtteranceAct:
    """Communicative act, separate from the event/proposition it contains."""

    local_id: str
    force: UtteranceForce
    speaker_role: SpeakerRole
    evidence_spans: tuple[EvidenceSpan, ...]
    speaker_mention: SemanticMention | None = None
    addressee_mention: SemanticMention | None = None
    quote_spans: tuple[EvidenceSpan, ...] = ()

    def __post_init__(self) -> None:
        _prefixed_id(self.local_id, "act_")
        if not isinstance(self.force, UtteranceForce):
            raise TypeError("force must be an UtteranceForce")
        if not isinstance(self.speaker_role, SpeakerRole):
            raise TypeError("speaker_role must be a SpeakerRole")
        if not isinstance(self.evidence_spans, tuple) or not 1 <= len(self.evidence_spans) <= MAX_EVIDENCE_SPANS_PER_RECORD:
            raise ValueError("utterance act requires bounded evidence spans")
        if any(not isinstance(item, EvidenceSpan) for item in self.evidence_spans):
            raise TypeError("evidence_spans must contain EvidenceSpan values")
        for name, mention in (("speaker_mention", self.speaker_mention), ("addressee_mention", self.addressee_mention)):
            if mention is not None and not isinstance(mention, SemanticMention):
                raise TypeError(f"{name} must be a SemanticMention or None")
            if mention is not None:
                _require_in_spans(self.evidence_spans, mention.text, name)
        if not isinstance(self.quote_spans, tuple) or len(self.quote_spans) > MAX_QUOTE_SPANS_PER_ACT:
            raise ValueError("quote_spans must be a bounded tuple")
        for quote in self.quote_spans:
            if not isinstance(quote, EvidenceSpan):
                raise TypeError("quote_spans must contain EvidenceSpan values")
            if not any(
                evidence.start <= quote.start and quote.end <= evidence.end
                for evidence in self.evidence_spans
            ):
                raise ValueError("quote span must be contained in act evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_id": self.local_id,
            "force": self.force.value,
            "speaker_role": self.speaker_role.value,
            "speaker_mention": None if self.speaker_mention is None else self.speaker_mention.to_dict(),
            "addressee_mention": None if self.addressee_mention is None else self.addressee_mention.to_dict(),
            "quote_spans": [item.to_dict() for item in self.quote_spans],
            "evidence_spans": [item.to_dict() for item in self.evidence_spans],
        }

    @classmethod
    def from_payload(cls, payload: Any, *, source_text: str) -> UtteranceAct:
        raw = _keys(
            payload,
            {
                "local_id", "force", "speaker_role", "speaker_mention",
                "addressee_mention", "quote_spans", "evidence_spans",
            },
            "utterance_act",
        )
        evidence = _parse_spans(raw["evidence_spans"], source_text=source_text, name="act evidence")
        quotes = _parse_spans(
            raw["quote_spans"],
            source_text=source_text,
            name="quote spans",
            minimum=0,
        )
        speaker = None if raw["speaker_mention"] is None else _parse_mention(
            raw["speaker_mention"], spans=evidence, name="speaker mention"
        )
        addressee = None if raw["addressee_mention"] is None else _parse_mention(
            raw["addressee_mention"], spans=evidence, name="addressee mention"
        )
        return cls(
            local_id=_local_id(raw["local_id"]),
            force=_enum(UtteranceForce, raw["force"], "force"),
            speaker_role=_enum(SpeakerRole, raw["speaker_role"], "speaker_role"),
            speaker_mention=speaker,
            addressee_mention=addressee,
            quote_spans=quotes,
            evidence_spans=evidence,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class EventFrame:
    """Event or proposition, with roles and status orthogonal to speech acts."""

    local_id: str
    source_act_id: str
    predicate_surface: str
    family: SemanticActionFamily
    arguments: tuple[SemanticArgument, ...]
    polarity: SemanticPolarity
    epistemic_status: EpistemicStatus
    action_phase: ActionPhase
    evidence_spans: tuple[EvidenceSpan, ...]
    attributed_source: SemanticMention | None = None
    temporal_expression: str | None = None

    def __post_init__(self) -> None:
        _prefixed_id(self.local_id, "event_")
        _prefixed_id(self.source_act_id, "act_", "source_act_id")
        _text(self.predicate_surface, "predicate_surface", 120)
        if not isinstance(self.family, SemanticActionFamily):
            raise TypeError("family must be a SemanticActionFamily")
        if not isinstance(self.arguments, tuple) or len(self.arguments) > MAX_EVENT_ARGUMENTS:
            raise ValueError("event arguments must be a bounded tuple")
        if any(not isinstance(item, SemanticArgument) for item in self.arguments):
            raise TypeError("arguments must contain SemanticArgument values")
        if len({
            (item.role, item.mention.text.casefold()) for item in self.arguments
        }) != len(self.arguments):
            raise ValueError("event arguments must not repeat role/mention pairs")
        if not isinstance(self.polarity, SemanticPolarity):
            raise TypeError("polarity must be a SemanticPolarity")
        if not isinstance(self.epistemic_status, EpistemicStatus):
            raise TypeError("epistemic_status must be an EpistemicStatus")
        if not isinstance(self.action_phase, ActionPhase):
            raise TypeError("action_phase must be an ActionPhase")
        if not isinstance(self.evidence_spans, tuple) or not 1 <= len(self.evidence_spans) <= MAX_EVIDENCE_SPANS_PER_RECORD:
            raise ValueError("event frame requires bounded evidence spans")
        if any(not isinstance(item, EvidenceSpan) for item in self.evidence_spans):
            raise TypeError("evidence_spans must contain EvidenceSpan values")
        _require_in_spans(self.evidence_spans, self.predicate_surface, "predicate_surface")
        for argument in self.arguments:
            _require_in_spans(self.evidence_spans, argument.mention.text, "argument mention")
        if self.attributed_source is not None:
            if not isinstance(self.attributed_source, SemanticMention):
                raise TypeError("attributed_source must be a SemanticMention or None")
            _require_in_spans(self.evidence_spans, self.attributed_source.text, "attributed_source")
        if self.temporal_expression is not None:
            _text(self.temporal_expression, "temporal_expression", 120)
            _require_in_spans(self.evidence_spans, self.temporal_expression, "temporal_expression")

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_id": self.local_id,
            "source_act_id": self.source_act_id,
            "predicate_surface": self.predicate_surface,
            "family": self.family.value,
            "arguments": [item.to_dict() for item in self.arguments],
            "polarity": self.polarity.value,
            "epistemic_status": self.epistemic_status.value,
            "action_phase": self.action_phase.value,
            "temporal_expression": self.temporal_expression,
            "attributed_source": None if self.attributed_source is None else self.attributed_source.to_dict(),
            "evidence_spans": [item.to_dict() for item in self.evidence_spans],
        }

    @classmethod
    def from_payload(cls, payload: Any, *, source_text: str) -> EventFrame:
        raw = _keys(
            payload,
            {
                "local_id", "source_act_id", "predicate_surface", "family",
                "arguments", "polarity", "epistemic_status", "action_phase",
                "temporal_expression", "attributed_source", "evidence_spans",
            },
            "event_frame",
        )
        evidence = _parse_spans(raw["evidence_spans"], source_text=source_text, name="event evidence")
        arguments_raw = _sequence(raw["arguments"], "event arguments", MAX_EVENT_ARGUMENTS)
        arguments = tuple(
            SemanticArgument.from_payload(
                item,
                evidence_text="\n".join(span.text for span in evidence),
            )
            for item in arguments_raw
        )
        attributed = None if raw["attributed_source"] is None else _parse_mention(
            raw["attributed_source"], spans=evidence, name="attributed source"
        )
        return cls(
            local_id=_local_id(raw["local_id"]),
            source_act_id=_local_id(raw["source_act_id"], "source_act_id"),
            predicate_surface=_text(raw["predicate_surface"], "predicate_surface", 120),
            family=_enum(SemanticActionFamily, raw["family"], "family"),
            arguments=arguments,
            polarity=_enum(SemanticPolarity, raw["polarity"], "polarity"),
            epistemic_status=_enum(EpistemicStatus, raw["epistemic_status"], "epistemic_status"),
            action_phase=_enum(ActionPhase, raw["action_phase"], "action_phase"),
            temporal_expression=None if raw["temporal_expression"] is None else _text(raw["temporal_expression"], "temporal_expression", 120),
            attributed_source=attributed,
            evidence_spans=evidence,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class DiscourseLink:
    """Directed relation between local acts/events/facts or a callback anchor."""

    local_id: str
    source_ref: str
    target_ref: str | None
    link_type: DiscourseLinkType
    evidence_spans: tuple[EvidenceSpan, ...]
    anchor_candidate: str | None = None

    def __post_init__(self) -> None:
        _prefixed_id(self.local_id, "link_")
        if not isinstance(self.source_ref, str) or _REFERENCE_RE.fullmatch(self.source_ref) is None:
            raise ValueError("source_ref must identify a local act/event/fact")
        if self.target_ref is not None and (
            not isinstance(self.target_ref, str)
            or _REFERENCE_RE.fullmatch(self.target_ref) is None
        ):
            raise ValueError("target_ref must identify a local act/event/fact")
        if not isinstance(self.link_type, DiscourseLinkType):
            raise TypeError("link_type must be a DiscourseLinkType")
        if not isinstance(self.evidence_spans, tuple) or not 1 <= len(self.evidence_spans) <= MAX_EVIDENCE_SPANS_PER_RECORD:
            raise ValueError("discourse link requires bounded evidence spans")
        if any(not isinstance(item, EvidenceSpan) for item in self.evidence_spans):
            raise TypeError("evidence_spans must contain EvidenceSpan values")
        if self.link_type is DiscourseLinkType.CALLBACK:
            if self.target_ref is not None:
                raise ValueError("callback cannot invent a historical local target")
            anchor_candidate = _text(self.anchor_candidate, "anchor_candidate", 160)
            _require_in_spans(self.evidence_spans, anchor_candidate, "anchor_candidate")
        else:
            if self.target_ref is None:
                raise ValueError("non-callback discourse links require a local target_ref")
            if self.anchor_candidate is not None:
                raise ValueError("anchor_candidate is reserved for callbacks")
        if self.target_ref == self.source_ref:
            raise ValueError("discourse link cannot point to itself")

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_id": self.local_id,
            "source_ref": self.source_ref,
            "target_ref": self.target_ref,
            "link_type": self.link_type.value,
            "anchor_candidate": self.anchor_candidate,
            "evidence_spans": [item.to_dict() for item in self.evidence_spans],
        }

    @classmethod
    def from_payload(cls, payload: Any, *, source_text: str) -> DiscourseLink:
        raw = _keys(
            payload,
            {"local_id", "source_ref", "target_ref", "link_type", "anchor_candidate", "evidence_spans"},
            "discourse_link",
        )
        return cls(
            local_id=_local_id(raw["local_id"]),
            source_ref=raw["source_ref"],
            target_ref=raw["target_ref"],
            link_type=_enum(DiscourseLinkType, raw["link_type"], "link_type"),
            anchor_candidate=None if raw["anchor_candidate"] is None else _text(raw["anchor_candidate"], "anchor_candidate", 160),
            evidence_spans=_parse_spans(
                raw["evidence_spans"],
                source_text=source_text,
                name="discourse link evidence",
            ),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class WorldFactCandidate:
    """Untrusted fact proposal; never carries persistence authorization."""

    local_id: str
    source_act_id: str
    fact_kind: WorldFactKind
    subject: SemanticMention
    predicate_surface: str
    polarity: SemanticPolarity
    epistemic_status: EpistemicStatus
    temporal_scope: FactTemporalScope
    evidence_spans: tuple[EvidenceSpan, ...]
    object: SemanticMention | None = None
    value_surface: str | None = None
    relation_family: SemanticRelationFamily | None = None
    normalized_relation_type: str | None = None
    direction: RelationDirection | None = None
    attributed_source: SemanticMention | None = None

    def __post_init__(self) -> None:
        _prefixed_id(self.local_id, "fact_")
        _prefixed_id(self.source_act_id, "act_", "source_act_id")
        if not isinstance(self.fact_kind, WorldFactKind):
            raise TypeError("fact_kind must be a WorldFactKind")
        if not isinstance(self.subject, SemanticMention):
            raise TypeError("subject must be a SemanticMention")
        _text(self.predicate_surface, "predicate_surface", 120)
        if not isinstance(self.polarity, SemanticPolarity):
            raise TypeError("polarity must be a SemanticPolarity")
        if not isinstance(self.epistemic_status, EpistemicStatus):
            raise TypeError("epistemic_status must be an EpistemicStatus")
        if not isinstance(self.temporal_scope, FactTemporalScope):
            raise TypeError("temporal_scope must be a FactTemporalScope")
        if not isinstance(self.evidence_spans, tuple) or not 1 <= len(self.evidence_spans) <= MAX_EVIDENCE_SPANS_PER_RECORD:
            raise ValueError("world fact requires bounded evidence spans")
        if any(not isinstance(item, EvidenceSpan) for item in self.evidence_spans):
            raise TypeError("evidence_spans must contain EvidenceSpan values")
        if self.object is not None and not isinstance(self.object, SemanticMention):
            raise TypeError("object must be a SemanticMention or None")
        if self.value_surface is not None:
            _text(self.value_surface, "value_surface", MAX_FACT_TEXT_CHARS)
        if self.relation_family is not None and not isinstance(self.relation_family, SemanticRelationFamily):
            raise TypeError("relation_family must be a SemanticRelationFamily or None")
        if self.direction is not None and not isinstance(self.direction, RelationDirection):
            raise TypeError("direction must be a RelationDirection or None")
        if self.normalized_relation_type is not None:
            normalized = _text(self.normalized_relation_type, "normalized_relation_type", 80)
            if _NORMALIZED_RELATION_RE.fullmatch(normalized) is None:
                raise ValueError("normalized_relation_type must use a bounded namespaced key")
        if self.attributed_source is not None and not isinstance(self.attributed_source, SemanticMention):
            raise TypeError("attributed_source must be a SemanticMention or None")

        if self.fact_kind is WorldFactKind.RELATION:
            if self.object is None or self.relation_family is None or self.direction is None:
                raise ValueError("relation facts require object, relation_family and direction")
            if self.value_surface is not None:
                raise ValueError("relation facts cannot carry value_surface")
        elif self.fact_kind is WorldFactKind.ENTITY_ATTRIBUTE:
            if self.object is not None or self.value_surface is None:
                raise ValueError("entity-attribute facts require value_surface and no object")
            if self.relation_family is not None or self.direction is not None or self.normalized_relation_type is not None:
                raise ValueError("entity-attribute facts cannot carry relation fields")
        elif self.object is None and self.value_surface is None:
            raise ValueError("other fact candidates require an object or value")

        for name, mention in (
            ("subject", self.subject),
            ("object", self.object),
            ("attributed_source", self.attributed_source),
        ):
            if mention is not None:
                _require_in_spans(self.evidence_spans, mention.text, name)
        _require_in_spans(self.evidence_spans, self.predicate_surface, "predicate_surface")
        if self.value_surface is not None:
            _require_in_spans(self.evidence_spans, self.value_surface, "value_surface")

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_id": self.local_id,
            "source_act_id": self.source_act_id,
            "fact_kind": self.fact_kind.value,
            "subject": self.subject.to_dict(),
            "predicate_surface": self.predicate_surface,
            "object": None if self.object is None else self.object.to_dict(),
            "value_surface": self.value_surface,
            "relation_family": None if self.relation_family is None else self.relation_family.value,
            "normalized_relation_type": self.normalized_relation_type,
            "direction": None if self.direction is None else self.direction.value,
            "polarity": self.polarity.value,
            "epistemic_status": self.epistemic_status.value,
            "temporal_scope": self.temporal_scope.value,
            "attributed_source": None if self.attributed_source is None else self.attributed_source.to_dict(),
            "evidence_spans": [item.to_dict() for item in self.evidence_spans],
        }

    @classmethod
    def from_payload(cls, payload: Any, *, source_text: str) -> WorldFactCandidate:
        raw = _keys(
            payload,
            {
                "local_id", "source_act_id", "fact_kind", "subject", "predicate_surface",
                "object", "value_surface", "relation_family", "normalized_relation_type",
                "direction", "polarity", "epistemic_status", "temporal_scope",
                "attributed_source", "evidence_spans",
            },
            "world_fact_candidate",
        )
        evidence = _parse_spans(raw["evidence_spans"], source_text=source_text, name="fact evidence")
        subject = _parse_mention(raw["subject"], spans=evidence, name="fact subject")
        object_mention = None if raw["object"] is None else _parse_mention(
            raw["object"], spans=evidence, name="fact object"
        )
        attributed = None if raw["attributed_source"] is None else _parse_mention(
            raw["attributed_source"], spans=evidence, name="fact attributed source"
        )
        return cls(
            local_id=_local_id(raw["local_id"]),
            source_act_id=_local_id(raw["source_act_id"], "source_act_id"),
            fact_kind=_enum(WorldFactKind, raw["fact_kind"], "fact_kind"),
            subject=subject,
            predicate_surface=_text(raw["predicate_surface"], "predicate_surface", 120),
            object=object_mention,
            value_surface=None if raw["value_surface"] is None else _text(raw["value_surface"], "value_surface", MAX_FACT_TEXT_CHARS),
            relation_family=None if raw["relation_family"] is None else _enum(SemanticRelationFamily, raw["relation_family"], "relation_family"),
            normalized_relation_type=raw["normalized_relation_type"],
            direction=None if raw["direction"] is None else _enum(RelationDirection, raw["direction"], "direction"),
            polarity=_enum(SemanticPolarity, raw["polarity"], "polarity"),
            epistemic_status=_enum(EpistemicStatus, raw["epistemic_status"], "epistemic_status"),
            temporal_scope=_enum(FactTemporalScope, raw["temporal_scope"], "temporal_scope"),
            attributed_source=attributed,
            evidence_spans=evidence,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ClarificationCandidate:
    """Semantic description of an ambiguity, not a durable checkpoint."""

    local_id: str
    affected_local_ids: tuple[str, ...]
    ambiguity_kind: ClarificationKind
    missing_slot: str
    question_intent: str
    evidence_spans: tuple[EvidenceSpan, ...]

    def __post_init__(self) -> None:
        _prefixed_id(self.local_id, "clarify_")
        if not isinstance(self.affected_local_ids, tuple) or not 1 <= len(self.affected_local_ids) <= 8:
            raise ValueError("affected_local_ids must contain 1-8 local identifiers")
        for identifier in self.affected_local_ids:
            _local_id(identifier, "affected_local_id")
        if len(set(self.affected_local_ids)) != len(self.affected_local_ids):
            raise ValueError("affected_local_ids must be unique")
        if not isinstance(self.ambiguity_kind, ClarificationKind):
            raise TypeError("ambiguity_kind must be a ClarificationKind")
        _text(self.missing_slot, "missing_slot", 64)
        _text(self.question_intent, "question_intent", 200)
        if not isinstance(self.evidence_spans, tuple) or not 1 <= len(self.evidence_spans) <= MAX_EVIDENCE_SPANS_PER_RECORD:
            raise ValueError("clarification candidate requires bounded evidence spans")
        if any(not isinstance(item, EvidenceSpan) for item in self.evidence_spans):
            raise TypeError("evidence_spans must contain EvidenceSpan values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_id": self.local_id,
            "affected_local_ids": list(self.affected_local_ids),
            "ambiguity_kind": self.ambiguity_kind.value,
            "missing_slot": self.missing_slot,
            "question_intent": self.question_intent,
            "evidence_spans": [item.to_dict() for item in self.evidence_spans],
        }

    @classmethod
    def from_payload(cls, payload: Any, *, source_text: str) -> ClarificationCandidate:
        raw = _keys(
            payload,
            {
                "local_id", "affected_local_ids", "ambiguity_kind",
                "missing_slot", "question_intent", "evidence_spans",
            },
            "clarification_candidate",
        )
        return cls(
            local_id=_local_id(raw["local_id"]),
            affected_local_ids=tuple(
                _local_id(item, "affected_local_id")
                for item in _sequence(raw["affected_local_ids"], "affected_local_ids", 8, minimum=1)
            ),
            ambiguity_kind=_enum(ClarificationKind, raw["ambiguity_kind"], "ambiguity_kind"),
            missing_slot=_text(raw["missing_slot"], "missing_slot", 64),
            question_intent=_text(raw["question_intent"], "question_intent", 200),
            evidence_spans=_parse_spans(
                raw["evidence_spans"],
                source_text=source_text,
                name="clarification evidence",
            ),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class TurnInterpretationV3:
    """One holistic untrusted interpretation. It never selects an active action."""

    utterance_acts: tuple[UtteranceAct, ...]
    events: tuple[EventFrame, ...]
    discourse_links: tuple[DiscourseLink, ...]
    world_facts: tuple[WorldFactCandidate, ...]
    clarification_candidates: tuple[ClarificationCandidate, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("TurnInterpretationV3 requires schema_version 3")
        for name, values, maximum, expected_type in (
            ("utterance_acts", self.utterance_acts, MAX_UTTERANCE_ACTS, UtteranceAct),
            ("events", self.events, MAX_EVENT_FRAMES, EventFrame),
            ("discourse_links", self.discourse_links, MAX_DISCOURSE_LINKS, DiscourseLink),
            ("world_facts", self.world_facts, MAX_WORLD_FACT_CANDIDATES, WorldFactCandidate),
            ("clarification_candidates", self.clarification_candidates, MAX_CLARIFICATION_CANDIDATES, ClarificationCandidate),
        ):
            if not isinstance(values, tuple) or len(values) > maximum:
                raise ValueError(f"{name} must be a bounded tuple")
            if any(not isinstance(item, expected_type) for item in values):
                raise TypeError(f"{name} contains an invalid record type")

        act_ids = {item.local_id for item in self.utterance_acts}
        event_ids = {item.local_id for item in self.events}
        fact_ids = {item.local_id for item in self.world_facts}
        link_ids = {item.local_id for item in self.discourse_links}
        clarification_ids = {item.local_id for item in self.clarification_candidates}
        all_ids = act_ids | event_ids | fact_ids | link_ids | clarification_ids
        declared_id_count = (
            len(self.utterance_acts) + len(self.events) + len(self.discourse_links)
            + len(self.world_facts) + len(self.clarification_candidates)
        )
        if len(all_ids) != declared_id_count:
            raise ValueError("local identifiers must be unique across the turn")
        if any(item.source_act_id not in act_ids for item in self.events):
            raise ValueError("event source_act_id must reference an utterance act")
        if any(item.source_act_id not in act_ids for item in self.world_facts):
            raise ValueError("fact source_act_id must reference an utterance act")

        allowed_refs = {
            *(f"act:{identifier}" for identifier in act_ids),
            *(f"event:{identifier}" for identifier in event_ids),
            *(f"fact:{identifier}" for identifier in fact_ids),
        }
        for link in self.discourse_links:
            if link.source_ref not in allowed_refs:
                raise ValueError("discourse source_ref does not resolve locally")
            if link.target_ref is not None and link.target_ref not in allowed_refs:
                raise ValueError("discourse target_ref does not resolve locally")
        if any(
            identifier not in all_ids - clarification_ids
            for item in self.clarification_candidates
            for identifier in item.affected_local_ids
        ):
            raise ValueError("clarification candidate references an unknown local record")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "utterance_acts": [item.to_dict() for item in self.utterance_acts],
            "events": [item.to_dict() for item in self.events],
            "discourse_links": [item.to_dict() for item in self.discourse_links],
            "world_facts": [item.to_dict() for item in self.world_facts],
            "clarification_candidates": [item.to_dict() for item in self.clarification_candidates],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_payload(cls, payload: Any, *, source_text: str) -> TurnInterpretationV3:
        """Decode strict model output and bind every span to current player text."""
        if not isinstance(source_text, str) or not source_text.strip() or len(source_text) > MAX_SOURCE_CHARS:
            raise TurnInterpretationV3ValidationError("invalid_source_text", "source_text")
        try:
            raw = _keys(
                payload,
                {
                    "schema_version", "utterance_acts", "events",
                    "discourse_links", "world_facts", "clarification_candidates",
                },
                "turn_interpretation_v3",
            )
            acts = tuple(
                UtteranceAct.from_payload(item, source_text=source_text)
                for item in _sequence(raw["utterance_acts"], "utterance_acts", MAX_UTTERANCE_ACTS)
            )
            events = tuple(
                EventFrame.from_payload(item, source_text=source_text)
                for item in _sequence(raw["events"], "events", MAX_EVENT_FRAMES)
            )
            links = tuple(
                DiscourseLink.from_payload(item, source_text=source_text)
                for item in _sequence(raw["discourse_links"], "discourse_links", MAX_DISCOURSE_LINKS)
            )
            facts = tuple(
                WorldFactCandidate.from_payload(item, source_text=source_text)
                for item in _sequence(raw["world_facts"], "world_facts", MAX_WORLD_FACT_CANDIDATES)
            )
            clarifications = tuple(
                ClarificationCandidate.from_payload(item, source_text=source_text)
                for item in _sequence(raw["clarification_candidates"], "clarification_candidates", MAX_CLARIFICATION_CANDIDATES)
            )
            return cls(
                schema_version=raw["schema_version"],
                utterance_acts=acts,
                events=events,
                discourse_links=links,
                world_facts=facts,
                clarification_candidates=clarifications,
            )
        except TurnInterpretationV3ValidationError:
            raise
        except (TypeError, ValueError, KeyError):
            raise TurnInterpretationV3ValidationError("invalid_payload", "payload") from None

    @classmethod
    def from_json(cls, payload: str, *, source_text: str) -> TurnInterpretationV3:
        if not isinstance(payload, str):
            raise TurnInterpretationV3ValidationError("invalid_json_input", "payload")
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError):
            raise TurnInterpretationV3ValidationError("invalid_json", "payload") from None
        return cls.from_payload(decoded, source_text=source_text)


@dataclasses.dataclass(frozen=True, slots=True)
class GameplayResolvedReference:
    """Canonical reference attached by trusted backend code, never by the LLM."""

    mention: SemanticMention
    category: GameplayResolvedReferenceKind
    referent_id: int | str
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.mention, SemanticMention):
            raise TypeError("mention must be a SemanticMention")
        if not isinstance(self.category, GameplayResolvedReferenceKind):
            raise TypeError("category must be a GameplayResolvedReferenceKind")
        _text(self.name, "resolved reference name", 160)
        if self.category is GameplayResolvedReferenceKind.EVENT:
            if not isinstance(self.referent_id, str) or not self.referent_id.strip():
                raise ValueError("event reference requires a non-empty string ID")
        elif isinstance(self.referent_id, bool) or not isinstance(self.referent_id, int) or self.referent_id < 1:
            raise ValueError("canonical world references require a positive integer ID")


@dataclasses.dataclass(frozen=True, slots=True)
class GameplayActionCandidate:
    """Backend-derived action focus; never accepted by the v3 payload decoder."""

    local_id: str
    source_event_id: str
    actor: SemanticMention
    action_type: str
    eligibility: GameplayActionEligibility
    reason: GameplayActionReason
    workflow: GameplayWorkflow
    unlock_condition: GameplayUnlockCondition
    processing_state: GameplayProcessingState
    target_mentions: tuple[SemanticMention, ...] = ()
    dependency_event_ids: tuple[str, ...] = ()
    resolved_references: tuple[GameplayResolvedReference, ...] = ()

    def __post_init__(self) -> None:
        _prefixed_id(self.local_id, "action_")
        _prefixed_id(self.source_event_id, "event_", "source_event_id")
        if not isinstance(self.actor, SemanticMention):
            raise TypeError("actor must be a SemanticMention")
        _text(self.action_type, "action_type", 64)
        for name, expected in (
            ("eligibility", GameplayActionEligibility),
            ("reason", GameplayActionReason),
            ("workflow", GameplayWorkflow),
            ("unlock_condition", GameplayUnlockCondition),
            ("processing_state", GameplayProcessingState),
        ):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(f"{name} has an invalid enum type")
        if not isinstance(self.target_mentions, tuple) or len(self.target_mentions) > 8:
            raise ValueError("target_mentions must be a bounded tuple")
        if any(not isinstance(item, SemanticMention) for item in self.target_mentions):
            raise TypeError("target_mentions must contain SemanticMention values")
        if not isinstance(self.dependency_event_ids, tuple) or len(self.dependency_event_ids) > MAX_EVENT_FRAMES:
            raise ValueError("dependency_event_ids must be a bounded tuple")
        for identifier in self.dependency_event_ids:
            _prefixed_id(identifier, "event_", "dependency_event_id")
        if self.source_event_id in self.dependency_event_ids or len(set(self.dependency_event_ids)) != len(self.dependency_event_ids):
            raise ValueError("action dependencies must be unique and cannot depend on themselves")
        if not isinstance(self.resolved_references, tuple) or any(
            not isinstance(item, GameplayResolvedReference) for item in self.resolved_references
        ):
            raise TypeError("resolved_references must contain GameplayResolvedReference values")
        reference_keys = tuple((item.category, item.referent_id) for item in self.resolved_references)
        if len(set(reference_keys)) != len(reference_keys):
            raise ValueError("resolved_references must be unique")
        if self.eligibility is GameplayActionEligibility.ELIGIBLE and self.reason is not GameplayActionReason.ELIGIBLE:
            raise ValueError("eligible actions require the eligible reason")
        if self.eligibility is not GameplayActionEligibility.ELIGIBLE and self.reason is GameplayActionReason.ELIGIBLE:
            raise ValueError("non-eligible actions require a non-eligible reason")
        if (
            self.eligibility is GameplayActionEligibility.BLOCKED_BY_DEPENDENCY
            and (
                not self.dependency_event_ids
                or self.unlock_condition is GameplayUnlockCondition.NONE
            )
        ):
            raise ValueError("dependency-blocked actions require dependencies and an unlock condition")
        if self.workflow is GameplayWorkflow.CLARIFICATION and self.eligibility is not GameplayActionEligibility.REQUIRES_CLARIFICATION:
            raise ValueError("clarification workflow requires clarification eligibility")

