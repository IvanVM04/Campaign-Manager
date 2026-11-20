"""Versioned, durable partial checkpoint for backend-derived player actions.

The checkpoint stores only bounded action candidates and execution progress. It
never accepts model-supplied outcomes, permissions, or canonical references.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import re
from typing import Any

from models.player_turn_interpretation_v3 import (
    GameplayActionCandidate,
    GameplayActionEligibility,
    GameplayActionReason,
    GameplayProcessingState,
    GameplayResolvedReference,
    GameplayResolvedReferenceKind,
    GameplayUnlockCondition,
    GameplayWorkflow,
)
from models.semantic_frames import SemanticMention, SemanticObjectKind

CHECKPOINT_SCHEMA_VERSION = 1
MAX_CHECKPOINT_NODES = 12
MAX_CHECKPOINT_BYTES = 131_072
MAX_FACT_VALIDATION_RECEIPTS = 12
MAX_FACT_CANDIDATE_BYTES = 16_384
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FACT_ID_RE = re.compile(r"^fact_[a-z][a-z0-9_]{0,26}$")
_ACT_ID_RE = re.compile(r"^act_[a-z][a-z0-9_]{0,27}$")
_ALLOWED_CLARIFICATION_SLOTS = frozenset(
    {"actor", "target", "action", "sequence", "reference"}
)


class ActionCheckpointValidationError(ValueError):
    """Safe checkpoint decoding failure with a fixed code and field path."""

    def __init__(self, code: str, field_path: str) -> None:
        self.code = code
        self.field_path = field_path
        super().__init__(f"Invalid action checkpoint ({code}) at {field_path}")


class ActionExecutionState(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_INPUT = "awaiting_input"
    RESOLVED = "resolved"
    EXECUTION_FAILED = "execution_failed"
    SKIPPED = "skipped"


class ActionOutcome(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class FactValidationState(str, enum.Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"


@dataclasses.dataclass(frozen=True, slots=True)
class FactValidationReceipt:
    """Backend-only receipt binding a fact decision to one exact v3 candidate."""

    fact_local_id: str
    source_act_id: str
    candidate_sha256: str
    candidate_json: str
    state: FactValidationState

    def __post_init__(self) -> None:
        if not isinstance(self.fact_local_id, str) or not _FACT_ID_RE.fullmatch(
            self.fact_local_id
        ):
            raise ValueError("fact_local_id must be a bounded fact_ identifier")
        if not isinstance(self.source_act_id, str) or not _ACT_ID_RE.fullmatch(
            self.source_act_id
        ):
            raise ValueError("source_act_id must be a bounded act_ identifier")
        _safe_digest(self.candidate_sha256, "candidate_sha256")
        if not isinstance(self.candidate_json, str):
            raise TypeError("candidate_json must be text")
        if len(self.candidate_json.encode("utf-8")) > MAX_FACT_CANDIDATE_BYTES:
            raise ValueError("candidate_json exceeds its byte budget")
        try:
            candidate = json.loads(self.candidate_json)
        except (TypeError, ValueError):
            raise ValueError("candidate_json must contain valid JSON") from None
        if not isinstance(candidate, dict):
            raise TypeError("candidate_json must contain an object")
        expected_candidate_fields = {
            "local_id", "source_act_id", "fact_kind", "subject",
            "predicate_surface", "object", "value_surface", "relation_family",
            "normalized_relation_type", "direction", "polarity",
            "epistemic_status", "temporal_scope", "attributed_source",
            "evidence_spans",
        }
        if set(candidate) != expected_candidate_fields:
            raise ValueError("candidate_json does not match the fact candidate contract")
        if (
            candidate.get("local_id") != self.fact_local_id
            or candidate.get("source_act_id") != self.source_act_id
        ):
            raise ValueError("candidate_json identity does not match receipt")
        canonical = json.dumps(
            candidate,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if canonical != self.candidate_json:
            raise ValueError("candidate_json must use canonical JSON encoding")
        if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != self.candidate_sha256:
            raise ValueError("candidate_json does not match candidate_sha256")
        if not isinstance(self.state, FactValidationState):
            raise TypeError("state must be a FactValidationState")

    def to_dict(self) -> dict[str, str]:
        return {
            "fact_local_id": self.fact_local_id,
            "source_act_id": self.source_act_id,
            "candidate_sha256": self.candidate_sha256,
            "candidate_json": self.candidate_json,
            "state": self.state.value,
        }


def _positive_int(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _safe_digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _exact_object(value: Any, expected: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{name} has missing or unexpected fields")
    return value


def _safe_mention(value: Any, name: str = "mention") -> SemanticMention:
    raw = _exact_object(value, {"text", "kind_hint"}, name)
    if not isinstance(raw["text"], str):
        raise TypeError(f"{name}.text must be text")
    if not isinstance(raw["kind_hint"], str):
        raise TypeError(f"{name}.kind_hint must be text")
    return SemanticMention(
        text=raw["text"],
        kind_hint=SemanticObjectKind(raw["kind_hint"]),
    )


def _candidate_to_dict(candidate: GameplayActionCandidate) -> dict[str, Any]:
    return {
        "local_id": candidate.local_id,
        "source_event_id": candidate.source_event_id,
        "actor": candidate.actor.to_dict(),
        "action_type": candidate.action_type,
        "eligibility": candidate.eligibility.value,
        "reason": candidate.reason.value,
        "workflow": candidate.workflow.value,
        "unlock_condition": candidate.unlock_condition.value,
        "processing_state": candidate.processing_state.value,
        "target_mentions": [item.to_dict() for item in candidate.target_mentions],
        "dependency_event_ids": list(candidate.dependency_event_ids),
        "resolved_references": [
            {
                "mention": item.mention.to_dict(),
                "category": item.category.value,
                "referent_id": item.referent_id,
                "name": item.name,
            }
            for item in candidate.resolved_references
        ],
    }


def _candidate_from_dict(value: Any) -> GameplayActionCandidate:
    raw = _exact_object(
        value,
        {
            "local_id", "source_event_id", "actor", "action_type",
            "eligibility", "reason", "workflow", "unlock_condition",
            "processing_state", "target_mentions", "dependency_event_ids",
            "resolved_references",
        },
        "candidate",
    )
    targets = raw["target_mentions"]
    dependencies = raw["dependency_event_ids"]
    references = raw["resolved_references"]
    if not isinstance(targets, list) or len(targets) > 8:
        raise ValueError("candidate target_mentions must be a bounded array")
    if not isinstance(dependencies, list) or len(dependencies) > MAX_CHECKPOINT_NODES:
        raise ValueError("candidate dependency_event_ids must be a bounded array")
    if not isinstance(references, list) or len(references) > 16:
        raise ValueError("candidate resolved_references must be a bounded array")

    resolved_references = []
    for item in references:
        reference = _exact_object(
            item, {"mention", "category", "referent_id", "name"},
            "resolved_reference",
        )
        resolved_references.append(
            GameplayResolvedReference(
                mention=_safe_mention(reference["mention"], "resolved_reference.mention"),
                category=GameplayResolvedReferenceKind(reference["category"]),
                referent_id=reference["referent_id"],
                name=reference["name"],
            )
        )

    return GameplayActionCandidate(
        local_id=raw["local_id"],
        source_event_id=raw["source_event_id"],
        actor=_safe_mention(raw["actor"], "candidate.actor"),
        action_type=raw["action_type"],
        eligibility=GameplayActionEligibility(raw["eligibility"]),
        reason=GameplayActionReason(raw["reason"]),
        workflow=GameplayWorkflow(raw["workflow"]),
        unlock_condition=GameplayUnlockCondition(raw["unlock_condition"]),
        processing_state=GameplayProcessingState(raw["processing_state"]),
        target_mentions=tuple(
            _safe_mention(item, "candidate.target_mentions")
            for item in targets
        ),
        dependency_event_ids=tuple(dependencies),
        resolved_references=tuple(resolved_references),
    )


def processing_state_for(state: ActionExecutionState) -> GameplayProcessingState:
    return {
        ActionExecutionState.PENDING: GameplayProcessingState.PENDING,
        ActionExecutionState.IN_PROGRESS: GameplayProcessingState.ADJUDICATING,
        ActionExecutionState.AWAITING_INPUT: GameplayProcessingState.AWAITING_INPUT,
        ActionExecutionState.RESOLVED: GameplayProcessingState.RESOLVED,
        ActionExecutionState.EXECUTION_FAILED: GameplayProcessingState.FAILED,
        ActionExecutionState.SKIPPED: GameplayProcessingState.BLOCKED,
    }[state]


@dataclasses.dataclass(frozen=True, slots=True)
class ActionCheckpointNode:
    """One action candidate and its durable processing state."""

    candidate: GameplayActionCandidate
    source_order: int
    state: ActionExecutionState
    execution_key: str
    attempt_count: int = 0
    outcome: ActionOutcome | None = None
    clarification_slots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, GameplayActionCandidate):
            raise TypeError("candidate must be a GameplayActionCandidate")
        if isinstance(self.source_order, bool) or not isinstance(self.source_order, int):
            raise TypeError("source_order must be an integer")
        if self.source_order < 0:
            raise ValueError("source_order must not be negative")
        if not isinstance(self.state, ActionExecutionState):
            raise TypeError("state must be an ActionExecutionState")
        if not isinstance(self.execution_key, str) or _SHA256_RE.fullmatch(
            self.execution_key
        ) is None:
            raise ValueError("execution_key must be a lowercase SHA-256 digest")
        if isinstance(self.attempt_count, bool) or not isinstance(self.attempt_count, int):
            raise TypeError("attempt_count must be an integer")
        if self.attempt_count < 0:
            raise ValueError("attempt_count must not be negative")
        if self.outcome is not None and not isinstance(self.outcome, ActionOutcome):
            raise TypeError("outcome must be an ActionOutcome or None")
        if not isinstance(self.clarification_slots, tuple):
            raise TypeError("clarification_slots must be a tuple")
        if len(self.clarification_slots) > 5:
            raise ValueError("clarification_slots must be bounded to five slots")
        if any(
            not isinstance(item, str) or item not in _ALLOWED_CLARIFICATION_SLOTS
            for item in self.clarification_slots
        ):
            raise ValueError("clarification_slots contains an unsupported slot")
        if len(set(self.clarification_slots)) != len(self.clarification_slots):
            raise ValueError("clarification_slots must be unique")
        if self.candidate.processing_state is not processing_state_for(self.state):
            raise ValueError("candidate and checkpoint processing states must match")
        if self.state is ActionExecutionState.RESOLVED:
            if self.outcome is None:
                raise ValueError("resolved actions require an authoritative outcome")
        elif self.outcome is not None:
            raise ValueError("only resolved actions may carry an outcome")
        if self.state in {
            ActionExecutionState.IN_PROGRESS,
            ActionExecutionState.EXECUTION_FAILED,
        } and self.attempt_count < 1:
            raise ValueError("started actions require an attempt count")
        if self.state is ActionExecutionState.AWAITING_INPUT:
            if not self.clarification_slots:
                raise ValueError("awaiting-input actions require missing slots")
            if self.candidate.eligibility is not GameplayActionEligibility.REQUIRES_CLARIFICATION:
                raise ValueError("awaiting-input candidate must require clarification")
        elif self.clarification_slots:
            raise ValueError("clarification slots are only valid while awaiting input")
        if (
            self.candidate.eligibility is GameplayActionEligibility.INELIGIBLE
            and self.state is not ActionExecutionState.SKIPPED
        ):
            raise ValueError("ineligible candidates must be skipped")
        if (
            self.candidate.eligibility is GameplayActionEligibility.REQUIRES_CLARIFICATION
            and self.state is not ActionExecutionState.AWAITING_INPUT
        ):
            raise ValueError("clarification candidates must await input")
        if (
            self.candidate.eligibility is GameplayActionEligibility.ELIGIBLE
            and self.state is ActionExecutionState.AWAITING_INPUT
        ):
            raise ValueError("eligible candidates cannot await input without a new gate")
        if (
            self.state is ActionExecutionState.SKIPPED
            and self.candidate.eligibility is not GameplayActionEligibility.INELIGIBLE
        ):
            raise ValueError("skipped actions must be ineligible")
        if (
            self.state in {
                ActionExecutionState.IN_PROGRESS,
                ActionExecutionState.EXECUTION_FAILED,
                ActionExecutionState.RESOLVED,
            }
            and self.candidate.eligibility is not GameplayActionEligibility.ELIGIBLE
        ):
            raise ValueError("started and resolved actions must be eligible")
        if (
            self.state is ActionExecutionState.PENDING
            and self.candidate.eligibility not in {
                GameplayActionEligibility.ELIGIBLE,
                GameplayActionEligibility.BLOCKED_BY_DEPENDENCY,
            }
        ):
            raise ValueError("pending actions must be eligible or dependency-blocked")


@dataclasses.dataclass(frozen=True, slots=True)
class PlayerActionCheckpoint:
    """Versioned checkpoint bound to one durable turn, source and context revision."""

    resolution_id: int
    context_revision: int
    source_sha256: str
    interpretation_sha256: str
    nodes: tuple[ActionCheckpointNode, ...]
    fact_validation_receipts: tuple[FactValidationReceipt, ...] = ()
    schema_version: int = CHECKPOINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _positive_int(self.resolution_id, "resolution_id")
        _positive_int(self.context_revision, "context_revision")
        _safe_digest(self.source_sha256, "source_sha256")
        _safe_digest(self.interpretation_sha256, "interpretation_sha256")
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != CHECKPOINT_SCHEMA_VERSION
        ):
            raise ValueError("unsupported action checkpoint schema_version")
        if not isinstance(self.nodes, tuple) or len(self.nodes) > MAX_CHECKPOINT_NODES:
            raise ValueError("checkpoint nodes must be a bounded tuple")
        if any(not isinstance(item, ActionCheckpointNode) for item in self.nodes):
            raise TypeError("checkpoint nodes must contain ActionCheckpointNode values")
        if (
            not isinstance(self.fact_validation_receipts, tuple)
            or len(self.fact_validation_receipts) > MAX_FACT_VALIDATION_RECEIPTS
        ):
            raise ValueError("fact_validation_receipts must be a bounded tuple")
        if any(
            not isinstance(item, FactValidationReceipt)
            for item in self.fact_validation_receipts
        ):
            raise TypeError(
                "fact_validation_receipts must contain FactValidationReceipt values"
            )
        fact_ids = tuple(
            item.fact_local_id for item in self.fact_validation_receipts
        )
        if len(set(fact_ids)) != len(fact_ids):
            raise ValueError("fact validation receipt IDs must be unique")

        event_ids = tuple(item.candidate.source_event_id for item in self.nodes)
        action_ids = tuple(item.candidate.local_id for item in self.nodes)
        orders = tuple(item.source_order for item in self.nodes)
        execution_keys = tuple(item.execution_key for item in self.nodes)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("checkpoint event IDs must be unique")
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("checkpoint action IDs must be unique")
        if len(set(orders)) != len(orders):
            raise ValueError("checkpoint source order must be unique")
        if len(set(execution_keys)) != len(execution_keys):
            raise ValueError("checkpoint execution keys must be unique")
        if any(order >= MAX_CHECKPOINT_NODES for order in orders):
            raise ValueError("checkpoint source order exceeds the node limit")
        if orders != tuple(sorted(orders)):
            raise ValueError("checkpoint nodes must be stored in source order")

        by_event = {item.candidate.source_event_id: item for item in self.nodes}
        for node in self.nodes:
            for dependency_id in node.candidate.dependency_event_ids:
                dependency = by_event.get(dependency_id)
                if dependency is None:
                    raise ValueError("checkpoint dependency must reference a stored event")
                if dependency.source_order >= node.source_order:
                    raise ValueError("checkpoint dependency must precede its dependent event")
                if dependency_id == node.candidate.source_event_id:
                    raise ValueError("checkpoint node cannot depend on itself")

        self._validate_acyclic(by_event)

    @staticmethod
    def _validate_acyclic(nodes: dict[str, ActionCheckpointNode]) -> None:
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(event_id: str) -> None:
            if event_id in visiting:
                raise ValueError("action dependency graph contains a cycle")
            if event_id in visited:
                return
            visiting.add(event_id)
            node = nodes[event_id]
            for dependency_id in node.candidate.dependency_event_ids:
                visit(dependency_id)
            visiting.remove(event_id)
            visited.add(event_id)

        for event_id in nodes:
            visit(event_id)

    def validate_progress_from(self, previous: PlayerActionCheckpoint) -> None:
        """Require a checkpoint update to preserve identity and advance progress."""
        if not isinstance(previous, PlayerActionCheckpoint):
            raise TypeError("previous must be a PlayerActionCheckpoint")
        if (
            self.resolution_id != previous.resolution_id
            or self.context_revision != previous.context_revision
            or self.source_sha256 != previous.source_sha256
            or self.interpretation_sha256 != previous.interpretation_sha256
        ):
            raise ValueError("checkpoint identity cannot change during progress")

        previous_nodes = {
            node.candidate.source_event_id: node for node in previous.nodes
        }
        current_nodes = {
            node.candidate.source_event_id: node for node in self.nodes
        }
        if set(previous_nodes) != set(current_nodes):
            raise ValueError("checkpoint progress cannot add or drop action nodes")

        allowed_transitions = {
            ActionExecutionState.PENDING: {
                ActionExecutionState.PENDING,
                ActionExecutionState.IN_PROGRESS,
                ActionExecutionState.AWAITING_INPUT,
                ActionExecutionState.SKIPPED,
            },
            ActionExecutionState.IN_PROGRESS: {
                ActionExecutionState.IN_PROGRESS,
                ActionExecutionState.AWAITING_INPUT,
                ActionExecutionState.RESOLVED,
                ActionExecutionState.EXECUTION_FAILED,
            },
            ActionExecutionState.AWAITING_INPUT: {
                ActionExecutionState.AWAITING_INPUT,
                ActionExecutionState.PENDING,
                ActionExecutionState.SKIPPED,
            },
            ActionExecutionState.EXECUTION_FAILED: {
                ActionExecutionState.EXECUTION_FAILED,
                ActionExecutionState.IN_PROGRESS,
            },
            ActionExecutionState.RESOLVED: {ActionExecutionState.RESOLVED},
            ActionExecutionState.SKIPPED: {ActionExecutionState.SKIPPED},
        }
        for event_id, old in previous_nodes.items():
            new = current_nodes[event_id]
            if (
                old.source_order != new.source_order
                or old.execution_key != new.execution_key
                or old.candidate.local_id != new.candidate.local_id
                or old.candidate.actor != new.candidate.actor
                or old.candidate.action_type != new.candidate.action_type
                or old.candidate.dependency_event_ids
                != new.candidate.dependency_event_ids
            ):
                raise ValueError("checkpoint action identity cannot change")
            if (
                old.candidate.target_mentions != new.candidate.target_mentions
                and old.state is not ActionExecutionState.AWAITING_INPUT
            ):
                raise ValueError(
                    "target mentions may only change while resuming clarification"
                )
            if not set(old.candidate.resolved_references).issubset(
                set(new.candidate.resolved_references)
            ):
                raise ValueError("checkpoint cannot discard resolved references")
            if new.state not in allowed_transitions[old.state]:
                raise ValueError("checkpoint action state cannot move backwards")

            expected_attempts = old.attempt_count
            if (
                old.state
                in {
                    ActionExecutionState.PENDING,
                    ActionExecutionState.EXECUTION_FAILED,
                }
                and new.state is ActionExecutionState.IN_PROGRESS
            ):
                expected_attempts += 1
            if new.attempt_count != expected_attempts:
                raise ValueError("checkpoint action attempt count is not monotonic")
            if old.state in {
                ActionExecutionState.RESOLVED,
                ActionExecutionState.SKIPPED,
            } and new != old:
                raise ValueError("terminal checkpoint action is immutable")

        old_receipts = {
            item.fact_local_id: item
            for item in previous.fact_validation_receipts
        }
        new_receipts = {
            item.fact_local_id: item
            for item in self.fact_validation_receipts
        }
        if not set(old_receipts).issubset(new_receipts):
            raise ValueError("checkpoint cannot drop fact validation receipts")
        for fact_id, old in old_receipts.items():
            new = new_receipts[fact_id]
            if (
                old.source_act_id != new.source_act_id
                or old.candidate_sha256 != new.candidate_sha256
                or old.candidate_json != new.candidate_json
            ):
                raise ValueError("fact validation receipt identity cannot change")
            if (
                old.state is not FactValidationState.PENDING
                and new.state is not old.state
            ):
                raise ValueError("final fact validation receipt cannot be reversed")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "resolution_id": self.resolution_id,
            "context_revision": self.context_revision,
            "source_sha256": self.source_sha256,
            "interpretation_sha256": self.interpretation_sha256,
            "fact_validation_receipts": [
                item.to_dict() for item in self.fact_validation_receipts
            ],
            "nodes": [
                {
                    "candidate": _candidate_to_dict(item.candidate),
                    "source_order": item.source_order,
                    "state": item.state.value,
                    "execution_key": item.execution_key,
                    "attempt_count": item.attempt_count,
                    "outcome": None if item.outcome is None else item.outcome.value,
                    "clarification_slots": list(item.clarification_slots),
                }
                for item in self.nodes
            ],
        }

    def to_json(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(payload.encode("utf-8")) > MAX_CHECKPOINT_BYTES:
            raise ValueError("action checkpoint exceeds its byte budget")
        return payload

    @classmethod
    def from_payload(cls, payload: Any) -> PlayerActionCheckpoint:
        try:
            raw = _exact_object(
                payload,
                {
                    "schema_version", "resolution_id", "context_revision",
                    "source_sha256", "interpretation_sha256", "nodes",
                    "fact_validation_receipts",
                },
                "action_checkpoint",
            )
            if not isinstance(raw["nodes"], list) or len(raw["nodes"]) > MAX_CHECKPOINT_NODES:
                raise ValueError("checkpoint nodes must be a bounded array")
            nodes = []
            for item in raw["nodes"]:
                node = _exact_object(
                    item,
                    {
                        "candidate", "source_order", "state", "execution_key",
                        "attempt_count", "outcome", "clarification_slots",
                    },
                    "checkpoint_node",
                )
                slots = node["clarification_slots"]
                if not isinstance(slots, list) or len(slots) > 5:
                    raise ValueError("clarification_slots must be a bounded array")
                outcome = (
                    None if node["outcome"] is None
                    else ActionOutcome(node["outcome"])
                )
                nodes.append(
                    ActionCheckpointNode(
                        candidate=_candidate_from_dict(node["candidate"]),
                        source_order=node["source_order"],
                        state=ActionExecutionState(node["state"]),
                        execution_key=node["execution_key"],
                        attempt_count=node["attempt_count"],
                        outcome=outcome,
                        clarification_slots=tuple(slots),
                    )
                )
            raw_receipts = raw["fact_validation_receipts"]
            if (
                not isinstance(raw_receipts, list)
                or len(raw_receipts) > MAX_FACT_VALIDATION_RECEIPTS
            ):
                raise ValueError("fact_validation_receipts must be a bounded array")
            fact_receipts = []
            for item in raw_receipts:
                receipt = _exact_object(
                    item,
                    {
                        "fact_local_id", "source_act_id",
                        "candidate_sha256", "candidate_json", "state",
                    },
                    "fact_validation_receipt",
                )
                fact_receipts.append(
                    FactValidationReceipt(
                        fact_local_id=receipt["fact_local_id"],
                        source_act_id=receipt["source_act_id"],
                        candidate_sha256=receipt["candidate_sha256"],
                        candidate_json=receipt["candidate_json"],
                        state=FactValidationState(receipt["state"]),
                    )
                )
            return cls(
                schema_version=raw["schema_version"],
                resolution_id=raw["resolution_id"],
                context_revision=raw["context_revision"],
                source_sha256=raw["source_sha256"],
                interpretation_sha256=raw["interpretation_sha256"],
                nodes=tuple(nodes),
                fact_validation_receipts=tuple(fact_receipts),
            )
        except ActionCheckpointValidationError:
            raise
        except (TypeError, ValueError, KeyError):
            raise ActionCheckpointValidationError("invalid_payload", "checkpoint") from None

    @classmethod
    def from_json(cls, payload: str) -> PlayerActionCheckpoint:
        if not isinstance(payload, str):
            raise ActionCheckpointValidationError("invalid_json_input", "checkpoint")
        if len(payload.encode("utf-8")) > MAX_CHECKPOINT_BYTES:
            raise ActionCheckpointValidationError("payload_too_large", "checkpoint")
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError):
            raise ActionCheckpointValidationError("invalid_json", "checkpoint") from None
        return cls.from_payload(decoded)
