from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum

from database import transaction
from models.campaign_scope import CampaignScope
from models.turn_record import TurnRecord
from models.turn_resolution_record import TurnResolutionRecord
from models.turn_resolution_result import TurnResolutionResult
from operations.character_operations import CharacterOperation
from models.operation_result import OperationResult, OperationStatus
from operations.operation_reference import OperationReference
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import WorldOperation
from repositories.campaign_state_version_repository import CampaignStateVersionRepository
from repositories.turn_repository import TurnRepository
from repositories.turn_resolution_repository import TurnResolutionRepository
from services.turn_resolution_service import (
    TurnResolutionPlan,
    TurnResolutionService,
)
from services.world_service import WorldService


class DurableNativeTurnError(RuntimeError):
    """Failure while executing or resuming a durable native turn."""


class DurableNativeTurnService:
    """Coordinates native automatic turns across durable lifecycle boundaries."""

    def __init__(
        self,
        *,
        scope: CampaignScope,
        resolver: TurnResolutionService,
        world_service: WorldService,
        context_service,
        turn_repository: TurnRepository,
        resolution_repository: TurnResolutionRepository | None = None,
        turn_execution_lock=None,
    ) -> None:
        self.scope = scope
        self.resolver = resolver
        self.world_service = world_service
        self.context_service = context_service
        self.turn_repository = turn_repository
        self.resolution_repository = resolution_repository or TurnResolutionRepository()
        self.revision_repository = CampaignStateVersionRepository()
        self.turn_execution_lock = turn_execution_lock

    @staticmethod
    def _json_default(value):
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return {
                field.name: getattr(value, field.name)
                for field in fields(value)
            }
        raise TypeError(f"cannot serialize {type(value).__name__}")

    @classmethod
    def _operation_value(cls, value):
        if isinstance(value, OperationReference):
            return "$" + value.name
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, tuple):
            return [cls._operation_value(item) for item in value]
        if isinstance(value, list):
            return [cls._operation_value(item) for item in value]
        if isinstance(value, dict):
            return {key: cls._operation_value(item) for key, item in value.items()}
        if is_dataclass(value):
            return {
                field.name: cls._operation_value(getattr(value, field.name))
                for field in fields(value)
            }
        return value

    def _serialize_operations(self, plan: TurnResolutionPlan) -> str:
        from services.operation_parser import OperationParser

        type_names = {
            operation_class: operation_name
            for operation_name, operation_class in OperationParser._BUILDERS.items()
        }
        serialized = []
        for raw in plan.ordered_operations:
            ref = None
            operation = raw
            if isinstance(raw, ReferencedOperation):
                ref = raw.ref
                operation = raw.operation
            operation_type = type_names.get(type(operation))
            if operation_type is None:
                raise DurableNativeTurnError(
                    f"unsupported operation type: {type(operation).__name__}"
                )
            payload = {
                "type": operation_type,
                **self._operation_value(operation),
            }
            if ref is not None:
                payload["ref"] = ref
            serialized.append(payload)
        return json.dumps({"operations": serialized}, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _mechanics_to_json(result) -> str | None:
        if result is None:
            return None
        decision = result.decision
        check = result.check
        roll = check.roll
        return json.dumps({
            "decision": {
                "decision": decision.decision.value,
                "skill": decision.skill.value if decision.skill else None,
                "ability": decision.ability.value if decision.ability else None,
                "dc": decision.dc,
                "advantage": decision.advantage,
                "disadvantage": decision.disadvantage,
                "situational_modifier": decision.situational_modifier,
                "reason": decision.reason,
                "question": decision.question,
            },
            "check": {
                "kind": check.kind,
                "ability": check.ability.value,
                "ability_score": check.ability_score,
                "ability_modifier": check.ability_modifier,
                "proficiency_bonus": check.proficiency_bonus,
                "proficiency_applied": check.proficiency_applied,
                "situational_modifier": check.situational_modifier,
                "rolls": list(roll.rolls),
                "selected": roll.selected,
                "mode": roll.mode.value,
                "modifier": roll.modifier,
                "total": roll.total,
                "dc": check.dc,
                "success": check.success,
            },
        }, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _mechanics_from_json(payload: str | None):
        if payload is None:
            return None
        from models.mechanics import MechanicsDecision, MechanicsDecisionType, MechanicsResult
        from rules_engine.dnd5e_2014.checks import CheckResult
        from rules_engine.dnd5e_2014.core.abilities import Ability
        from rules_engine.dnd5e_2014.core.dice import D20Roll, RollMode
        from rules_engine.dnd5e_2014.core.skills import Skill

        data = json.loads(payload)
        d = data["decision"]
        decision = MechanicsDecision(
            decision=MechanicsDecisionType(d["decision"]),
            skill=Skill(d["skill"]) if d["skill"] else None,
            ability=Ability(d["ability"]) if d["ability"] else None,
            dc=d["dc"],
            advantage=d["advantage"],
            disadvantage=d["disadvantage"],
            situational_modifier=d["situational_modifier"],
            reason=d["reason"],
            question=d["question"],
        )
        c = data["check"]
        roll = D20Roll(
            rolls=tuple(c["rolls"]),
            selected=c["selected"],
            mode=RollMode(c["mode"]),
            modifier=c["modifier"],
            total=c["total"],
        )
        check = CheckResult(
            kind=c["kind"],
            ability=Ability(c["ability"]),
            ability_score=c["ability_score"],
            ability_modifier=c["ability_modifier"],
            proficiency_bonus=c["proficiency_bonus"],
            proficiency_applied=c["proficiency_applied"],
            situational_modifier=c["situational_modifier"],
            roll=roll,
            dc=c["dc"],
            success=c["success"],
        )
        return MechanicsResult(decision, check)

    @staticmethod
    def _operation_results_json(result: TurnResolutionResult) -> str:
        return json.dumps([
            {
                "status": item.status.value,
                "message": item.message,
                "changed": item.changed,
                "success": item.success,
            }
            for item in result.operation_results
        ], separators=(",", ":"), sort_keys=True)

    def _context_and_history(self, conn):
        context = self.context_service.get_turn_context(
            campaign_id=self.scope.campaign_id,
            conn=conn,
        )
        fresh_world = self.world_service.repository.load_world(
            campaign_id=self.scope.campaign_id,
            conn=conn,
        )
        context = replace(context, world=fresh_world)
        self.world_service.world = fresh_world
        session_id = (
            context.current_session.session_id
            if context.current_session is not None
            else None
        )
        recent = self.turn_repository.list_recent_turns(
            session_id=session_id,
            limit=10,
            scope=self.scope,
            conn=conn,
        )
        return context, recent

    def _plan_from_record(self, record: TurnResolutionRecord) -> TurnResolutionPlan:
        parser = self.resolver.extractor.operation_parser
        parsed = parser.parse(record.proposal_json or '{"operations":[]}')
        ordered = tuple(parsed)
        def unwrap(raw):
            return raw.operation if isinstance(raw, ReferencedOperation) else raw
        world_operations = tuple(
            raw for raw in ordered if isinstance(unwrap(raw), WorldOperation)
        )
        character_operations = tuple(
            raw for raw in ordered if isinstance(unwrap(raw), CharacterOperation)
        )
        mechanics_result = self._mechanics_from_json(record.mechanics_json)
        return TurnResolutionPlan(
            player_input=record.player_input,
            narrative="",
            world_operations=world_operations,
            character_operations=character_operations,
            ordered_operations=ordered,
            mechanics_result=mechanics_result,
            mechanics_decision=mechanics_result.decision if mechanics_result else None,
        )

    @staticmethod
    def _fingerprint(player_input: str, session_id, dice_mode: str) -> str:
        raw = json.dumps(
            [player_input, session_id, dice_mode],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def play_turn(self, player_input: str, *, idempotency_key: str | None = None):
        if self.turn_execution_lock is None:
            return self._play_turn_locked(player_input, idempotency_key=idempotency_key)
        with self.turn_execution_lock.acquire():
            return self._play_turn_locked(player_input, idempotency_key=idempotency_key)

    def _play_turn_locked(self, player_input: str, *, idempotency_key: str | None = None):
        normalized = player_input.strip() if isinstance(player_input, str) else ""
        if not normalized:
            raise DurableNativeTurnError("player_input must not be empty")

        with transaction("DEFERRED") as conn:
            context, recent = self._context_and_history(conn)
            revision = self.revision_repository.get_revision(
                self.scope.campaign_id, conn=conn
            )
        session_id = (
            context.current_session.session_id
            if context.current_session is not None
            else None
        )
        previous_turn_id = recent[-1].id if recent else 0
        fingerprint = self._fingerprint(
            normalized, session_id, "automatic"
        )
        fallback_identity = hashlib.sha256(
            f"{fingerprint}:{previous_turn_id}".encode("utf-8")
        ).hexdigest()
        key = idempotency_key or "native-" + fallback_identity
        if not isinstance(key, str) or not key.strip() or len(key) > 500:
            raise DurableNativeTurnError("idempotency_key must contain 1-500 characters")

        with transaction("IMMEDIATE") as conn:
            record = self.resolution_repository.get_by_idempotency_key(
                "native", key, scope=self.scope, conn=conn
            )
            if record is not None:
                fingerprint = self._fingerprint(
                    normalized, record.session_id, "automatic"
                )
                if record.request_fingerprint != fingerprint:
                    raise DurableNativeTurnError(
                        "idempotency key was already used for a different request"
                    )
                if record.lifecycle_state == "completed":
                    turn = self.turn_repository.get_turn(
                        record.turn_id, scope=self.scope, conn=conn
                    )
                    if turn is None:
                        raise DurableNativeTurnError("completed resolution has no transcript")
                    return self._result_from_completed_record(record, turn, already_processed=True)
                if record.lifecycle_state == "awaiting_input":
                    question = json.loads(record.adjudication_json or "{}").get(
                        "clarification_question",
                        "Necesito una aclaración antes de resolver esa acción.",
                    )
                    return TurnResolutionResult(
                        player_input=record.player_input,
                        narrative=question,
                    )
                if record.lifecycle_state in {"committed", "narration_pending"}:
                    pass
                elif record.lifecycle_state in {"accepted", "planning", "prepared"}:
                    pass
                else:
                    raise DurableNativeTurnError(
                        f"turn request is in terminal or unsupported state: {record.lifecycle_state}"
                    )
            else:
                record = self.resolution_repository.create(
                    TurnResolutionRecord(
                        campaign_id=self.scope.campaign_id,
                        session_id=session_id,
                        player_input=normalized,
                        adapter_namespace="native",
                        idempotency_key=key,
                        request_fingerprint=fingerprint,
                    ),
                    scope=self.scope,
                    conn=conn,
                )

        if record.lifecycle_state in {"committed", "narration_pending"}:
            return self._resume_narration(record, already_processed=True)

        resume_prepared = record.lifecycle_state == "prepared"
        lease_token = None
        if not resume_prepared:
            lease_token = secrets.token_urlsafe(24)
            now = datetime.now(timezone.utc)
            with transaction("IMMEDIATE") as conn:
                record = self.resolution_repository.claim_for_planning(
                    record.id,
                    scope=self.scope,
                    lease_token=lease_token,
                    lease_expires_at=(now + timedelta(minutes=3)).isoformat(),
                    now=now.isoformat(),
                    conn=conn,
                )

        try:
            if resume_prepared:
                if record.context_revision != revision:
                    with transaction("IMMEDIATE") as conn:
                        self.resolution_repository.transition(
                            record.id,
                            "rejected",
                            scope=self.scope,
                            expected_state="prepared",
                            updates={"last_error_code": "stale_context"},
                            conn=conn,
                        )
                    raise DurableNativeTurnError(
                        "prepared turn became stale before commit and was rejected"
                    )
                plan = self._plan_from_record(record)
            else:
                plan = self.resolver.prepare_turn(
                    context,
                    normalized,
                    recent_turns=recent,
                    proposal_from_intent=True,
                )
                if plan.awaiting_manual_roll:
                    raise DurableNativeTurnError(
                        "automatic turn unexpectedly requested a manual roll"
                    )
                if plan.clarification_question is not None:
                    with transaction("IMMEDIATE") as conn:
                        self.resolution_repository.transition(
                            record.id,
                            "awaiting_input",
                            scope=self.scope,
                            expected_state="planning",
                            expected_lease_token=lease_token,
                            updates={
                                "adjudication_json": json.dumps(
                                    {"clarification_question": plan.clarification_question},
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                                "lease_token": None,
                                "lease_expires_at": None,
                            },
                            conn=conn,
                        )
                    return TurnResolutionResult(
                        player_input=normalized,
                        narrative=plan.clarification_question,
                    )
                proposal_json = self._serialize_operations(plan)
                mechanics_json = self._mechanics_to_json(plan.mechanics_result)

                with transaction("IMMEDIATE") as conn:
                    self.resolution_repository.transition(
                        record.id,
                        "prepared",
                        scope=self.scope,
                        expected_state="planning",
                        expected_lease_token=lease_token,
                        updates={
                            "context_revision": revision,
                            "proposal_json": proposal_json,
                            "adjudication_json": json.dumps(
                                {"decision": plan.mechanics_decision.decision.value}
                                if plan.mechanics_decision else {},
                                separators=(",", ":"),
                            ),
                            "mechanics_json": mechanics_json,
                            "lease_token": None,
                            "lease_expires_at": None,
                        },
                        conn=conn,
                    )

            with transaction("IMMEDIATE") as conn:
                current_revision = self.revision_repository.get_revision(
                    self.scope.campaign_id, conn=conn
                )
                if current_revision != revision:
                    raise DurableNativeTurnError(
                        "campaign state changed while the turn was being prepared; retry"
                    )
                current_context, current_recent = self._context_and_history(conn)
                if current_context != context or current_recent != recent:
                    raise DurableNativeTurnError(
                        "campaign context changed while the turn was being prepared; retry"
                    )
                result = self.resolver.apply_plan(
                    current_context, plan, conn=conn
                )
                if not result.all_operations_succeeded:
                    raise DurableNativeTurnError(
                        "one or more proposed consequences failed validation"
                    )
                resulting_revision = self.revision_repository.get_revision(
                    self.scope.campaign_id, conn=conn
                )
                self.resolution_repository.transition(
                    record.id,
                    "committed",
                    scope=self.scope,
                    expected_state="prepared",
                    updates={
                        "resulting_revision": resulting_revision,
                        "operation_results_json": self._operation_results_json(result),
                        "committed_at": datetime.now(timezone.utc).isoformat(),
                    },
                    conn=conn,
                )
                self.resolution_repository.transition(
                    record.id,
                    "narration_pending",
                    scope=self.scope,
                    expected_state="committed",
                    conn=conn,
                )
            return self._resume_narration(
                self.resolution_repository.get(record.id, scope=self.scope),
                already_processed=False,
            )
        except Exception as exc:
            if (
                record.lifecycle_state == "planning"
                and "character-state changes must come from deterministic mechanics" in str(exc)
            ):
                with transaction("IMMEDIATE") as conn:
                    current = self.resolution_repository.get(
                        record.id, scope=self.scope, conn=conn
                    )
                    if current is not None and current.lifecycle_state == "planning":
                        self.resolution_repository.transition(
                            record.id,
                            "rejected",
                            scope=self.scope,
                            expected_state="planning",
                            expected_lease_token=lease_token,
                            updates={"last_error_code": "character_operation_not_allowed"},
                            conn=conn,
                        )
            rejection_code = None
            if isinstance(exc, DurableNativeTurnError):
                if "one or more proposed consequences failed validation" in str(exc):
                    rejection_code = "operation_validation_failed"
                elif "campaign state changed" in str(exc) or "campaign context changed" in str(exc):
                    rejection_code = "stale_context"
            if rejection_code is not None:
                with transaction("IMMEDIATE") as conn:
                    current = self.resolution_repository.get(
                        record.id, scope=self.scope, conn=conn
                    )
                    if current is not None and current.lifecycle_state == "prepared":
                        self.resolution_repository.transition(
                            record.id,
                            "rejected",
                            scope=self.scope,
                            expected_state="prepared",
                            updates={"last_error_code": rejection_code},
                            conn=conn,
                        )
            if isinstance(exc, DurableNativeTurnError):
                raise
            raise DurableNativeTurnError("native turn execution failed") from exc

    def _result_from_completed_record(
        self,
        record: TurnResolutionRecord,
        turn: TurnRecord,
        *,
        already_processed: bool,
    ) -> TurnResolutionResult:
        parsed = self.resolver.extractor.operation_parser.parse(
            record.proposal_json or '{"operations":[]}'
        )
        def unwrap(raw):
            return raw.operation if isinstance(raw, ReferencedOperation) else raw
        world_operations = tuple(
            unwrap(raw) for raw in parsed if isinstance(unwrap(raw), WorldOperation)
        )
        character_operations = tuple(
            unwrap(raw) for raw in parsed if isinstance(unwrap(raw), CharacterOperation)
        )
        stored_results = json.loads(record.operation_results_json or "[]")
        operation_results = tuple(
            OperationResult(
                status=OperationStatus(item["status"]),
                message=item.get("message", ""),
                operation=unwrap(parsed[index]) if index < len(parsed) else None,
            )
            for index, item in enumerate(stored_results)
        )
        return TurnResolutionResult(
            player_input=turn.player_input,
            narrative=turn.narrative,
            operations=world_operations,
            character_operations=character_operations,
            operation_results=operation_results,
            mechanics_result=self._mechanics_from_json(record.mechanics_json),
            already_processed=already_processed,
            persisted_operation_count=turn.operation_count,
            persisted_successful_operation_count=turn.successful_operation_count,
            persisted_failed_operation_count=turn.failed_operation_count,
            persisted_all_operations_succeeded=turn.all_operations_succeeded,
            persisted_world_changed=turn.world_changed,
        )

    def _resume_narration(
        self,
        record: TurnResolutionRecord,
        *,
        already_processed: bool,
    ):
        if record.lifecycle_state == "committed":
            with transaction("IMMEDIATE") as conn:
                record = self.resolution_repository.transition(
                    record.id,
                    "narration_pending",
                    scope=self.scope,
                    expected_state="committed",
                    conn=conn,
                )
        if record.lifecycle_state != "narration_pending":
            raise DurableNativeTurnError("resolution is not awaiting narration")

        with transaction("DEFERRED") as conn:
            context, recent = self._context_and_history(conn)
        mechanics_result = self._mechanics_from_json(record.mechanics_json)
        committed_resolution = json.dumps(
            {
                "context_revision": record.context_revision,
                "resulting_revision": record.resulting_revision,
                "operations": json.loads(
                    record.proposal_json or '{"operations":[]}'
                )["operations"],
                "operation_results": json.loads(
                    record.operation_results_json or "[]"
                ),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        narrative = self.resolver.generate_narrative(
            context,
            record.player_input,
            recent_turns=recent,
            mechanics_result=mechanics_result,
            committed_resolution=committed_resolution,
        )
        if not narrative:
            raise DurableNativeTurnError("DMService returned an empty narrative")

        with transaction("IMMEDIATE") as conn:
            turn = self.turn_repository.save_turn(
                TurnRecord(
                    session_id=record.session_id,
                    player_input=record.player_input,
                    narrative=narrative,
                    operation_count=len(
                        json.loads(record.operation_results_json or "[]")
                    ),
                    successful_operation_count=len(
                        json.loads(record.operation_results_json or "[]")
                    ),
                    failed_operation_count=0,
                    all_operations_succeeded=True,
                    world_changed=any(
                        item.get("changed", False)
                        for item in json.loads(record.operation_results_json or "[]")
                    ),
                ),
                scope=self.scope,
                conn=conn,
            )
            self.resolution_repository.transition(
                record.id,
                "completed",
                scope=self.scope,
                expected_state="narration_pending",
                updates={
                    "turn_id": turn.id,
                    "narrative": narrative,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
                conn=conn,
            )
        completed = self.resolution_repository.get(
            record.id, scope=self.scope
        )
        completed_turn = self.turn_repository.get_turn(
            completed.turn_id, scope=self.scope
        )
        return self._result_from_completed_record(
            completed, completed_turn, already_processed=already_processed
        )
