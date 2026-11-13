"""Durable manual-roll challenge submission and recovery."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta

from database import transaction
from services.turns.turn_resolution_codec import TurnResolutionCodec


class DurableTurnManualRollSubmissionService:
    """Own manual-roll validation, submission, idempotency, and recovery."""

    def __init__(self, turn_service, *, error_type) -> None:
        self.turn_service = turn_service
        self.error_type = error_type

    def submit_manual_roll(
        self, pending_roll_id: str, rolls: tuple[int, ...], *,
        adapter_namespace: str | None = None,
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
            raise self.error_type("answer_external_turn_id must contain 1-500 characters")
        if answer_external_turn_id is not None:
            answer_external_turn_id = answer_external_turn_id.strip()
        if not isinstance(pending_roll_id, str) or ":" not in pending_roll_id:
            raise self.error_type("pending_roll_id is invalid")
        if not isinstance(rolls, tuple) or not rolls or len(rolls) > 2 or any(isinstance(v, bool) or not isinstance(v, int) or v < 1 or v > 20 for v in rolls):
            raise self.error_type("manual d20 results must contain one or two integers from 1 to 20")
        raw_id, challenge_id = pending_roll_id.split(":", 1)
        if not raw_id.isdigit() or not challenge_id:
            raise self.error_type("pending_roll_id is invalid")
        def submit():
            record = service.resolution_repository.get(int(raw_id), scope=service.scope)
            if record is None:
                raise self.error_type("manual roll request not found")
            if adapter_namespace is not None and record.adapter_namespace != adapter_namespace:
                raise self.error_type("manual roll challenge belongs to a different adapter")
            if conversation_id is not None and record.conversation_id != conversation_id:
                raise self.error_type("manual roll challenge belongs to a different conversation")
            state = json.loads(record.adjudication_json or "{}")
            pending = state.get("manual_roll")
            if not pending or not secrets.compare_digest(pending.get("challenge_id", ""), challenge_id):
                raise self.error_type("manual roll challenge is invalid or stale")
            accepted = pending.get("submitted_rolls")
            if accepted is not None:
                if list(rolls) != accepted:
                    raise self.error_type("manual roll challenge was already submitted with different results")
                accepted_external_turn_id = pending.get("submitted_external_turn_id")
                if (
                    accepted_external_turn_id is not None
                    and answer_external_turn_id is not None
                    and not secrets.compare_digest(str(accepted_external_turn_id), answer_external_turn_id)
                ):
                    raise self.error_type(
                        "manual roll challenge was already submitted by a different chat message"
                    )
                if record.lifecycle_state in {"narration_pending", "committed"}:
                    return service._preparation_from_record(record) if defer_narration else service._resume_narration(record, already_processed=True)
                if record.lifecycle_state == "completed":
                    turn = service.turn_repository.get_turn(record.turn_id, scope=service.scope)
                    return service._result_from_completed_record(record, turn, already_processed=True)
                if record.lifecycle_state == "prepared":
                    with transaction("DEFERRED") as conn:
                        context, recent = service._context_and_history(conn, conversation_id=record.conversation_id)
                        revision = service.revision_repository.get_revision(service.scope.campaign_id, conn=conn)
                    if revision != record.context_revision:
                        raise self.error_type("prepared manual roll became stale before commit")
                    plan = service._plan_from_record(record)
                    service.prepared_commit_service.commit_prepared_plan(
                        record,
                        plan,
                        context=context,
                        recent=recent,
                        revision=revision,
                        revision_error_message=(
                            "prepared manual roll became stale before commit"
                        ),
                        context_error_message=(
                            "campaign context changed while recovering the manual roll"
                        ),
                    )
                    saved = service.resolution_repository.get(record.id, scope=service.scope)
                    return service._preparation_from_record(saved) if defer_narration else service._resume_narration(saved, already_processed=True)
            if record.lifecycle_state not in {"awaiting_input", "planning"}:
                raise self.error_type("manual roll challenge is no longer pending")
            with transaction("DEFERRED") as conn:
                context, recent = service._context_and_history(conn)
                revision = service.revision_repository.get_revision(service.scope.campaign_id, conn=conn)
            if revision != pending.get("context_revision") or revision != record.context_revision:
                expected_state = record.lifecycle_state
                lease_token = None
                if expected_state == "planning":
                    lease_token = secrets.token_urlsafe(24)
                    try:
                        with transaction("IMMEDIATE") as conn:
                            service.resolution_repository.claim_for_planning(
                                record.id, scope=service.scope, lease_token=lease_token,
                                lease_expires_at=(datetime.now(UTC) + timedelta(minutes=3)).isoformat(),
                                now=datetime.now(UTC).isoformat(), conn=conn,
                            )
                    except ValueError as exc:
                        raise self.error_type("manual roll is still being submitted; retry") from exc
                with transaction("IMMEDIATE") as conn:
                    service.resolution_repository.transition(
                        record.id, "rejected", scope=service.scope,
                        expected_state=expected_state,
                        expected_lease_token=lease_token,
                        updates={"last_error_code": "stale_manual_roll"}, conn=conn,
                    )
                raise self.error_type("campaign state changed while waiting for the manual roll")
            if len(rolls) != pending["count"]:
                raise self.error_type("manual roll has an invalid number of dice")
            token = secrets.token_urlsafe(24)
            try:
                with transaction("IMMEDIATE") as conn:
                    record = service.resolution_repository.claim_for_planning(record.id, scope=service.scope, lease_token=token, lease_expires_at=(datetime.now(UTC) + timedelta(minutes=3)).isoformat(), now=datetime.now(UTC).isoformat(), conn=conn)
            except ValueError as exc:
                raise self.error_type("manual roll is already being submitted; retry") from exc
            from models.mechanics import MechanicsDecision, MechanicsDecisionType
            from rules_engine.dnd5e_2014.core.abilities import Ability
            from rules_engine.dnd5e_2014.core.skills import Skill
            d = pending["decision"]
            decision = MechanicsDecision(decision=MechanicsDecisionType(d["decision"]), skill=Skill(d["skill"]) if d["skill"] else None, ability=Ability(d["ability"]) if d["ability"] else None, dc=d["dc"], advantage=d["advantage"], disadvantage=d["disadvantage"], situational_modifier=d["situational_modifier"], reason=d["reason"], question=d["question"])
            persisted_source_text = TurnResolutionCodec.intent_source_text(
                record.intent_json,
                original_input=record.player_input,
            )
            persisted_evidence_text = TurnResolutionCodec.intent_evidence_text(
                record.intent_json,
                original_input=record.player_input,
            )
            persisted_intent = TurnResolutionCodec.intent_from_json(
                record.intent_json,
                original_input=record.player_input,
            )
            plan = service.resolver.prepare_turn(
                context,
                persisted_source_text,
                manual_mode=True,
                manual_rolls=rolls,
                decision_override=decision,
                intent_analysis_override=persisted_intent,
                recent_turns=recent,
                intent_evidence_text=persisted_evidence_text,
            )
            if plan.awaiting_manual_roll or plan.clarification_question:
                raise self.error_type("manual roll could not be resolved")
            pending["submitted_rolls"] = list(rolls)
            if answer_external_turn_id is not None:
                pending["submitted_external_turn_id"] = answer_external_turn_id
            with transaction("IMMEDIATE") as conn:
                service.resolution_repository.transition(record.id, "prepared", scope=service.scope, expected_state="planning", expected_lease_token=token, updates={"proposal_json": service._serialize_operations(plan), "mechanics_json": service._mechanics_to_json(plan.mechanics_result), "adjudication_json": json.dumps({"manual_roll": pending}, separators=(",", ":"), sort_keys=True), "lease_token": None, "lease_expires_at": None}, conn=conn)
            service.prepared_commit_service.commit_prepared_plan(
                record,
                plan,
                context=context,
                recent=recent,
                revision=revision,
                revision_error_message=(
                    "campaign context changed while resolving the manual roll"
                ),
                context_error_message=(
                    "campaign context changed while resolving the manual roll"
                ),
            )
            saved = service.resolution_repository.get(record.id, scope=service.scope)
            return service._preparation_from_record(saved) if defer_narration else service._resume_narration(saved, already_processed=False)
        if service.turn_execution_lock is None:
            return submit()
        with service.turn_execution_lock.acquire():
            return submit()
