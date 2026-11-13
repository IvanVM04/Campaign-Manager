"""Serialization boundary for durable turn-resolution records.

This module owns the JSON representation persisted by the durable turn
lifecycle. Keep the payload shape backward compatible: existing SQLite
records must remain readable without a migration.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from enum import Enum

from models.player_intent_analysis import PlayerIntentAnalysis
from models.turn_resolution_record import TurnResolutionRecord
from models.turn_resolution_result import TurnResolutionResult
from operations.character_operations import CharacterOperation
from operations.operation_reference import OperationReference
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import WorldOperation
from services.turns.turn_resolution_service import TurnResolutionPlan


class TurnResolutionCodec:
    """Encode and reconstruct the durable resolution's persisted payloads."""

    @staticmethod
    def json_default(value):
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return {
                field.name: getattr(value, field.name)
                for field in fields(value)
            }
        raise TypeError(f"cannot serialize {type(value).__name__}")

    @classmethod
    def operation_value(cls, value):
        if isinstance(value, OperationReference):
            return "$" + value.name
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (tuple, list)):
            return [cls.operation_value(item) for item in value]
        if isinstance(value, dict):
            return {
                key: cls.operation_value(item)
                for key, item in value.items()
            }
        if is_dataclass(value):
            return {
                field.name: cls.operation_value(getattr(value, field.name))
                for field in fields(value)
            }
        return value

    @classmethod
    def serialize_operations(cls, plan: TurnResolutionPlan) -> str:
        from services.llm_world.operation_parser import OperationParser

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
                raise ValueError(
                    f"unsupported operation type: {type(operation).__name__}"
                )
            payload = {
                "type": operation_type,
                **cls.operation_value(operation),
            }
            if ref is not None:
                payload["ref"] = ref
            serialized.append(payload)
        return json.dumps(
            {"operations": serialized},
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def mechanics_to_json(result) -> str | None:
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
    def mechanics_from_json(payload: str | None):
        if payload is None:
            return None
        from models.mechanics import (
            MechanicsDecision,
            MechanicsDecisionType,
            MechanicsResult,
        )
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
    def operation_results_json(result: TurnResolutionResult) -> str:
        return json.dumps([
            {
                "status": item.status.value,
                "message": item.message,
                "changed": item.changed,
                "success": item.success,
            }
            for item in result.operation_results
        ], separators=(",", ":"), sort_keys=True)

    @staticmethod
    def intent_to_json(plan: TurnResolutionPlan) -> str | None:
        """Persist the exact source text with its evidence-bound interpretation."""
        analysis = plan.intent_analysis
        if analysis is None:
            return None
        return json.dumps(
            {
                "schema_version": 1,
                "source_text": plan.player_input,
                "source_sha256": hashlib.sha256(
                    plan.player_input.encode("utf-8")
                ).hexdigest(),
                "analysis": analysis.to_dict(),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def intent_from_json(
        payload: str | None,
        *,
        original_input: str,
    ) -> PlayerIntentAnalysis | None:
        """Rebuild an analysis only when it remains bound to original input."""
        if payload is None:
            return None
        try:
            envelope = json.loads(payload)
            if not isinstance(envelope, dict) or set(envelope) != {
                "schema_version", "source_text", "source_sha256", "analysis"
            }:
                raise ValueError("invalid persisted intent envelope")
            if envelope["schema_version"] != 1:
                raise ValueError("unsupported persisted intent envelope version")
            source_text = envelope["source_text"]
            if (
                not isinstance(source_text, str)
                or len(source_text) > 20000
                or not source_text.startswith(original_input)
            ):
                raise ValueError("persisted intent is not bound to the original input")
            expected_digest = hashlib.sha256(
                source_text.encode("utf-8")
            ).hexdigest()
            if envelope["source_sha256"] != expected_digest:
                raise ValueError("persisted intent source fingerprint does not match")
            return PlayerIntentAnalysis.from_payload(
                envelope["analysis"],
                source_text=source_text,
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"persisted player intent analysis is invalid: {exc}"
            ) from exc

    @staticmethod
    def intent_source_text(
        payload: str | None,
        *,
        original_input: str,
    ) -> str:
        """Return the validated source text bound to an optional stored analysis."""
        if payload is None:
            return original_input
        TurnResolutionCodec.intent_from_json(
            payload,
            original_input=original_input,
        )
        return json.loads(payload)["source_text"]

    @classmethod
    def plan_from_record(cls, record: TurnResolutionRecord, operation_parser):
        parsed = operation_parser.parse(record.proposal_json or '{"operations":[]}')
        ordered = tuple(parsed)

        def unwrap(raw):
            return raw.operation if isinstance(raw, ReferencedOperation) else raw

        world_operations = tuple(
            raw for raw in ordered if isinstance(unwrap(raw), WorldOperation)
        )
        character_operations = tuple(
            raw for raw in ordered if isinstance(unwrap(raw), CharacterOperation)
        )
        mechanics_result = cls.mechanics_from_json(record.mechanics_json)
        intent_analysis = cls.intent_from_json(
            getattr(record, "intent_json", None),
            original_input=record.player_input,
        )
        intent_source_text = cls.intent_source_text(
            getattr(record, "intent_json", None),
            original_input=record.player_input,
        )
        return TurnResolutionPlan(
            player_input=intent_source_text,
            narrative="",
            world_operations=world_operations,
            character_operations=character_operations,
            ordered_operations=ordered,
            mechanics_result=mechanics_result,
            mechanics_decision=mechanics_result.decision if mechanics_result else None,
            intent_analysis=intent_analysis,
        )
