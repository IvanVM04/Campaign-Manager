from __future__ import annotations  # noqa: I001

import hashlib
import json
import logging
import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from database import transaction
from models.campaign_scope import CampaignScope
from models.turn_record import TurnRecord
from models.turn_resolution_record import TurnResolutionRecord
from models.turn_resolution_result import TurnResolutionResult
from repositories.campaign_state_version_repository import (
    CampaignStateVersionRepository,
)
from repositories.turn_repository import TurnRepository
from repositories.turn_resolution_repository import TurnResolutionRepository
from services.durable_turn_preparation_mapper import (
    DurableTurnPreparation,
    DurableTurnPreparationMapper,
)
from services.durable_turn_result_mapper import DurableTurnResultMapper
from services.durable_turn_challenge_state_service import (
    DurableTurnChallengeStateService,
)
from services.llm_world_extractor import LLMExtractionError
from services.turn_resolution_codec import TurnResolutionCodec
from services.turn_resolution_service import (
    TurnResolutionPlan,
    TurnResolutionService,
)
from services.world_service import WorldService


logger = logging.getLogger(__name__)


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
        self.challenge_state_service = DurableTurnChallengeStateService(
            scope=scope,
            turn_repository=self.turn_repository,
            resolution_repository=self.resolution_repository,
            error_type=DurableNativeTurnError,
        )

    @staticmethod
    def _json_default(value):
        return TurnResolutionCodec.json_default(value)

    @classmethod
    def _operation_value(cls, value):
        return TurnResolutionCodec.operation_value(value)

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

    @staticmethod
    def _operation_results_json(result: TurnResolutionResult) -> str:
        return TurnResolutionCodec.operation_results_json(result)

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
        return TurnResolutionCodec.plan_from_record(
            record,
            self.resolver.extractor.operation_parser,
        )

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
                return DurableTurnPreparation(
                    resolution_id=None,
                    lifecycle_state="legacy_replay",
                    player_input=active_turn.player_input,
                    committed_resolution=json.dumps(
                        {
                            "legacy_replay": True,
                            "message": (
                                "This turn predates durable resolution. "
                                "Preserve its existing world effects; narration regeneration "
                                "must not create new consequences."
                            ),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    legacy_replay=True,
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

    def get_external_clarification_state(
        self,
        external_turn_id: str,
    ) -> dict:
        return self.challenge_state_service.get_external_clarification_state(
            external_turn_id
        )

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
                        return self._preparation_from_record(record)
                    turn = self.turn_repository.get_turn(
                        record.turn_id, scope=self.scope, conn=conn
                    )
                    if turn is None:
                        raise DurableNativeTurnError("completed resolution has no transcript")
                    return self._preparation_from_record(record) if defer_narration else self._result_from_completed_record(record, turn, already_processed=True)
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
                return self._preparation_from_record(record)
            return self._resume_narration(record, already_processed=True)

        resume_prepared = record.lifecycle_state == "prepared"
        lease_token = None
        if not resume_prepared:
            lease_token = secrets.token_urlsafe(24)
            now = datetime.now(UTC)
            try:
                with transaction("IMMEDIATE") as conn:
                    record = self.resolution_repository.claim_for_planning(
                        record.id,
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
                    context, normalized, recent_turns=recent,
                    manual_mode=(dice_mode == "manual"),
                    proposal_from_intent=True,
                )
                if plan.awaiting_manual_roll:
                    pending = self._build_manual_roll_request(record, plan.mechanics_decision, context, revision)
                    with transaction("IMMEDIATE") as conn:
                        self.resolution_repository.transition(
                            record.id, "awaiting_input", scope=self.scope,
                            expected_state="planning", expected_lease_token=lease_token,
                            updates={
                                "context_revision": revision,
                                "adjudication_json": json.dumps({"manual_roll": pending, "dice_mode": dice_mode}, separators=(",", ":"), sort_keys=True),
                                "lease_token": None, "lease_expires_at": None,
                            }, conn=conn,
                        )
                    saved = self.resolution_repository.get(record.id, scope=self.scope)
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
                            record.id,
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
                    saved = self.resolution_repository.get(record.id, scope=self.scope)
                    return self._clarification_result(saved, pending)
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
                        "committed_at": datetime.now(UTC).isoformat(),
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
            committed_record = self.resolution_repository.get(
                record.id, scope=self.scope
            )
            if defer_narration:
                return self._preparation_from_record(committed_record)
            return self._resume_narration(
                committed_record,
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
                    record.id, scope=self.scope, conn=conn
                )
                if (
                    current is not None
                    and current.lifecycle_state == "planning"
                    and current.lease_token == lease_token
                ):
                    self.resolution_repository.transition(
                        record.id,
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
            logger.exception(
                "Unexpected native turn execution failure "
                "(campaign_id=%s, resolution_id=%s, adapter_namespace=%s, "
                "lifecycle_state=%s, dice_mode=%s)",
                self.scope.campaign_id,
                record.id,
                adapter_namespace,
                record.lifecycle_state,
                dice_mode,
            )
            raise DurableNativeTurnError("native turn execution failed") from exc

    @staticmethod
    def _manual_roll_result(record, pending):
        return DurableTurnResultMapper.manual_roll_result(record, pending)

    @staticmethod
    def _clarification_result(record, pending):
        return DurableTurnResultMapper.clarification_result(record, pending)

    def submit_clarification(
        self,
        pending_clarification_id: str,
        answer: str,
        *,
        adapter_namespace: str = "native",
        defer_narration: bool = False,
        answer_external_turn_id: str | None = None,
    ):
        if answer_external_turn_id is not None and (
            not isinstance(answer_external_turn_id, str)
            or not answer_external_turn_id.strip()
            or len(answer_external_turn_id.strip()) > 500
        ):
            raise DurableNativeTurnError(
                "answer_external_turn_id must contain 1-500 characters"
            )
        if answer_external_turn_id is not None:
            answer_external_turn_id = answer_external_turn_id.strip()
        if (
            not isinstance(pending_clarification_id, str)
            or ":" not in pending_clarification_id
        ):
            raise DurableNativeTurnError("pending_clarification_id is invalid")
        if not isinstance(answer, str) or not answer.strip():
            raise DurableNativeTurnError("clarification answer must not be empty")
        answer = answer.strip()
        if len(answer) > 5000:
            raise DurableNativeTurnError("clarification answer must not exceed 5000 characters")
        raw_id, challenge_id = pending_clarification_id.split(":", 1)
        if not raw_id.isdigit() or not challenge_id:
            raise DurableNativeTurnError("pending_clarification_id is invalid")

        def submit():
            record = self.resolution_repository.get(int(raw_id), scope=self.scope)
            if record is None:
                raise DurableNativeTurnError("clarification request was not found")
            if record.adapter_namespace != adapter_namespace:
                raise DurableNativeTurnError(
                    "clarification challenge belongs to a different adapter"
                )
            pending_state = json.loads(record.adjudication_json or "{}")
            if (
                secrets.compare_digest(
                    str(pending_state.get("last_challenge_id", "")),
                    challenge_id,
                )
                and secrets.compare_digest(
                    str(pending_state.get("last_answer", "")),
                    answer,
                )
                and (
                    answer_external_turn_id is None
                    or secrets.compare_digest(
                        str(pending_state.get("last_answer_external_turn_id", "")),
                        answer_external_turn_id,
                    )
                )
            ):
                if record.lifecycle_state == "awaiting_input":
                    current_pending = pending_state.get("clarification")
                    if isinstance(current_pending, dict):
                        return (
                            self._preparation_from_record(record)
                            if defer_narration
                            else self._clarification_result(record, current_pending)
                        )
                if record.lifecycle_state == "prepared":
                    return self._resume_prepared_clarification(
                        record, defer_narration=defer_narration
                    )
                if record.lifecycle_state in {"committed", "narration_pending"}:
                    return (
                        self._preparation_from_record(record)
                        if defer_narration
                        else self._resume_narration(record, already_processed=True)
                    )
                if record.lifecycle_state == "completed" and defer_narration:
                    return self._preparation_from_record(record)
                if record.lifecycle_state == "completed":
                    turn = self.turn_repository.get_turn(
                        record.turn_id, scope=self.scope
                    )
                    if turn is None:
                        raise DurableNativeTurnError(
                            "completed clarification has no transcript"
                        )
                    return self._result_from_completed_record(
                        record, turn, already_processed=True
                    )
            if record.lifecycle_state not in {"awaiting_input", "planning"}:
                raise DurableNativeTurnError("clarification request is no longer pending")
            pending = pending_state.get("clarification")
            if not isinstance(pending, dict) or not secrets.compare_digest(
                str(pending.get("challenge_id", "")), challenge_id
            ):
                raise DurableNativeTurnError("clarification challenge is invalid or expired")

            token = secrets.token_urlsafe(24)
            now = datetime.now(UTC)
            try:
                with transaction("IMMEDIATE") as conn:
                    record = self.resolution_repository.claim_for_planning(
                        record.id,
                        scope=self.scope,
                        lease_token=token,
                        lease_expires_at=(now + timedelta(minutes=3)).isoformat(),
                        now=now.isoformat(),
                        conn=conn,
                    )
            except ValueError as exc:
                raise DurableNativeTurnError(
                    "clarification is already being processed; retry"
                ) from exc

            try:
                with transaction("DEFERRED") as conn:
                    context, recent = self._context_and_history(conn)
                    revision = self.revision_repository.get_revision(
                        self.scope.campaign_id, conn=conn
                    )
                if (
                    revision != record.context_revision
                    or revision != pending.get("context_revision")
                ):
                    with transaction("IMMEDIATE") as conn:
                        self.resolution_repository.transition(
                            record.id,
                            "rejected",
                            scope=self.scope,
                            expected_state="planning",
                            expected_lease_token=token,
                            updates={"last_error_code": "stale_clarification"},
                            conn=conn,
                        )
                    raise DurableNativeTurnError(
                        "campaign state changed while waiting for clarification"
                    )

                history = list(pending.get("history", []))
                history.append({
                    "question": pending["question"],
                    "answer": answer,
                })
                clarified_input = record.player_input + "".join(
                    "\n\nAclaración del DM: " + item["question"]
                    + "\nRespuesta del jugador: " + item["answer"]
                    for item in history
                )
                plan = self.resolver.prepare_turn(
                    context,
                    clarified_input,
                    recent_turns=recent,
                    manual_mode=(pending_state.get("dice_mode") == "manual"),
                    proposal_from_intent=True,
                )
                if plan.awaiting_manual_roll:
                    manual_pending = self._build_manual_roll_request(
                        record, plan.mechanics_decision, context, revision
                    )
                    with transaction("IMMEDIATE") as conn:
                        self.resolution_repository.transition(
                            record.id, "awaiting_input", scope=self.scope,
                            expected_state="planning", expected_lease_token=token,
                            updates={
                                "context_revision": revision,
                                "adjudication_json": json.dumps({
                                    "manual_roll": manual_pending,
                                    "dice_mode": "manual",
                                    "clarification_history": history,
                                    "last_challenge_id": challenge_id,
                                    "last_answer": answer,
                                    "last_answer_external_turn_id": answer_external_turn_id,
                                }, separators=(",", ":"), sort_keys=True),
                                "lease_token": None, "lease_expires_at": None,
                            }, conn=conn,
                        )
                    saved = self.resolution_repository.get(record.id, scope=self.scope)
                    return self._manual_roll_result(saved, manual_pending)
                if plan.clarification_question is not None:
                    next_pending = {
                        "challenge_id": secrets.token_urlsafe(24),
                        "context_revision": revision,
                        "question": plan.clarification_question,
                        "history": history,
                    }
                    with transaction("IMMEDIATE") as conn:
                        self.resolution_repository.transition(
                            record.id,
                            "awaiting_input",
                            scope=self.scope,
                            expected_state="planning",
                            expected_lease_token=token,
                            updates={
                                "context_revision": revision,
                                "adjudication_json": json.dumps(
                                    {
                                        "clarification": next_pending,
                                        "dice_mode": pending_state.get("dice_mode", "automatic"),
                                        "clarification_history": history,
                                        "last_challenge_id": challenge_id,
                                        "last_answer": answer,
                                        "last_answer_external_turn_id": (
                                            answer_external_turn_id
                                        ),
                                    },
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                    sort_keys=True,
                                ),
                                "lease_token": None,
                                "lease_expires_at": None,
                            },
                            conn=conn,
                        )
                    saved = self.resolution_repository.get(record.id, scope=self.scope)
                    return (
                        self._preparation_from_record(saved)
                        if defer_narration
                        else self._clarification_result(saved, next_pending)
                    )

                with transaction("IMMEDIATE") as conn:
                    self.resolution_repository.transition(
                        record.id,
                        "prepared",
                        scope=self.scope,
                        expected_state="planning",
                        expected_lease_token=token,
                        updates={
                            "context_revision": revision,
                            "proposal_json": self._serialize_operations(plan),
                            "adjudication_json": json.dumps(
                                {
                                    "clarification_history": history,
                                    "dice_mode": pending_state.get("dice_mode", "automatic"),
                                    "resolved_player_input": clarified_input,
                                    "last_challenge_id": challenge_id,
                                    "last_answer": answer,
                                    "last_answer_external_turn_id": (
                                        answer_external_turn_id
                                    ),
                                    "decision": (
                                        plan.mechanics_decision.decision.value
                                        if plan.mechanics_decision else None
                                    ),
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                                sort_keys=True,
                            ),
                            "mechanics_json": self._mechanics_to_json(
                                plan.mechanics_result
                            ),
                            "lease_token": None,
                            "lease_expires_at": None,
                        },
                        conn=conn,
                    )

                with transaction("IMMEDIATE") as conn:
                    current_revision = self.revision_repository.get_revision(
                        self.scope.campaign_id, conn=conn
                    )
                    current_context, current_recent = self._context_and_history(conn)
                    if (
                        current_revision != revision
                        or current_context != context
                        or current_recent != recent
                    ):
                        raise DurableNativeTurnError(
                            "campaign context changed while clarification was being resolved"
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
                            "committed_at": datetime.now(UTC).isoformat(),
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
                saved = self.resolution_repository.get(record.id, scope=self.scope)
                return (
                    self._preparation_from_record(saved)
                    if defer_narration
                    else self._resume_narration(saved, already_processed=False)
                )
            except Exception as exc:
                current = self.resolution_repository.get(record.id, scope=self.scope)
                if current is not None and current.lifecycle_state == "prepared":
                    with transaction("IMMEDIATE") as conn:
                        self.resolution_repository.transition(
                            record.id,
                            "rejected",
                            scope=self.scope,
                            expected_state="prepared",
                            updates={"last_error_code": "clarification_resolution_failed"},
                            conn=conn,
                        )
                if isinstance(exc, DurableNativeTurnError):
                    raise
                raise DurableNativeTurnError(
                    "clarification resolution failed"
                ) from exc

        if self.turn_execution_lock is None:
            return submit()
        with self.turn_execution_lock.acquire():
            return submit()

    def _resume_prepared_clarification(
        self,
        record: TurnResolutionRecord,
        *,
        defer_narration: bool,
    ):
        with transaction("DEFERRED") as conn:
            context, recent = self._context_and_history(conn)
            revision = self.revision_repository.get_revision(
                self.scope.campaign_id, conn=conn
            )
        if revision != record.context_revision:
            with transaction("IMMEDIATE") as conn:
                self.resolution_repository.transition(
                    record.id,
                    "rejected",
                    scope=self.scope,
                    expected_state="prepared",
                    updates={"last_error_code": "stale_clarification"},
                    conn=conn,
                )
            raise DurableNativeTurnError(
                "campaign state changed while recovering clarification"
            )

        plan = self._plan_from_record(record)
        try:
            with transaction("IMMEDIATE") as conn:
                current_context, current_recent = self._context_and_history(conn)
                current_revision = self.revision_repository.get_revision(
                    self.scope.campaign_id, conn=conn
                )
                if (
                    current_revision != revision
                    or current_context != context
                    or current_recent != recent
                ):
                    raise DurableNativeTurnError(
                        "campaign context changed while recovering clarification"
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
                        "committed_at": datetime.now(UTC).isoformat(),
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
        except Exception as exc:
            current = self.resolution_repository.get(record.id, scope=self.scope)
            if current is not None and current.lifecycle_state == "prepared":
                with transaction("IMMEDIATE") as conn:
                    self.resolution_repository.transition(
                        record.id,
                        "rejected",
                        scope=self.scope,
                        expected_state="prepared",
                        updates={"last_error_code": "clarification_recovery_failed"},
                        conn=conn,
                    )
            if isinstance(exc, DurableNativeTurnError):
                raise
            raise DurableNativeTurnError(
                "prepared clarification recovery failed"
            ) from exc

        saved = self.resolution_repository.get(record.id, scope=self.scope)
        return (
            self._preparation_from_record(saved)
            if defer_narration
            else self._resume_narration(saved, already_processed=True)
        )

    def _build_manual_roll_request(self, record, decision, context, revision):
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

    def get_external_manual_roll_state(self, external_turn_id: str) -> dict:
        return self.challenge_state_service.get_external_manual_roll_state(
            external_turn_id
        )

    def submit_manual_roll(
        self, pending_roll_id: str, rolls: tuple[int, ...], *,
        adapter_namespace: str | None = None,
        defer_narration: bool = False,
        answer_external_turn_id: str | None = None,
    ):
        if answer_external_turn_id is not None and (
            not isinstance(answer_external_turn_id, str)
            or not answer_external_turn_id.strip()
            or len(answer_external_turn_id.strip()) > 500
        ):
            raise DurableNativeTurnError("answer_external_turn_id must contain 1-500 characters")
        if answer_external_turn_id is not None:
            answer_external_turn_id = answer_external_turn_id.strip()
        if not isinstance(pending_roll_id, str) or ":" not in pending_roll_id:
            raise DurableNativeTurnError("pending_roll_id is invalid")
        if not isinstance(rolls, tuple) or not rolls or len(rolls) > 2 or any(isinstance(v, bool) or not isinstance(v, int) or v < 1 or v > 20 for v in rolls):
            raise DurableNativeTurnError("manual d20 results must contain one or two integers from 1 to 20")
        raw_id, challenge_id = pending_roll_id.split(":", 1)
        if not raw_id.isdigit() or not challenge_id:
            raise DurableNativeTurnError("pending_roll_id is invalid")
        def submit():
            record = self.resolution_repository.get(int(raw_id), scope=self.scope)
            if record is None:
                raise DurableNativeTurnError("manual roll request not found")
            if adapter_namespace is not None and record.adapter_namespace != adapter_namespace:
                raise DurableNativeTurnError("manual roll challenge belongs to a different adapter")
            state = json.loads(record.adjudication_json or "{}")
            pending = state.get("manual_roll")
            if not pending or not secrets.compare_digest(pending.get("challenge_id", ""), challenge_id):
                raise DurableNativeTurnError("manual roll challenge is invalid or stale")
            accepted = pending.get("submitted_rolls")
            if accepted is not None:
                if list(rolls) != accepted:
                    raise DurableNativeTurnError("manual roll challenge was already submitted with different results")
                accepted_external_turn_id = pending.get("submitted_external_turn_id")
                if (
                    accepted_external_turn_id is not None
                    and answer_external_turn_id is not None
                    and not secrets.compare_digest(str(accepted_external_turn_id), answer_external_turn_id)
                ):
                    raise DurableNativeTurnError(
                        "manual roll challenge was already submitted by a different chat message"
                    )
                if record.lifecycle_state in {"narration_pending", "committed"}:
                    return self._preparation_from_record(record) if defer_narration else self._resume_narration(record, already_processed=True)
                if record.lifecycle_state == "completed":
                    turn = self.turn_repository.get_turn(record.turn_id, scope=self.scope)
                    return self._result_from_completed_record(record, turn, already_processed=True)
                if record.lifecycle_state == "prepared":
                    with transaction("DEFERRED") as conn:
                        context, recent = self._context_and_history(conn)
                        revision = self.revision_repository.get_revision(self.scope.campaign_id, conn=conn)
                    if revision != record.context_revision:
                        raise DurableNativeTurnError("prepared manual roll became stale before commit")
                    plan = self._plan_from_record(record)
                    with transaction("IMMEDIATE") as conn:
                        current_context, current_recent = self._context_and_history(conn)
                        current_revision = self.revision_repository.get_revision(self.scope.campaign_id, conn=conn)
                        if current_revision != revision or current_context != context or current_recent != recent:
                            raise DurableNativeTurnError("campaign context changed while recovering the manual roll")
                        result = self.resolver.apply_plan(current_context, plan, conn=conn)
                        if not result.all_operations_succeeded:
                            raise DurableNativeTurnError("one or more proposed consequences failed validation")
                        resulting_revision = self.revision_repository.get_revision(self.scope.campaign_id, conn=conn)
                        self.resolution_repository.transition(record.id, "committed", scope=self.scope, expected_state="prepared", updates={"resulting_revision": resulting_revision, "operation_results_json": self._operation_results_json(result), "committed_at": datetime.now(UTC).isoformat()}, conn=conn)
                        self.resolution_repository.transition(record.id, "narration_pending", scope=self.scope, expected_state="committed", conn=conn)
                    saved = self.resolution_repository.get(record.id, scope=self.scope)
                    return self._preparation_from_record(saved) if defer_narration else self._resume_narration(saved, already_processed=True)
            if record.lifecycle_state not in {"awaiting_input", "planning"}:
                raise DurableNativeTurnError("manual roll challenge is no longer pending")
            with transaction("DEFERRED") as conn:
                context, recent = self._context_and_history(conn)
                revision = self.revision_repository.get_revision(self.scope.campaign_id, conn=conn)
            if revision != pending.get("context_revision") or revision != record.context_revision:
                expected_state = record.lifecycle_state
                lease_token = None
                if expected_state == "planning":
                    lease_token = secrets.token_urlsafe(24)
                    try:
                        with transaction("IMMEDIATE") as conn:
                            self.resolution_repository.claim_for_planning(
                                record.id, scope=self.scope, lease_token=lease_token,
                                lease_expires_at=(datetime.now(UTC) + timedelta(minutes=3)).isoformat(),
                                now=datetime.now(UTC).isoformat(), conn=conn,
                            )
                    except ValueError as exc:
                        raise DurableNativeTurnError("manual roll is still being submitted; retry") from exc
                with transaction("IMMEDIATE") as conn:
                    self.resolution_repository.transition(
                        record.id, "rejected", scope=self.scope,
                        expected_state=expected_state,
                        expected_lease_token=lease_token,
                        updates={"last_error_code": "stale_manual_roll"}, conn=conn,
                    )
                raise DurableNativeTurnError("campaign state changed while waiting for the manual roll")
            if len(rolls) != pending["count"]:
                raise DurableNativeTurnError("manual roll has an invalid number of dice")
            token = secrets.token_urlsafe(24)
            try:
                with transaction("IMMEDIATE") as conn:
                    record = self.resolution_repository.claim_for_planning(record.id, scope=self.scope, lease_token=token, lease_expires_at=(datetime.now(UTC) + timedelta(minutes=3)).isoformat(), now=datetime.now(UTC).isoformat(), conn=conn)
            except ValueError as exc:
                raise DurableNativeTurnError("manual roll is already being submitted; retry") from exc
            from models.mechanics import MechanicsDecision, MechanicsDecisionType
            from rules_engine.dnd5e_2014.core.abilities import Ability
            from rules_engine.dnd5e_2014.core.skills import Skill
            d = pending["decision"]
            decision = MechanicsDecision(decision=MechanicsDecisionType(d["decision"]), skill=Skill(d["skill"]) if d["skill"] else None, ability=Ability(d["ability"]) if d["ability"] else None, dc=d["dc"], advantage=d["advantage"], disadvantage=d["disadvantage"], situational_modifier=d["situational_modifier"], reason=d["reason"], question=d["question"])
            plan = self.resolver.prepare_turn(context, record.player_input, recent_turns=recent, manual_mode=True, manual_rolls=rolls, decision_override=decision, proposal_from_intent=True)
            if plan.awaiting_manual_roll or plan.clarification_question:
                raise DurableNativeTurnError("manual roll could not be resolved")
            pending["submitted_rolls"] = list(rolls)
            if answer_external_turn_id is not None:
                pending["submitted_external_turn_id"] = answer_external_turn_id
            with transaction("IMMEDIATE") as conn:
                self.resolution_repository.transition(record.id, "prepared", scope=self.scope, expected_state="planning", expected_lease_token=token, updates={"proposal_json": self._serialize_operations(plan), "mechanics_json": self._mechanics_to_json(plan.mechanics_result), "adjudication_json": json.dumps({"manual_roll": pending}, separators=(",", ":"), sort_keys=True), "lease_token": None, "lease_expires_at": None}, conn=conn)
            with transaction("IMMEDIATE") as conn:
                current_revision = self.revision_repository.get_revision(self.scope.campaign_id, conn=conn)
                current_context, current_recent = self._context_and_history(conn)
                if current_revision != revision or current_context != context or current_recent != recent:
                    raise DurableNativeTurnError("campaign context changed while resolving the manual roll")
                result = self.resolver.apply_plan(current_context, plan, conn=conn)
                if not result.all_operations_succeeded:
                    raise DurableNativeTurnError("one or more proposed consequences failed validation")
                resulting_revision = self.revision_repository.get_revision(self.scope.campaign_id, conn=conn)
                self.resolution_repository.transition(record.id, "committed", scope=self.scope, expected_state="prepared", updates={"resulting_revision": resulting_revision, "operation_results_json": self._operation_results_json(result), "committed_at": datetime.now(UTC).isoformat()}, conn=conn)
                self.resolution_repository.transition(record.id, "narration_pending", scope=self.scope, expected_state="committed", conn=conn)
            saved = self.resolution_repository.get(record.id, scope=self.scope)
            return self._preparation_from_record(saved) if defer_narration else self._resume_narration(saved, already_processed=False)
        if self.turn_execution_lock is None:
            return submit()
        with self.turn_execution_lock.acquire():
            return submit()
    @staticmethod
    def _committed_resolution_json(record: TurnResolutionRecord) -> str:
        return DurableTurnPreparationMapper.committed_resolution_json(record)

    def _preparation_from_record(
        self,
        record: TurnResolutionRecord,
    ) -> DurableTurnPreparation:
        return DurableTurnPreparationMapper.from_record(record)

    def complete_external_narration(
        self,
        *,
        external_turn_id: str,
        player_input: str,
        narrative: str,
        turn_version: int,
    ) -> TurnResolutionResult:
        if not isinstance(external_turn_id, str) or not external_turn_id.strip():
            raise DurableNativeTurnError("external_turn_id must not be empty")
        if not isinstance(player_input, str) or not player_input.strip():
            raise DurableNativeTurnError("player_input must not be empty")
        if not isinstance(narrative, str) or not narrative.strip():
            raise DurableNativeTurnError("narrative must not be empty")
        if not isinstance(turn_version, int) or isinstance(turn_version, bool) or turn_version < 1:
            raise DurableNativeTurnError("turn_version must be a positive integer")

        def complete():
            return self._complete_external_narration_locked(
                external_turn_id=external_turn_id.strip(),
                player_input=player_input.strip(),
                narrative=narrative.strip(),
                turn_version=turn_version,
            )

        if self.turn_execution_lock is None:
            return complete()
        with self.turn_execution_lock.acquire():
            return complete()

    def _complete_external_narration_locked(
        self,
        *,
        external_turn_id: str,
        player_input: str,
        narrative: str,
        turn_version: int,
    ) -> TurnResolutionResult:
        record = self.resolution_repository.get_by_idempotency_key(
            "sillytavern", external_turn_id, scope=self.scope
        )
        active_turn = self.turn_repository.get_active_by_external_turn_id(
            external_turn_id, scope=self.scope
        )

        if record is not None and record.player_input != player_input:
            raise DurableNativeTurnError(
                "external turn identity was reused with different player input"
            )

        if record is not None and record.lifecycle_state == "awaiting_input":
            raise DurableNativeTurnError(
                "turn is awaiting player clarification and cannot be completed as narration"
            )

        if record is not None and record.lifecycle_state not in {
            "narration_pending",
            "completed",
        }:
            raise DurableNativeTurnError(
                f"turn is not ready for narration: {record.lifecycle_state}"
            )

        previous_turn = active_turn
        if previous_turn is None and record is not None and record.turn_id is not None:
            previous_turn = self.turn_repository.get_turn(
                record.turn_id, scope=self.scope
            )

        existing_versions = self.turn_repository.get_versions_by_external_turn_id(
            external_turn_id, scope=self.scope
        )
        latest_version = max(
            (turn.version for turn in existing_versions),
            default=0,
        )

        if previous_turn is not None:
            if previous_turn.player_input != player_input:
                raise DurableNativeTurnError(
                    "external turn identity was reused with different player input"
                )
            if turn_version == previous_turn.version:
                if previous_turn.narrative != narrative:
                    raise DurableNativeTurnError(
                        "external turn version already exists with different content"
                    )
                if record is not None and record.lifecycle_state == "completed":
                    return self._result_from_completed_record(
                        record, previous_turn, already_processed=True
                    )
                return TurnResolutionResult.from_persisted_turn(previous_turn)
            if turn_version < previous_turn.version:
                raise DurableNativeTurnError("external turn version is older than the active version")

        if turn_version != latest_version + 1:
            raise DurableNativeTurnError(
                f"external turn version must be {latest_version + 1}"
            )

        if record is None and previous_turn is None:
            raise DurableNativeTurnError(
                "no durable resolution exists for this external turn"
            )

        operation_results = (
            json.loads(record.operation_results_json or "[]")
            if record is not None
            else []
        )
        operation_count = (
            len(operation_results) if record is not None else previous_turn.operation_count
        )
        successful_count = (
            sum(1 for item in operation_results if item.get("success", False))
            if record is not None else previous_turn.successful_operation_count
        )
        failed_count = operation_count - successful_count
        world_changed = (
            any(item.get("changed", False) for item in operation_results)
            if record is not None else previous_turn.world_changed
        )
        session_id = (
            record.session_id if record is not None else previous_turn.session_id
        )
        turn = TurnRecord(
            session_id=session_id,
            player_input=player_input,
            narrative=narrative,
            operation_count=operation_count,
            successful_operation_count=successful_count,
            failed_operation_count=failed_count,
            all_operations_succeeded=(failed_count == 0),
            world_changed=world_changed,
            external_turn_id=external_turn_id,
            version=turn_version,
            status="active",
            snapshot=None,
        )

        with transaction("IMMEDIATE") as conn:
            current_active = self.turn_repository.get_active_by_external_turn_id(
                external_turn_id, scope=self.scope, conn=conn
            )
            current_versions = self.turn_repository.get_versions_by_external_turn_id(
                external_turn_id, scope=self.scope, conn=conn
            )
            current_latest_version = max(
                (turn.version for turn in current_versions),
                default=0,
            )
            if (
                current_active is not None
                and current_active.version >= turn_version
            ):
                if (
                    current_active.version == turn_version
                    and current_active.player_input == player_input
                    and current_active.narrative == narrative
                ):
                    if record is not None and record.lifecycle_state == "completed":
                        current_record = self.resolution_repository.get(
                            record.id, scope=self.scope, conn=conn
                        )
                        return self._result_from_completed_record(
                            current_record, current_active, already_processed=True
                        )
                    return TurnResolutionResult.from_persisted_turn(current_active)
                raise DurableNativeTurnError(
                    "external turn version changed while narration was being saved"
                )
            if turn_version != current_latest_version + 1:
                raise DurableNativeTurnError(
                    f"external turn version must be {current_latest_version + 1}"
                )
            if current_active is not None:
                self.turn_repository.supersede_turn(
                    current_active.id, scope=self.scope, conn=conn
                )
            saved_turn = self.turn_repository.save_turn(
                turn, scope=self.scope, conn=conn
            )
            if record is not None and record.lifecycle_state == "narration_pending":
                self.resolution_repository.transition(
                    record.id,
                    "completed",
                    scope=self.scope,
                    expected_state="narration_pending",
                    updates={
                        "turn_id": saved_turn.id,
                        "narrative": narrative,
                        "completed_at": datetime.now(UTC).isoformat(),
                    },
                    conn=conn,
                )
            elif record is not None:
                self.resolution_repository.update_completed_projection(
                    record.id,
                    turn_id=saved_turn.id,
                    narrative=narrative,
                    scope=self.scope,
                    conn=conn,
                )

        if record is None:
            return TurnResolutionResult.from_persisted_turn(saved_turn)
        completed = self.resolution_repository.get(record.id, scope=self.scope)
        return self._result_from_completed_record(
            completed, saved_turn, already_processed=(turn_version > 1)
        )

    def _result_from_completed_record(
        self,
        record: TurnResolutionRecord,
        turn: TurnRecord,
        *,
        already_processed: bool,
    ) -> TurnResolutionResult:
        mapper = DurableTurnResultMapper(
            self.resolver.extractor.operation_parser
        )
        return mapper.from_completed_record(
            record,
            turn,
            already_processed=already_processed,
        )

    @staticmethod
    def _resolved_player_input(record: TurnResolutionRecord) -> str:
        adjudication = json.loads(record.adjudication_json or "{}")
        return adjudication.get("resolved_player_input", record.player_input)

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
        resolved_player_input = self._resolved_player_input(record)
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
            resolved_player_input,
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
                    player_input=resolved_player_input,
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
                    "completed_at": datetime.now(UTC).isoformat(),
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
