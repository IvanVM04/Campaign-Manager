"""Opt-in v3 shadow prompt and side-by-side interpreter runner.

This module deliberately lives under tests/: it is an evaluation harness, not
a production route. The v2 interpreter remains authoritative for live turns.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from models.player_intent_analysis import PlayerIntentAnalysis
from models.player_turn_interpretation_v3 import (
    TurnInterpretationV3,
    TurnInterpretationV3ValidationError,
)
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from services.providers import LLMProvider
from services.turns.intent_interpreter import IntentInterpreter
from services.turns.player_turn_v3_prompt import (
    V3_EVIDENCE_ALIGNMENT_VERSION,
    V3_PROMPT_VERSION,
    V3_RESPONSE_SCHEMA,
    V3_SYSTEM_PROMPT,
    EvidenceSpanAlignmentError,
    ShadowPromptError,
    align_v3_evidence_span_offsets,
    build_v3_shadow_prompt,
)


__all__ = [
    "V3_EVIDENCE_ALIGNMENT_VERSION",
    "V3_PROMPT_VERSION",
    "V3_RESPONSE_SCHEMA",
    "V3_SYSTEM_PROMPT",
    "align_v3_evidence_span_offsets",
    "build_v3_shadow_prompt",
]


class _PromptCapturingProvider(LLMProvider):
    """Transparent provider proxy that retains only the prompt for one call."""

    def __init__(self, delegate: LLMProvider) -> None:
        if not isinstance(delegate, LLMProvider):
            raise TypeError("delegate must be an LLMProvider")
        self.delegate = delegate
        self.captured_prompt: str | None = None

    @property
    def model(self) -> str | None:
        value = getattr(self.delegate, "model", None)
        return value if isinstance(value, str) else None

    def generate(self, prompt: str) -> str:
        self.captured_prompt = prompt
        return self.delegate.generate(prompt)

    def generate_structured(
        self,
        prompt: str,
        *,
        schema: dict[str, Any],
    ) -> str:
        self.captured_prompt = prompt
        return self.delegate.generate_structured(prompt, schema=schema)


@dataclass(frozen=True, slots=True)
class V2V3ShadowComparison:
    """In-memory result; it deliberately contains no raw prompt/completion."""

    v2_analysis: PlayerIntentAnalysis | None
    v3_interpretation: TurnInterpretationV3 | None
    v2_status: str
    v3_status: str
    v2_error_type: str | None
    v3_error_code: str | None
    v3_error_field: str | None
    v2_duration_ms: float
    v3_duration_ms: float
    v2_prompt_bytes: int | None
    v3_prompt_bytes: int | None
    v3_evidence_spans_realigned: int = 0


class PlayerTurnInterpretationV3ShadowRunner:
    """Run the production v2 interpreter and an isolated v3 shadow call.

    The v2 interpreter is cloned with the same provider, context builder,
    prompt/context budgets and normalizer. Its exact rendered prompt is
    captured and reused as the source of v3 context. The original interpreter
    and production composition are never modified.
    """

    def __init__(self, interpreter: IntentInterpreter) -> None:
        if not isinstance(interpreter, IntentInterpreter):
            raise TypeError("interpreter must be an IntentInterpreter")
        self.interpreter = interpreter

    def run(
        self,
        context: TurnContext,
        player_input: str,
        *,
        recent_turns: list[TurnRecord] | None = None,
        evidence_text: str | None = None,
        v3_system_prompt: str = V3_SYSTEM_PROMPT,
    ) -> V2V3ShadowComparison:
        provider = self.interpreter.provider
        capturing_provider = _PromptCapturingProvider(provider)
        shadow_v2_interpreter = IntentInterpreter(
            provider=capturing_provider,
            context_builder=self.interpreter.context_builder,
            max_prompt_bytes=self.interpreter.max_prompt_bytes,
            max_context_bytes=self.interpreter.max_context_bytes,
            normalization_pipeline=self.interpreter.normalization_pipeline,
        )
        exact_evidence = evidence_text if evidence_text is not None else player_input
        v2_started = perf_counter()
        v2_analysis: PlayerIntentAnalysis | None = None
        v2_error_type: str | None = None
        try:
            v2_analysis = shadow_v2_interpreter.interpret(
                context,
                player_input,
                recent_turns=recent_turns,
                evidence_text=evidence_text,
            )
            v2_status = "valid"
        except Exception as exc:  # noqa: BLE001 - a shadow benchmark records a safe miss
            v2_status = "invalid"
            v2_error_type = type(exc).__name__
        v2_duration_ms = round((perf_counter() - v2_started) * 1000, 3)
        v2_prompt = capturing_provider.captured_prompt
        v2_prompt_bytes = (
            len(v2_prompt.encode("utf-8")) if v2_prompt is not None else None
        )
        if v2_prompt is None:
            return V2V3ShadowComparison(
                v2_analysis, None, v2_status, "not_run", v2_error_type,
                "v2_prompt_unavailable", None, v2_duration_ms, 0.0,
                v2_prompt_bytes, None,
            )

        v3_started = perf_counter()
        v3_prompt: str | None = None
        v3_interpretation: TurnInterpretationV3 | None = None
        v3_evidence_spans_realigned = 0
        try:
            v3_prompt = build_v3_shadow_prompt(
                v2_prompt,
                expected_evidence=exact_evidence,
                max_prompt_bytes=self.interpreter.max_prompt_bytes,
                system_prompt=v3_system_prompt,
            )
        except ShadowPromptError as exc:
            v3_status = "not_run"
            v3_error_code = exc.code
            v3_error_field = None
        else:
            try:
                raw = provider.generate_structured(
                    v3_prompt,
                    schema=V3_RESPONSE_SCHEMA,
                )
                if not isinstance(raw, str):
                    raise TypeError("provider returned non-text")
                aligned_raw, v3_evidence_spans_realigned = (
                    align_v3_evidence_span_offsets(
                        raw,
                        source_text=exact_evidence,
                    )
                )
                v3_interpretation = TurnInterpretationV3.from_json(
                    aligned_raw,
                    source_text=exact_evidence,
                )
                v3_status = "valid"
                v3_error_code = None
                v3_error_field = None
            except EvidenceSpanAlignmentError as exc:
                v3_interpretation = None
                v3_status = "invalid"
                v3_error_code = exc.code
                v3_error_field = exc.field_path
            except TurnInterpretationV3ValidationError as exc:
                v3_interpretation = None
                v3_status = "invalid"
                v3_error_code = exc.code
                v3_error_field = exc.field_path
            except Exception as exc:  # noqa: BLE001 - do not expose provider content
                v3_interpretation = None
                v3_status = "provider_or_decoder_error"
                v3_error_code = type(exc).__name__
                v3_error_field = None
        v3_duration_ms = round((perf_counter() - v3_started) * 1000, 3)
        return V2V3ShadowComparison(
            v2_analysis=v2_analysis,
            v3_interpretation=v3_interpretation,
            v2_status=v2_status,
            v3_status=v3_status,
            v2_error_type=v2_error_type,
            v3_error_code=v3_error_code,
            v3_error_field=v3_error_field,
            v2_duration_ms=v2_duration_ms,
            v3_duration_ms=v3_duration_ms,
            v2_prompt_bytes=v2_prompt_bytes,
            v3_prompt_bytes=(
                len(v3_prompt.encode("utf-8")) if v3_prompt is not None else None
            ),
            v3_evidence_spans_realigned=v3_evidence_spans_realigned,
        )


def comparison_shape(comparison: V2V3ShadowComparison) -> dict[str, Any]:
    """Return a text-free, low-cardinality shape for diagnostics and reports."""
    v2 = comparison.v2_analysis
    v3 = comparison.v3_interpretation
    return {
        "v2": {
            "status": comparison.v2_status,
            "category": (
                v2.category.value if v2 is not None else None
            ),
            "step_count": len(v2.steps) if v2 is not None else None,
            "active_step_index": (
                v2.active_step_index if v2 is not None else None
            ),
            "modalities": (
                [step.modality.value for step in v2.steps]
                if v2 is not None else []
            ),
            "actors": (
                [step.actor.value for step in v2.steps]
                if v2 is not None else []
            ),
            "relation_count": (
                len(v2.relation_claims) if v2 is not None else None
            ),
            "prompt_bytes": comparison.v2_prompt_bytes,
            "duration_ms": comparison.v2_duration_ms,
            "error_type": comparison.v2_error_type,
        },
        "v3": {
            "status": comparison.v3_status,
            "act_count": len(v3.utterance_acts) if v3 is not None else None,
            "event_count": len(v3.events) if v3 is not None else None,
            "link_count": len(v3.discourse_links) if v3 is not None else None,
            "fact_count": len(v3.world_facts) if v3 is not None else None,
            "clarification_count": (
                len(v3.clarification_candidates) if v3 is not None else None
            ),
            "evidence_span_count": (
                sum(len(item.evidence_spans) for item in (
                    *v3.utterance_acts, *v3.events, *v3.discourse_links,
                    *v3.world_facts, *v3.clarification_candidates,
                )) if v3 is not None else None
            ),
            "quote_span_count": (
                sum(len(item.quote_spans) for item in v3.utterance_acts)
                if v3 is not None else None
            ),
            "speaker_mention_count": (
                sum(item.speaker_mention is not None for item in v3.utterance_acts)
                if v3 is not None else None
            ),
            "addressee_mention_count": (
                sum(item.addressee_mention is not None for item in v3.utterance_acts)
                if v3 is not None else None
            ),
            "event_attributed_source_count": (
                sum(item.attributed_source is not None for item in v3.events)
                if v3 is not None else None
            ),
            "fact_attributed_source_count": (
                sum(item.attributed_source is not None for item in v3.world_facts)
                if v3 is not None else None
            ),
            "fact_directions": [
                item.direction.value for item in v3.world_facts
                if item.direction is not None
            ] if v3 is not None else [],
            "fact_polarities": [
                item.polarity.value for item in v3.world_facts
            ] if v3 is not None else [],
            "fact_epistemic_statuses": [
                item.epistemic_status.value for item in v3.world_facts
            ] if v3 is not None else [],
            "fact_temporal_scopes": [
                item.temporal_scope.value for item in v3.world_facts
            ] if v3 is not None else [],
            "fact_predicate_surfaces": [
                item.predicate_surface for item in v3.world_facts
                if item.fact_kind.value == "relation"
            ] if v3 is not None else [],
            "normalized_relation_types": [
                item.normalized_relation_type for item in v3.world_facts
                if item.normalized_relation_type is not None
            ] if v3 is not None else [],
            "clarification_kinds": [
                item.ambiguity_kind.value for item in v3.clarification_candidates
            ] if v3 is not None else [],
            "link_source_ref_kinds": [
                item.source_ref.split(":", 1)[0] for item in v3.discourse_links
            ] if v3 is not None else [],
            "link_target_ref_kinds": [
                item.target_ref.split(":", 1)[0] if item.target_ref is not None else "none"
                for item in v3.discourse_links
            ] if v3 is not None else [],
            "callback_anchor_candidates": [
                item.anchor_candidate for item in v3.discourse_links
                if item.anchor_candidate is not None
            ] if v3 is not None else [],
            "event_predicate_surfaces": [
                item.predicate_surface for item in v3.events
            ] if v3 is not None else [],
            "act_forces": (
                [item.force.value for item in v3.utterance_acts]
                if v3 is not None else []
            ),
            "speaker_roles": (
                [item.speaker_role.value for item in v3.utterance_acts]
                if v3 is not None else []
            ),
            "event_families": (
                [item.family.value for item in v3.events]
                if v3 is not None else []
            ),
            "polarities": (
                [item.polarity.value for item in v3.events]
                if v3 is not None else []
            ),
            "epistemic_statuses": (
                [item.epistemic_status.value for item in v3.events]
                if v3 is not None else []
            ),
            "action_phases": (
                [item.action_phase.value for item in v3.events]
                if v3 is not None else []
            ),
            "link_types": (
                [item.link_type.value for item in v3.discourse_links]
                if v3 is not None else []
            ),
            "fact_kinds": (
                [item.fact_kind.value for item in v3.world_facts]
                if v3 is not None else []
            ),
            "relation_families": [
                item.relation_family.value
                for item in v3.world_facts
                if item.relation_family is not None
            ] if v3 is not None else [],
            "prompt_bytes": comparison.v3_prompt_bytes,
            "evidence_spans_realigned": comparison.v3_evidence_spans_realigned,
            "duration_ms": comparison.v3_duration_ms,
            "error_code": comparison.v3_error_code,
            "error_field": comparison.v3_error_field,
        },
    }
