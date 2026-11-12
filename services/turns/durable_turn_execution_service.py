"""Durable request claiming and consequence-planning execution boundary."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta

from database import transaction
from models.campaign_scope import CampaignScope
from models.turn_resolution_record import TurnResolutionRecord
from models.turn_resolution_result import TurnResolutionResult
from observability.log_context import bind_resolution_context
from repositories.campaign_state_version_repository import (
    CampaignStateVersionRepository,
)
from repositories.turn_repository import TurnRepository
from repositories.turn_resolution_repository import TurnResolutionRepository
from services.llm_world import LLMExtractionError
from services.turns.durable_turn_errors import (
    DurableNativeTurnError,
    DurableTurnCommitError,
    DurableTurnErrorCode,
)
from services.turns.durable_turn_narration_service import DurableTurnNarrationService
from services.turns.durable_turn_preparation_mapper import (
    DurableTurnPreparation,
    DurableTurnPreparationMapper,
)
from services.turns.durable_turn_result_mapper import DurableTurnResultMapper
from services.turns.turn_resolution_codec import TurnResolutionCodec
from services.turns.turn_resolution_service import (
    TurnResolutionPlan,
    TurnResolutionService,
    TurnResolutionServiceError,
)

logger = logging.getLogger(__name__)


class DurableTurnExecutionService:
    """Own durable request claims, planning, challenge creation and commit hand-off.

    DurableNativeTurnService remains the public application façade. This
    collaborator owns the accepted -> planning -> awaiting_input/prepared ->
    committed path, including idempotency identity and lease fencing.
    """

    def __init__(
        self,
        *,
        scope: CampaignScope,
        resolver: TurnResolutionService,
        turn_repository: TurnRepository,
        resolution_repository: TurnResolutionRepository,
        revision_repository: CampaignStateVersionRepository,
        prepared_commit_service,
        narration_service: DurableTurnNarrationService,
        context_loader,
        turn_execution_lock=None,
        error_type=DurableNativeTurnError,
    ) -> None:
        self.scope = scope
        self.resolver = resolver
        self.turn_repository = turn_repository
        self.resolution_repository = resolution_repository
        self.revision_repository = revision_repository
        self.prepared_commit_service = prepared_commit_service
        self.narration_service = narration_service
        self.context_loader = context_loader
        self.turn_execution_lock = turn_execution_lock
        self.error_type = error_type

    def _serialize_operations(self, plan: TurnResolutionPlan) -> str:
        try:
            return TurnResolutionCodec.serialize_operations(plan)
        except ValueError as exc:
            raise DurableNativeTurnError(str(exc)) from exc

    @staticmethod
    def _mechanics_to_json(result) -> str | None:
        return TurnResolutionCodec.mechanics_to_json(result)

    @staticmethod
    def _mechanics_from_json(payload: str | None):
        return TurnResolutionCodec.mechanics_from_json(payload)


    def _plan_from_record(self, record: TurnResolutionRecord) -> TurnResolutionPlan:
        return TurnResolutionCodec.plan_from_record(
            record,
            self.resolver.extractor.operation_parser,
        )


    @staticmethod
    def _required_resolution_id(record: TurnResolutionRecord) -> int:
        if record.id is None:
            raise DurableNativeTurnError(
                "persisted turn resolution has no database identifier"
            )
        return record.id

    @staticmethod
    def _require_resolution_record(
        record: TurnResolutionRecord | None,
    ) -> TurnResolutionRecord:
        if record is None:
            raise DurableNativeTurnError(
                "turn resolution disappeared after a successful persistence operation"
            )
        return record

    @staticmethod
    def _manual_roll_result(record, pending):
        return DurableTurnResultMapper.manual_roll_result(record, pending)

    @staticmethod
    def _clarification_result(record, pending):
        return DurableTurnResultMapper.clarification_result(record, pending)


    @staticmethod
    def _fingerprint(player_input: str, session_id, dice_mode: str) -> str:
        raw = json.dumps(
            [player_input, session_id, dice_mode],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def play_turn(
        self, player_input: str, *, idempotency_key: str | None = None,
        dice_mode: str = "automatic",
    ):
        if dice_mode not in {"automatic", "manual"}:
            raise DurableNativeTurnError("dice_mode must be automatic or manual")
        if self.turn_execution_lock is None:
            return self._play_turn_locked(
                player_input, idempotency_key=idempotency_key, dice_mode=dice_mode
            )
        with self.turn_execution_lock.acquire():
            return self._play_turn_locked(
                player_input, idempotency_key=idempotency_key, dice_mode=dice_mode
            )

    def prepare_external_turn(
        self,
        player_input: str,
        *,
        external_turn_id: str,
        dice_mode: str = "automatic",
    ) -> DurableTurnPreparation:
        if not isinstance(external_turn_id, str) or not external_turn_id.strip():
            raise DurableNativeTurnError("external_turn_id must not be empty")
        external_turn_id = external_turn_id.strip()
        if dice_mode not in {"automatic", "manual"}:
            raise DurableNativeTurnError("dice_mode must be automatic or manual")
        if len(external_turn_id) > 500:
            raise DurableNativeTurnError("external_turn_id must not exceed 500 characters")

        def prepare():
            effective_dice_mode = dice_mode
            existing_resolution = self.resolution_repository.get_by_idempotency_key(
                "sillytavern", external_turn_id, scope=self.scope
            )
            if existing_resolution is not None:
                persisted_state = json.loads(existing_resolution.adjudication_json or "{}")
                persisted_dice_mode = persisted_state.get("dice_mode")
                if persisted_dice_mode in {"automatic", "manual"}:
                    effective_dice_mode = persisted_dice_mode
                elif isinstance(persisted_state.get("manual_roll"), dict):
                    effective_dice_mode = "manual"
            active_turn = self.turn_repository.get_active_by_external_turn_id(
                external_turn_id, scope=self.scope
            )
            if existing_resolution is None and active_turn is not None:
                normalized_input = (
                    player_input.strip() if isinstance(player_input, str) else ""
                )
                if active_turn.player_input != normalized_input:
                    raise DurableNativeTurnError(
                        "external turn identity was reused with different player input"
                    )
                raise DurableNativeTurnError(
                    "external turn has no durable resolution; use a new external_turn_id"
                )
            result = self._play_turn_locked(
                player_input,
                idempotency_key=external_turn_id,
                adapter_namespace="sillytavern",
                defer_narration=True,
                dice_mode=effective_dice_mode,
            )
            if isinstance(result, TurnResolutionResult) and result.pending_roll_id:
                record = self.resolution_repository.get_by_idempotency_key(
                    "sillytavern", external_turn_id, scope=self.scope
                )
                return DurableTurnPreparation(
                    resolution_id=record.id if record is not None else None,
                    lifecycle_state="awaiting_input",
                    player_input=result.player_input,
                    committed_resolution=json.dumps({"manual_roll_required": True}),
                    pending_roll_id=result.pending_roll_id,
                    pending_roll=result.pending_roll,
                )
            if isinstance(result, TurnResolutionResult):
                question = result.narrative
                record = self.resolution_repository.get_by_idempotency_key(
                    "sillytavern", external_turn_id, scope=self.scope
                )
                return DurableTurnPreparation(
                    resolution_id=record.id if record is not None else None,
                    lifecycle_state=(
                        record.lifecycle_state if record is not None else "awaiting_input"
                    ),
                    player_input=result.player_input,
                    committed_resolution=json.dumps(
                        {"clarification_required": question},
                        ensure_ascii=False,
                    ),
                    clarification_question=question,
                    pending_clarification_id=getattr(
                        result, "pending_clarification_id", None
                    ),
                )
            return result

        if self.turn_execution_lock is None:
            return prepare()
        with self.turn_execution_lock.acquire():
            return prepare()

    def _play_turn_locked(
        self,
        player_input: str,
        *,
        idempotency_key: str | None = None,
        adapter_namespace: str = "native",
        defer_narration: bool = False,
        dice_mode: str = "automatic",
    ):
        normalized = player_input.strip() if isinstance(player_input, str) else ""
        if not normalized:
            raise DurableNativeTurnError("player_input must not be empty")

        with transaction("DEFERRED") as conn:
            context, recent = self.context_loader(conn)
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
            normalized, session_id, dice_mode
        )
        fallback_identity = hashlib.sha256(
            f"{fingerprint}:{previous_turn_id}".encode()
        ).hexdigest()
        key = idempotency_key or "native-" + fallback_identity
        if not isinstance(key, str) or not key.strip() or len(key) > 500:
            raise DurableNativeTurnError("idempotency_key must contain 1-500 characters")

        with transaction("IMMEDIATE") as conn:
            record = self.resolution_repository.get_by_idempotency_key(
                adapter_namespace, key, scope=self.scope, conn=conn
            )
            if record is not None:
                fingerprint = self._fingerprint(
                    normalized, record.session_id, dice_mode
                )
                if record.request_fingerprint != fingerprint:
                    raise DurableNativeTurnError(
                        "idempotency key was already used for a different request"
                    )
                if record.lifecycle_state == "completed":
                    if defer_narration:
                        return DurableTurnPreparationMapper.from_record(record)
                    if record.turn_id is None:
                        raise DurableNativeTurnError(
                            "completed resolution has no transcript identifier"
                        )
                    turn = self.turn_repository.get_turn(
                        record.turn_id, scope=self.scope, conn=conn
                    )
                    if turn is None:
                        raise DurableNativeTurnError("completed resolution has no transcript")
                    return DurableTurnPreparationMapper.from_record(record) if defer_narration else self.narration_service.result_from_completed_record(record, turn, already_processed=True)
                if record.lifecycle_state == "awaiting_input":
                    pending = json.loads(record.adjudication_json or "{}")
                    if pending.get("manual_roll"):
                        return self._manual_roll_result(record, pending["manual_roll"])
                    clarification = pending.get("clarification")
                    if isinstance(clarification, dict):
                        return self._clarification_result(record, clarification)
                    question = pending.get(
                        "clarification_question",
                        "Necesito una aclaración antes de resolver esa acción.",
                    )
                    return TurnResolutionResult(player_input=record.player_input, narrative=question)
                if record.lifecycle_state in {
                    "committed",
                    "narration_pending",
                    "accepted",
                    "planning",
                    "prepared",
                }:
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
                        adapter_namespace=adapter_namespace,
                        idempotency_key=key,
                        request_fingerprint=fingerprint,
                    ),
                    scope=self.scope,
                    conn=conn,
                )

        if record.lifecycle_state in {"committed", "narration_pending"}:
            if defer_narration:
                return DurableTurnPreparationMapper.from_record(record)
            with bind_resolution_context(
                str(self._required_resolution_id(record))
            ):
                return self.narration_service.resume_narration(
                    record,
                    already_processed=True,
                )

        resume_prepared = record.lifecycle_state == "prepared"
        lease_token = None
        if not resume_prepared:
            lease_token = secrets.token_urlsafe(24)
            now = datetime.now(UTC)
            try:
                with transaction("IMMEDIATE") as conn:
                    record = self.resolution_repository.claim_for_planning(
                        self._required_resolution_id(record),
                        scope=self.scope,
                        lease_token=lease_token,
                        lease_expires_at=(now + timedelta(minutes=3)).isoformat(),
                        now=now.isoformat(),
                        conn=conn,
                    )
            except ValueError as exc:
                raise DurableNativeTurnError(
                    "turn resolution is already being planned; retry with the same identity"
                ) from exc

        try:
            if resume_prepared:
                if record.context_revision != revision:
                    with transaction("IMMEDIATE") as conn:
                        self.resolution_repository.transition(
                            self._required_resolution_id(record),
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
                with bind_resolution_context(
                    str(self._required_resolution_id(record))
                ):
                    plan = self.resolver.prepare_turn(
                        context,
                        normalized,
                        manual_mode=(dice_mode == "manual"),
                    )
                if plan.awaiting_manual_roll:
                    pending = self.build_manual_roll_request(record, plan.mechanics_decision, context, revision)
                    with transaction("IMMEDIATE") as conn:
                        self.resolution_repository.transition(
                            self._required_resolution_id(record), "awaiting_input", scope=self.scope,
                            expected_state="planning", expected_lease_token=lease_token,
                            updates={
                                "context_revision": revision,
                                "adjudication_json": json.dumps({"manual_roll": pending, "dice_mode": dice_mode}, separators=(",", ":"), sort_keys=True),
                                "lease_token": None, "lease_expires_at": None,
                            }, conn=conn,
                        )
                    saved = self._require_resolution_record(
                        self.resolution_repository.get(
                            self._required_resolution_id(record), scope=self.scope
                        )
                    )
                    return self._manual_roll_result(saved, pending)
                if plan.clarification_question is not None:
                    pending = {
                        "challenge_id": secrets.token_urlsafe(24),
                        "context_revision": revision,
                        "question": plan.clarification_question,
                        "history": [],
                    }
                    with transaction("IMMEDIATE") as conn:
                        self.resolution_repository.transition(
                            self._required_resolution_id(record),
                            "awaiting_input",
                            scope=self.scope,
                            expected_state="planning",
                            expected_lease_token=lease_token,
                            updates={
                                "context_revision": revision,
                                "adjudication_json": json.dumps(
                                    {"clarification": pending, "dice_mode": dice_mode},
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                    sort_keys=True,
                                ),
                                "lease_token": None,
                                "lease_expires_at": None,
                            },
                            conn=conn,
                        )
                    saved = self._require_resolution_record(
                        self.resolution_repository.get(
                            self._required_resolution_id(record), scope=self.scope
                        )
                    )
                    return self._clarification_result(saved, pending)
                proposal_json = self._serialize_operations(plan)
                mechanics_json = self._mechanics_to_json(plan.mechanics_result)

                with transaction("IMMEDIATE") as conn:
                    self.resolution_repository.transition(
                        self._required_resolution_id(record),
                        "prepared",
                        scope=self.scope,
                        expected_state="planning",
                        expected_lease_token=lease_token,
                        updates={
                            "context_revision": revision,
                            "proposal_json": proposal_json,
                            "adjudication_json": json.dumps(
                                {
                                    "decision": plan.mechanics_decision.decision.value,
                                    "dice_mode": dice_mode,
                                }
                                if plan.mechanics_decision else {"dice_mode": dice_mode},
                                separators=(",", ":"),
                            ),
                            "mechanics_json": mechanics_json,
                            "lease_token": None,
                            "lease_expires_at": None,
                        },
                        conn=conn,
                    )

            self.prepared_commit_service.commit_prepared_plan(
                record,
                plan,
                context=context,
                recent=recent,
                revision=revision,
                revision_error_message=(
                    "campaign state changed while the turn was being prepared; retry"
                ),
                context_error_message=(
                    "campaign context changed while the turn was being prepared; retry"
                ),
            )
            committed_record = self._require_resolution_record(
                self.resolution_repository.get(
                    self._required_resolution_id(record), scope=self.scope
                )
            )
            if defer_narration:
                return DurableTurnPreparationMapper.from_record(committed_record)
            with bind_resolution_context(
                str(self._required_resolution_id(committed_record))
            ):
                return self.narration_service.resume_narration(
                    committed_record,
                    already_processed=False,
                )
        except Exception as exc:
            if (
                record.lifecycle_state == "planning"
                and isinstance(exc, TurnResolutionServiceError)
                and exc.code == DurableTurnErrorCode.CHARACTER_OPERATION_NOT_ALLOWED.value
            ):
                with transaction("IMMEDIATE") as conn:
                    current = self.resolution_repository.get(
                        self._required_resolution_id(record), scope=self.scope, conn=conn
                    )
                    if current is not None and current.lifecycle_state == "planning":
                        self.resolution_repository.transition(
                            self._required_resolution_id(record),
                            "rejected",
                            scope=self.scope,
                            expected_state="planning",
                            expected_lease_token=lease_token,
                            updates={"last_error_code": "character_operation_not_allowed"},
                            conn=conn,
                        )
            cause = exc
            invalid_llm_proposal = False
            while cause is not None:
                if isinstance(cause, LLMExtractionError):
                    invalid_llm_proposal = True
                    break
                cause = cause.__cause__

            # A failure before the prepared/commit boundary must not strand
            # the idempotent request in planning until its lease expires.
            # Requeue only while this attempt still owns the lease; the token
            # check fences off stale workers and preserves committed work.
            with transaction("IMMEDIATE") as conn:
                current = self.resolution_repository.get(
                    self._required_resolution_id(record), scope=self.scope, conn=conn
                )
                if (
                    current is not None
                    and current.lifecycle_state == "planning"
                    and current.lease_token == lease_token
                ):
                    self.resolution_repository.transition(
                        self._required_resolution_id(record),
                        "accepted",
                        scope=self.scope,
                        expected_state="planning",
                        expected_lease_token=lease_token,
                        updates={
                            "lease_token": None,
                            "lease_expires_at": None,
                            "last_error_code": (
                                "invalid_llm_proposal"
                                if invalid_llm_proposal
                                else "planning_failed"
                            ),
                        },
                        conn=conn,
                    )

            rejection_code = (
                exc.code
                if isinstance(exc, DurableTurnCommitError)
                else (
                    exc.code
                    if isinstance(exc, DurableNativeTurnError)
                    and exc.code == DurableTurnErrorCode.STALE_CONTEXT.value
                    else None
                )
            )
            if rejection_code is not None:
                with transaction("IMMEDIATE") as conn:
                    current = self.resolution_repository.get(
                        self._required_resolution_id(record), scope=self.scope, conn=conn
                    )
                    if current is not None and current.lifecycle_state == "prepared":
                        self.resolution_repository.transition(
                            self._required_resolution_id(record),
                            "rejected",
                            scope=self.scope,
                            expected_state="prepared",
                            updates={"last_error_code": rejection_code},
                            conn=conn,
                        )
            if isinstance(exc, DurableNativeTurnError):
                raise
            logger.exception(
                "turn.execution.failed",
                extra={
                    "campaign_id": str(self.scope.campaign_id),
                    "resolution_id": str(self._required_resolution_id(record)),
                    "adapter_namespace": adapter_namespace,
                    "lifecycle_state": record.lifecycle_state,
                    "dice_mode": dice_mode,
                    "error_type": type(exc).__name__,
                    "error_code": (
                        exc.code
                        if isinstance(exc, DurableNativeTurnError)
                        else None
                    ),
                },
            )
            raise DurableNativeTurnError(
                "native turn execution failed",
                code=DurableTurnErrorCode.EXECUTION_FAILED,
            ) from exc


    def build_manual_roll_request(self, record, decision, context, revision):
        if decision is None or context.active_character is None:
            raise DurableNativeTurnError("manual roll requires a character and mechanics decision")
        from models.mechanics import MechanicsDecisionType
        from rules_engine.dnd5e_2014.character_checks import (
            ability_check_modifier_for_character,
        )
        from rules_engine.dnd5e_2014.core.skills import ability_for_skill
        ability = decision.ability or (ability_for_skill(decision.skill) if decision.skill else None)
        if ability is None:
            raise DurableNativeTurnError("manual roll has no governing ability")
        character = context.active_character
        proficient = (decision.decision is MechanicsDecisionType.SKILL_CHECK and decision.skill in character.skill_proficiencies) or (decision.decision is MechanicsDecisionType.SAVING_THROW and ability in character.saving_throw_proficiencies)
        expertise = decision.decision is MechanicsDecisionType.SKILL_CHECK and decision.skill in character.skill_expertise
        modifier = ability_check_modifier_for_character(character=character, ability=ability, proficient=proficient, expertise=expertise, situational_modifier=decision.situational_modifier)
        return {
            "challenge_id": secrets.token_urlsafe(24), "context_revision": revision,
            "count": 1 if decision.advantage == decision.disadvantage else 2,
            "dice": "d20", "kind": decision.decision.value,
            "skill": decision.skill.value if decision.skill else None,
            "ability": ability.value, "dc": decision.dc, "modifier": modifier,
            "advantage": decision.advantage, "disadvantage": decision.disadvantage,
            "decision": {"decision": decision.decision.value, "skill": decision.skill.value if decision.skill else None,
                "ability": decision.ability.value if decision.ability else None, "dc": decision.dc,
                "advantage": decision.advantage, "disadvantage": decision.disadvantage,
                "situational_modifier": decision.situational_modifier, "reason": decision.reason, "question": decision.question},
        }
