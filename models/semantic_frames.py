"""Evidence-bound semantic frames used by the v2 player-intent contract.

These records are an untrusted interpretation of player language. They never
contain canonical IDs and never authorize domain writes.
"""
from __future__ import annotations

import dataclasses
import enum
import typing
import unicodedata

MAX_ACTION_ARGUMENTS = 12
MAX_RELATION_CLAIMS = 8


class SemanticObjectKind(str, enum.Enum):
    CHARACTER = "character"
    CREATURE = "creature"
    LOCATION = "location"
    ITEM_DEFINITION = "item_definition"
    ITEM_INSTANCE = "item_instance"
    EVENT = "event"
    FACTION = "faction"
    RESOURCE = "resource"
    WORLD_ENTITY = "world_entity"
    UNKNOWN = "unknown"


class SemanticArgumentRole(str, enum.Enum):
    AGENT = "agent"
    PATIENT = "patient"
    THEME = "theme"
    RECIPIENT = "recipient"
    SOURCE = "source"
    DESTINATION = "destination"
    INSTRUMENT = "instrument"
    LOCATION = "location"
    PATH = "path"
    BENEFICIARY = "beneficiary"
    COMPANION = "companion"
    EXPERIENCER = "experiencer"
    OWNER = "owner"
    HOLDER = "holder"
    CONTAINER = "container"
    CAUSE = "cause"
    RESULT = "result"


class SemanticActionFamily(str, enum.Enum):
    MOVEMENT = "movement"
    COMMUNICATION = "communication"
    PERCEPTION = "perception"
    INTERACTION = "interaction"
    TRANSFER = "transfer"
    ITEM_USE = "item_use"
    COMBAT = "combat"
    SOCIAL = "social"
    STATE_CHANGE = "state_change"
    CREATION = "creation"
    RESOURCE = "resource"
    OTHER = "other"
    UNKNOWN = "unknown"


class SemanticRelationFamily(str, enum.Enum):
    KINSHIP = "kinship"
    OWNERSHIP = "ownership"
    POSSESSION = "possession"
    MEMBERSHIP = "membership"
    EMPLOYMENT = "employment"
    ALLEGIANCE = "allegiance"
    FRIENDSHIP = "friendship"
    HOSTILITY = "hostility"
    SPATIAL = "spatial"
    CONTAINMENT = "containment"
    PART_OF = "part_of"
    KNOWLEDGE = "knowledge"
    OBLIGATION = "obligation"
    PROTECTION = "protection"
    SERVICE = "service"
    OTHER = "other"
    UNKNOWN = "unknown"


class SemanticPolarity(str, enum.Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNCERTAIN = "uncertain"


class SemanticModality(str, enum.Enum):
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


@dataclasses.dataclass(frozen=True, slots=True)
class SemanticMention:
    """Literal mention plus an untrusted coarse object-kind hint."""

    text: str
    kind_hint: SemanticObjectKind = SemanticObjectKind.UNKNOWN

    def __post_init__(self) -> None:
        _validate_text(self.text, "mention", 120)
        if not isinstance(self.kind_hint, SemanticObjectKind):
            raise TypeError("kind_hint must be a SemanticObjectKind")

    def to_dict(self) -> dict[str, str]:
        return {"text": self.text, "kind_hint": self.kind_hint.value}

    @classmethod
    def from_payload(
        cls,
        payload: typing.Any,
        *,
        evidence_text: str,
        field_name: str = "mention",
    ) -> SemanticMention:
        expected = {"text", "kind_hint"}
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError(f"{field_name} has missing or unexpected fields")
        value = _validate_text(payload["text"], field_name, 120)
        if not _is_literal(evidence_text, value):
            raise ValueError(f"{field_name} is not literal player evidence")
        return cls(
            text=value,
            kind_hint=_enum(SemanticObjectKind, payload["kind_hint"]),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class SemanticArgument:
    """One semantic role filled by a literal, unresolved mention."""

    role: SemanticArgumentRole
    mention: SemanticMention

    def __post_init__(self) -> None:
        if not isinstance(self.role, SemanticArgumentRole):
            raise TypeError("role must be a SemanticArgumentRole")
        if not isinstance(self.mention, SemanticMention):
            raise TypeError("mention must be a SemanticMention")

    def to_dict(self) -> dict[str, typing.Any]:
        return {"role": self.role.value, "mention": self.mention.to_dict()}

    @classmethod
    def from_payload(
        cls,
        payload: typing.Any,
        *,
        evidence_text: str,
    ) -> SemanticArgument:
        expected = {"role", "mention"}
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("semantic argument has missing or unexpected fields")
        return cls(
            role=_enum(SemanticArgumentRole, payload["role"]),
            mention=SemanticMention.from_payload(
                payload["mention"],
                evidence_text=evidence_text,
                field_name="argument mention",
            ),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class SemanticActionFrame:
    """Predicate and typed arguments for one already-classified intent step."""

    predicate: str
    family: SemanticActionFamily
    arguments: tuple[SemanticArgument, ...]

    def __post_init__(self) -> None:
        _validate_text(self.predicate, "predicate", 120)
        if not isinstance(self.family, SemanticActionFamily):
            raise TypeError("family must be a SemanticActionFamily")
        if not isinstance(self.arguments, tuple) or len(self.arguments) > MAX_ACTION_ARGUMENTS:
            raise ValueError("arguments must be a tuple with at most 12 items")
        if any(not isinstance(item, SemanticArgument) for item in self.arguments):
            raise TypeError("arguments must contain SemanticArgument values")
        keys = [(item.role, item.mention.text.casefold()) for item in self.arguments]
        if len(keys) != len(set(keys)):
            raise ValueError("semantic arguments must not repeat the same role and mention")

    def to_dict(self) -> dict[str, typing.Any]:
        return {
            "predicate": self.predicate,
            "family": self.family.value,
            "arguments": [item.to_dict() for item in self.arguments],
        }

    @classmethod
    def from_payload(
        cls,
        payload: typing.Any,
        *,
        evidence_text: str,
    ) -> SemanticActionFrame:
        expected = {"predicate", "family", "arguments"}
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("action_frame has missing or unexpected fields")
        predicate = _validate_text(payload["predicate"], "predicate", 120)
        if not _is_literal(evidence_text, predicate):
            raise ValueError("action predicate is not literal player evidence")
        raw_arguments = payload["arguments"]
        if not isinstance(raw_arguments, list) or len(raw_arguments) > MAX_ACTION_ARGUMENTS:
            raise ValueError("action_frame arguments must be a bounded array")
        arguments = tuple(
            SemanticArgument.from_payload(item, evidence_text=evidence_text)
            for item in raw_arguments
        )
        return cls(
            predicate=predicate,
            family=_enum(SemanticActionFamily, payload["family"]),
            arguments=arguments,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class SemanticRelationClaim:
    """A directed, evidence-grounded relation claim; never a write instruction."""

    step_index: int
    subject: SemanticMention
    predicate: str
    object: SemanticMention
    relation_family: SemanticRelationFamily
    polarity: SemanticPolarity
    modality: SemanticModality
    source_excerpt: str
    attributed_to: SemanticMention | None = None
    temporal_expression: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or self.step_index < 0
        ):
            raise ValueError("relation step_index must be a non-negative integer")
        if not isinstance(self.subject, SemanticMention) or not isinstance(self.object, SemanticMention):
            raise TypeError("relation subject and object must be SemanticMention values")
        _validate_text(self.predicate, "relation predicate", 120)
        if not isinstance(self.relation_family, SemanticRelationFamily):
            raise TypeError("relation_family must be a SemanticRelationFamily")
        if not isinstance(self.polarity, SemanticPolarity):
            raise TypeError("relation polarity must be a SemanticPolarity")
        if not isinstance(self.modality, SemanticModality):
            raise TypeError("relation modality must be a SemanticModality")
        _validate_text(self.source_excerpt, "relation source_excerpt", 300)
        if self.attributed_to is not None and not isinstance(self.attributed_to, SemanticMention):
            raise TypeError("attributed_to must be a SemanticMention or None")
        if self.temporal_expression is not None:
            _validate_text(self.temporal_expression, "temporal_expression", 120)

    def to_dict(self) -> dict[str, typing.Any]:
        return {
            "step_index": self.step_index,
            "subject": self.subject.to_dict(),
            "predicate": self.predicate,
            "object": self.object.to_dict(),
            "relation_family": self.relation_family.value,
            "polarity": self.polarity.value,
            "modality": self.modality.value,
            "source_excerpt": self.source_excerpt,
            "attributed_to": (
                None if self.attributed_to is None else self.attributed_to.to_dict()
            ),
            "temporal_expression": self.temporal_expression,
        }

    @classmethod
    def from_payload(
        cls,
        payload: typing.Any,
        *,
        evidence_text: str,
    ) -> SemanticRelationClaim:
        expected = {
            "step_index", "subject", "predicate", "object", "relation_family",
            "polarity", "modality", "source_excerpt", "attributed_to",
            "temporal_expression",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("relation claim has missing or unexpected fields")
        index = payload["step_index"]
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("relation step_index must be a non-negative integer")
        predicate = _validate_text(payload["predicate"], "relation predicate", 120)
        excerpt = _validate_text(payload["source_excerpt"], "relation source_excerpt", 300)
        if not _is_literal(evidence_text, excerpt):
            raise ValueError("relation source_excerpt is not grounded in player input")
        if not _is_literal(evidence_text, predicate):
            raise ValueError("relation predicate is not literal player evidence")
        attribution_payload = payload["attributed_to"]
        temporal = payload["temporal_expression"]
        if temporal is not None:
            temporal = _validate_text(temporal, "temporal_expression", 120)
            if not _is_literal(evidence_text, temporal):
                raise ValueError("temporal_expression is not literal player evidence")
        return cls(
            step_index=index,
            subject=SemanticMention.from_payload(
                payload["subject"], evidence_text=evidence_text, field_name="relation subject"
            ),
            predicate=predicate,
            object=SemanticMention.from_payload(
                payload["object"], evidence_text=evidence_text, field_name="relation object"
            ),
            relation_family=_enum(SemanticRelationFamily, payload["relation_family"]),
            polarity=_enum(SemanticPolarity, payload["polarity"]),
            modality=_enum(SemanticModality, payload["modality"]),
            source_excerpt=excerpt,
            attributed_to=(
                None if attribution_payload is None else SemanticMention.from_payload(
                    attribution_payload,
                    evidence_text=evidence_text,
                    field_name="relation attribution",
                )
            ),
            temporal_expression=temporal,
        )


def _validate_text(value: typing.Any, field_name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} must not exceed {maximum} characters")
    return normalized


def _enum[EnumT: enum.Enum](
    enum_type: type[EnumT],
    value: typing.Any,
) -> EnumT:
    if not isinstance(value, str):
        raise TypeError("enum fields must be strings")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"unsupported {enum_type.__name__}: {value}") from exc


def _is_literal(source: str, fragment: str) -> bool:
    normalize = lambda value: unicodedata.normalize("NFKC", value).casefold()
    return normalize(fragment) in normalize(source)
