"""Durable clarification challenge submission and recovery."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta

from database import transaction
from models.turn_resolution_record import TurnResolutionRecord
from services.turns.turn_resolution_codec import TurnResolutionCodec


class DurableTurnClarificationSubmissionService:
    """Own clarification validation, planning leases, and recovery flow.

    The native turn service remains the owner of shared repositories and
    collaborators. This service coordinates the clarification-specific
    lifecycle without owning manual-roll challenge behavior.
    """

    def __init__(self, turn_service, *, error_type) -> None:
        self.turn_service = turn_service
        self.error_type = error_type

    def submit_clarification(
        self,
        pending_clarification_id: str,
        answer: str,
        *,
        adapter_namespace: str = "native",
        defer_narration: bool = False,
        answer_external_turn_id: str | None = None,
        conversation_id: str | None = None,
    ):
        service = self.turn_service
        if answer_external_turn_id is not None and (
            not isinstance(answer_external_turn_id, str)
            or not answer_external_turn_id.strip()
            or len(answer_external_turn_id.strip()) > 500
        ):
            raise self.error_type(
                "answer_external_turn_id must contain 1-500 characters"
            )
        if answer_external_turn_id is not None:
            answer_external_turn_id = answer_external_turn_id.strip()
        if (
            not isinstance(pending_clarification_id, str)
            or ":" not in pending_clarification_id
        ):
            raise self.error_type("pending_clarification_id is invalid")
        if not isinstance(answer, str) or not answer.strip():
            raise self.error_type("clarification answer must not be empty")
        answer = answer.strip()
        if len(answer) > 5000:
            raise self.error_type("clarification answer must not exceed 5000 characters")
        raw_id, challenge_id = pending_clarification_id.split(":", 1)
        if not raw_id.isdigit() or not challenge_id:
            raise self.error_type("pending_clarification_id is invalid")

        def submit():
            record = service.resolution_repository.get(int(raw_id), scope=service.scope)
            if record is None:
                raise self.error_type("clarification request was not found")
            if record.adapter_namespace != adapter_namespace:
                raise self.error_type(
                    "clarification challenge belongs to a different adapter"
                )
            if record.conversation_id != conversation_id:
                raise self.error_type("clarification challenge belongs to a different conversation")
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
                            service._preparation_from_record(record)
                            if defer_narration
                            else service._clarification_result(record, current_pending)
                        )
                if record.lifecycle_state == "prepared":
                    return self._resume_prepared_clarification(
                        record, defer_narration=defer_narration
                    )
                if record.lifecycle_state in {"committed", "narration_pending"}:
                    return (
                        service._preparation_from_record(record)
                        if defer_narration
                        else service._resume_narration(record, already_processed=True)
                    )
                if record.lifecycle_state == "completed" and defer_narration:
                    return service._preparation_from_record(record)
                if record.lifecycle_state == "completed":
                    turn = service.turn_repository.get_turn(
                        record.turn_id, scope=service.scope
                    )
                    if turn is None:
                        raise self.error_type(
                            "completed clarification has no transcript"
                        )
                    return service._result_from_completed_record(
                        record, turn, already_processed=True
                    )
            if record.lifecycle_state not in {"awaiting_input", "planning"}:
                raise self.error_type("clarification request is no longer pending")
            pending = pending_state.get("clarification")
            if not isinstance(pending, dict) or not secrets.compare_digest(
                str(pending.get("challenge_id", "")), challenge_id
            ):
                raise self.error_type("clarification challenge is invalid or expired")

            token = secrets.token_urlsafe(24)
            now = datetime.now(UTC)
            try:
                with transaction("IMMEDIATE") as conn:
                    record = service.resolution_repository.claim_for_planning(
                        record.id,
                        scope=service.scope,
                        lease_token=token,
                        lease_expires_at=(now + timedelta(minutes=3)).isoformat(),
                        now=now.isoformat(),
                        conn=conn,
                    )
            except ValueError as exc:
                raise self.error_type(
                    "clarification is already being processed; retry"
                ) from exc

            try:
                with transaction("DEFERRED") as conn:
                    context, recent = service._context_and_history(conn, conversation_id=record.conversation_id)
                    revision = service.revision_repository.get_revision(
                        service.scope.campaign_id, conn=conn
                    )
                if (
                    revision != record.context_revision
                    or revision != pending.get("context_revision")
                ):
                    with transaction("IMMEDIATE") as conn:
                        service.resolution_repository.transition(
                            record.id,
                            "rejected",
                            scope=service.scope,
                            expected_state="planning",
                            expected_lease_token=token,
                            updates={"last_error_code": "stale_clarification"},
                            conn=conn,
                        )
                    raise self.error_type(
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
                clarified_evidence = record.player_input + "".join(
                    "\n\n" + item["answer"]
                    for item in history
                )
                plan = service.resolver.prepare_turn(
                    context,
                    clarified_input,
                    manual_mode=(pending_state.get("dice_mode") == "manual"),
                    recent_turns=recent,
                    intent_evidence_text=clarified_evidence,
                )
                if plan.awaiting_manual_roll:
                    manual_pending = service._build_manual_roll_request(
                        record, plan.mechanics_decision, context, revision
                    )
                    with transaction("IMMEDIATE") as conn:
                        service.resolution_repository.transition(
                            record.id, "awaiting_input", scope=service.scope,
                            expected_state="planning", expected_lease_token=token,
                            updates={
                                "context_revision": revision,
                                "intent_json": TurnResolutionCodec.intent_to_json(plan),
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
                    saved = service.resolution_repository.get(record.id, scope=service.scope)
                    return service._manual_roll_result(saved, manual_pending)
                if plan.clarification_question is not None:
                    next_pending = {
                        "challenge_id": secrets.token_urlsafe(24),
                        "context_revision": revision,
                        "question": plan.clarification_question,
                        "history": history,
                    }
                    with transaction("IMMEDIATE") as conn:
                        service.resolution_repository.transition(
                            record.id,
                            "awaiting_input",
                            scope=service.scope,
                            expected_state="planning",
                            expected_lease_token=token,
                            updates={
                                "context_revision": revision,
                                "intent_json": TurnResolutionCodec.intent_to_json(plan),
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
                    saved = service.resolution_repository.get(record.id, scope=service.scope)
                    return (
                        service._preparation_from_record(saved)
                        if defer_narration
                        else service._clarification_result(saved, next_pending)
                    )

                with transaction("IMMEDIATE") as conn:
                    service.resolution_repository.transition(
                        record.id,
                        "prepared",
                        scope=service.scope,
                        expected_state="planning",
                        expected_lease_token=token,
                        updates={
                            "context_revision": revision,
                            "proposal_json": service._serialize_operations(plan),
                            "intent_json": TurnResolutionCodec.intent_to_json(plan),
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
                            "mechanics_json": service._mechanics_to_json(
                                plan.mechanics_result
                            ),
                            "lease_token": None,
                            "lease_expires_at": None,
                        },
                        conn=conn,
                    )

                service.prepared_commit_service.commit_prepared_plan(
                    record,
                    plan,
                    context=context,
                    recent=recent,
                    revision=revision,
                    revision_error_message=(
                        "campaign context changed while clarification was being resolved"
                    ),
                    context_error_message=(
                        "campaign context changed while clarification was being resolved"
                    ),
                )
                saved = service.resolution_repository.get(record.id, scope=service.scope)
                return (
                    service._preparation_from_record(saved)
                    if defer_narration
                    else service._resume_narration(saved, already_processed=False)
                )
            except Exception as exc:
                current = service.resolution_repository.get(record.id, scope=service.scope)
                if current is not None and current.lifecycle_state == "prepared":
                    with transaction("IMMEDIATE") as conn:
                        service.resolution_repository.transition(
                            record.id,
                            "rejected",
                            scope=service.scope,
                            expected_state="prepared",
                            updates={"last_error_code": "clarification_resolution_failed"},
                            conn=conn,
                        )
                if isinstance(exc, self.error_type):
                    raise
                raise self.error_type(
                    "clarification resolution failed"
                ) from exc

        if service.turn_execution_lock is None:
            return submit()
        with service.turn_execution_lock.acquire():
            return submit()

    def _resume_prepared_clarification(
        self,
        record: TurnResolutionRecord,
        *,
        defer_narration: bool,
    ):
        service = self.turn_service
        with transaction("DEFERRED") as conn:
            context, recent = service._context_and_history(conn)
            revision = service.revision_repository.get_revision(
                service.scope.campaign_id, conn=conn
            )
        if revision != record.context_revision:
            with transaction("IMMEDIATE") as conn:
                service.resolution_repository.transition(
                    record.id,
                    "rejected",
                    scope=service.scope,
                    expected_state="prepared",
                    updates={"last_error_code": "stale_clarification"},
                    conn=conn,
                )
            raise self.error_type(
                "campaign state changed while recovering clarification"
            )

        plan = service._plan_from_record(record)
        try:
            service.prepared_commit_service.commit_prepared_plan(
                record,
                plan,
                context=context,
                recent=recent,
                revision=revision,
                revision_error_message=(
                    "campaign state changed while recovering clarification"
                ),
                context_error_message=(
                    "campaign context changed while recovering clarification"
                ),
            )
        except Exception as exc:
            current = service.resolution_repository.get(record.id, scope=service.scope)
            if current is not None and current.lifecycle_state == "prepared":
                with transaction("IMMEDIATE") as conn:
                    service.resolution_repository.transition(
                        record.id,
                        "rejected",
                        scope=service.scope,
                        expected_state="prepared",
                        updates={"last_error_code": "clarification_recovery_failed"},
                        conn=conn,
                    )
            if isinstance(exc, self.error_type):
                raise
            raise self.error_type(
                "prepared clarification recovery failed"
            ) from exc

        saved = service.resolution_repository.get(record.id, scope=service.scope)
        return (
            service._preparation_from_record(saved)
            if defer_narration
            else service._resume_narration(saved, already_processed=True)
        )

