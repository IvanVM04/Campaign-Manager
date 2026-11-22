"""Versioned durable staging format for individually planned v3 actions.

During planning, the durable resolution's proposal_json column may hold this
snapshot. Each append is persisted together with the action checkpoint through
TurnResolutionRepository.save_action_checkpoint's lease/CAS update. The normal
prepared transition later replaces this staging envelope with the final
aggregate proposal expected by TurnResolutionCodec.
"""
from __future__ import annotations

import dataclasses
import json
import re
from typing import Any

from models.player_action_checkpoint import MAX_CHECKPOINT_NODES
from services.turns.turn_resolution_service import TurnResolutionPlan


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EVENT_ID_RE = re.compile(r"^event_[a-z][a-z0-9_]{0,26}$")
_ACTION_ID_RE = re.compile(r"^action_[a-z][a-z0-9_]{0,26}$")
_MAX_ENTRY_BYTES = 32_768
_MAX_SNAPSHOT_BYTES = 131_072


class V3ActionProgressValidationError(ValueError):
    """Safe error decoding or advancing the staged v3 action progress envelope."""

    def __init__(self, code: str, field_path: str) -> None:
        self.code = code
        self.field_path = field_path
        super().__init__(f"Invalid v3 action progress ({code}) at {field_path}")


def _positive_int(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")


def _json_object(value: Any, field: str, *, nullable: bool = False) -> dict[str, Any] | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a JSON string")
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must contain valid JSON") from None
    if not isinstance(decoded, dict):
        raise TypeError(f"{field} must contain a JSON object")
    return decoded


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _exact_object(value: Any, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} has missing or unexpected fields")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class V3ActionProgressEntry:
    """One action's exact staged legacy plan and mechanics evidence."""

    event_id: str
    action_id: str
    source_order: int
    execution_key: str
    evidence_excerpt: str
    operations_json: str
    intent_json: str | None = None
    mechanics_json: str | None = None
    mechanics_decision_json: str | None = None
    awaiting_manual_roll: bool = False
    clarification_question: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not _EVENT_ID_RE.fullmatch(self.event_id):
            raise ValueError("event_id must be a bounded event_ identifier")
        if not isinstance(self.action_id, str) or not _ACTION_ID_RE.fullmatch(self.action_id):
            raise ValueError("action_id must be a bounded action_ identifier")
        if isinstance(self.source_order, bool) or not isinstance(self.source_order, int):
            raise TypeError("source_order must be an integer")
        if self.source_order < 0 or self.source_order >= MAX_CHECKPOINT_NODES:
            raise ValueError("source_order exceeds the action node bounds")
        if not isinstance(self.execution_key, str) or not _SHA256_RE.fullmatch(self.execution_key):
            raise ValueError("execution_key must be a lowercase SHA-256 digest")
        if (
            not isinstance(self.evidence_excerpt, str)
            or not self.evidence_excerpt.strip()
            or len(self.evidence_excerpt) > 300
        ):
            raise ValueError("evidence_excerpt must contain 1-300 characters")
        operations = _json_object(self.operations_json, "operations_json")
        if operations is None:
            raise TypeError("operations_json must contain an object")
        if set(operations) != {"operations"} or not isinstance(operations["operations"], list):
            raise ValueError("operations_json must be a typed operation envelope")
        intent = _json_object(self.intent_json, "intent_json", nullable=True)
        if intent is not None and (
            isinstance(intent.get("schema_version"), bool)
            or not isinstance(intent.get("schema_version"), int)
            or intent.get("schema_version") != 1
        ):
            raise ValueError("intent_json must use TurnResolutionCodec envelope v1")
        mechanics = _json_object(self.mechanics_json, "mechanics_json", nullable=True)
        if mechanics is not None and set(mechanics) != {"decision", "check"}:
            raise ValueError("mechanics_json must contain a complete mechanics result")
        decision = _json_object(
            self.mechanics_decision_json,
            "mechanics_decision_json",
            nullable=True,
        )
        if decision is not None and "decision" not in decision:
            raise ValueError("mechanics_decision_json must identify its decision")
        if not isinstance(self.awaiting_manual_roll, bool):
            raise TypeError("awaiting_manual_roll must be a boolean")
        if self.clarification_question is not None and (
            not isinstance(self.clarification_question, str)
            or not self.clarification_question.strip()
            or len(self.clarification_question) > 300
        ):
            raise ValueError("clarification_question must be bounded text or None")
        if self.awaiting_manual_roll and self.mechanics_decision_json is None:
            raise ValueError("manual roll staging requires a mechanics decision")
        serialized = _canonical_json(self.to_dict())
        if len(serialized.encode("utf-8")) > _MAX_ENTRY_BYTES:
            raise ValueError("action progress entry exceeds its byte budget")

    @classmethod
    def from_plan(
        cls,
        *,
        event_id: str,
        action_id: str,
        source_order: int,
        execution_key: str,
        evidence_excerpt: str,
        plan: TurnResolutionPlan,
    ) -> V3ActionProgressEntry:
        """Serialize the exact one-action TurnResolutionPlan without re-running providers."""
        if not isinstance(plan, TurnResolutionPlan):
            raise TypeError("plan must be a TurnResolutionPlan")
        from services.turns.turn_resolution_codec import TurnResolutionCodec

        operations_json = TurnResolutionCodec.serialize_operations(plan)
        intent_json = TurnResolutionCodec.intent_to_json(plan)
        mechanics_json = TurnResolutionCodec.mechanics_to_json(plan.mechanics_result)
        decision = plan.mechanics_decision
        decision_json = None
        if decision is not None:
            decision_json = _canonical_json(
                {
                    "decision": decision.decision.value,
                    "skill": decision.skill.value if decision.skill else None,
                    "ability": decision.ability.value if decision.ability else None,
                    "dc": decision.dc,
                    "advantage": decision.advantage,
                    "disadvantage": decision.disadvantage,
                    "situational_modifier": decision.situational_modifier,
                    "reason": decision.reason,
                    "question": decision.question,
                }
            )
        return cls(
            event_id=event_id,
            action_id=action_id,
            source_order=source_order,
            execution_key=execution_key,
            evidence_excerpt=evidence_excerpt,
            operations_json=operations_json,
            intent_json=intent_json,
            mechanics_json=mechanics_json,
            mechanics_decision_json=decision_json,
            awaiting_manual_roll=plan.awaiting_manual_roll,
            clarification_question=plan.clarification_question,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "action_id": self.action_id,
            "source_order": self.source_order,
            "execution_key": self.execution_key,
            "evidence_excerpt": self.evidence_excerpt,
            "operations_json": self.operations_json,
            "intent_json": self.intent_json,
            "mechanics_json": self.mechanics_json,
            "mechanics_decision_json": self.mechanics_decision_json,
            "awaiting_manual_roll": self.awaiting_manual_roll,
            "clarification_question": self.clarification_question,
        }

    @classmethod
    def from_payload(cls, payload: Any) -> V3ActionProgressEntry:
        raw = _exact_object(
            payload,
            {
                "event_id", "action_id", "source_order", "execution_key",
                "evidence_excerpt", "operations_json", "intent_json",
                "mechanics_json", "mechanics_decision_json",
                "awaiting_manual_roll", "clarification_question",
            },
            "v3_action_progress_entry",
        )
        return cls(**raw)


@dataclasses.dataclass(frozen=True, slots=True)
class V3ActionProgressSnapshot:
    """Monotonic, identity-bound collection of staged action plans."""

    resolution_id: int
    context_revision: int
    source_sha256: str
    entries: tuple[V3ActionProgressEntry, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        _positive_int(self.resolution_id, "resolution_id")
        _positive_int(self.context_revision, "context_revision")
        if not isinstance(self.source_sha256, str) or not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != 1
        ):
            raise ValueError("unsupported v3 action progress schema_version")
        if not isinstance(self.entries, tuple) or len(self.entries) > MAX_CHECKPOINT_NODES:
            raise ValueError("entries must be a bounded tuple")
        if any(not isinstance(item, V3ActionProgressEntry) for item in self.entries):
            raise TypeError("entries must contain V3ActionProgressEntry values")
        event_ids = tuple(item.event_id for item in self.entries)
        action_ids = tuple(item.action_id for item in self.entries)
        keys = tuple(item.execution_key for item in self.entries)
        orders = tuple(item.source_order for item in self.entries)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("progress event IDs must be unique")
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("progress action IDs must be unique")
        if len(set(keys)) != len(keys):
            raise ValueError("progress execution keys must be unique")
        if len(set(orders)) != len(orders) or orders != tuple(sorted(orders)):
            raise ValueError("progress entries must be in unique source order")
        if len(self.to_json().encode("utf-8")) > _MAX_SNAPSHOT_BYTES:
            raise ValueError("v3 action progress snapshot exceeds its byte budget")

    def append(self, entry: V3ActionProgressEntry) -> V3ActionProgressSnapshot:
        """Append exactly once; identical retries are idempotent, rebinding is rejected."""
        if not isinstance(entry, V3ActionProgressEntry):
            raise TypeError("entry must be a V3ActionProgressEntry")
        existing = next(
            (item for item in self.entries if item.event_id == entry.event_id),
            None,
        )
        if existing is not None:
            if existing == entry:
                return self
            raise ValueError("staged action identity or payload cannot be rebound")
        if any(item.execution_key == entry.execution_key for item in self.entries):
            raise ValueError("execution key is already assigned to another action")
        if self.entries and entry.source_order <= self.entries[-1].source_order:
            raise ValueError("staged actions must be appended in source order")
        return dataclasses.replace(self, entries=(*self.entries, entry))

    def entry_for_event(self, event_id: str) -> V3ActionProgressEntry | None:
        """Return the immutable staged action snapshot for one event."""
        if not isinstance(event_id, str) or not _EVENT_ID_RE.fullmatch(event_id):
            raise ValueError("event_id must be a bounded event_ identifier")
        return next(
            (item for item in self.entries if item.event_id == event_id),
            None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "resolution_id": self.resolution_id,
            "context_revision": self.context_revision,
            "source_sha256": self.source_sha256,
            "entries": [item.to_dict() for item in self.entries],
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    def to_repository_progress_updates(self) -> dict[str, str]:
        """Store staged actions in proposal_json while lifecycle_state is planning.

        The prepared transition replaces this staging envelope with the final
        aggregate operations payload used by the existing commit service.
        """
        return {"proposal_json": self.to_json()}

    @classmethod
    def from_payload(cls, payload: Any) -> V3ActionProgressSnapshot:
        raw = _exact_object(
            payload,
            {
                "schema_version", "resolution_id", "context_revision",
                "source_sha256", "entries",
            },
            "v3_action_progress",
        )
        if not isinstance(raw["entries"], list) or len(raw["entries"]) > MAX_CHECKPOINT_NODES:
            raise ValueError("entries must be a bounded JSON array")
        return cls(
            schema_version=raw["schema_version"],
            resolution_id=raw["resolution_id"],
            context_revision=raw["context_revision"],
            source_sha256=raw["source_sha256"],
            entries=tuple(
                V3ActionProgressEntry.from_payload(item)
                for item in raw["entries"]
            ),
        )

    @classmethod
    def from_json(cls, payload: str) -> V3ActionProgressSnapshot:
        if not isinstance(payload, str):
            raise TypeError("payload must be text")
        if len(payload.encode("utf-8")) > _MAX_SNAPSHOT_BYTES:
            raise ValueError("v3 action progress snapshot exceeds its byte budget")
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError):
            raise ValueError("v3 action progress snapshot must contain valid JSON") from None
        return cls.from_payload(decoded)

    @classmethod
    def empty(
        cls,
        *,
        resolution_id: int,
        context_revision: int,
        source_sha256: str,
    ) -> V3ActionProgressSnapshot:
        return cls(
            resolution_id=resolution_id,
            context_revision=context_revision,
            source_sha256=source_sha256,
        )
