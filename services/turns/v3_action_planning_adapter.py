"""Per-action planning adapter from stored v3 semantics to legacy mechanics.

This adapter never reinterprets player language. It selects one already-built
checkpoint node, derives a one-step v2 analysis from that exact EventFrame,
and asks TurnResolutionService to plan only the selected evidence excerpt.
The full player input is restored on the resulting plan for durable identity
and transcript association after planning has completed.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from models.player_intent_analysis import (
    IntentActor,
    IntentModality,
    IntentPolarity,
    IntentStep,
    PlayerIntentAnalysis,
    PlayerReportedOutcome,
    UtteranceCategory,
)
from models.player_turn_interpretation_v3 import (
    EventFrame,
    EvidenceSpan,
    GameplayActionCandidate,
    GameplayActionEligibility,
    GameplayResolvedReference,
    GameplayResolvedReferenceKind,
    GameplayWorkflow,
    SpeakerRole,
    UtteranceAct,
)
from models.resolved_conversation_reference import ResolvedConversationReference
from models.semantic_frames import SemanticActionFrame
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.world_context_projection import WorldContextProjection
from services.turns.player_action_selector import (
    ActionSelectionStatus,
    select_next_action,
)
from services.turns.turn_resolution_service import (
    TurnResolutionPlan,
    TurnResolutionService,
)
from services.turns.v3_action_preview_service import V3ActionPreviewResult


class V3ActionPlanningError(RuntimeError):
    """Safe failure while lowering one stored v3 action into a mechanics plan."""

    def __init__(self, code: str, stage: str) -> None:
        self.code = code
        self.stage = stage
        super().__init__(f"v3 action planning failed ({stage}:{code})")


@dataclass(frozen=True, slots=True)
class V3ActionPlanningResult:
    """One selected action and its one-step legacy mechanics/proposal plan."""

    candidate: GameplayActionCandidate
    event: EventFrame
    intent_analysis: PlayerIntentAnalysis
    evidence_excerpt: str
    resolved_references: tuple[ResolvedConversationReference, ...]
    additional_reference_mentions: tuple[str, ...]
    plan: TurnResolutionPlan


class V3ActionPlanningAdapter:
    """Lower one next-ready v3 graph node into a single legacy plan."""

    @staticmethod
    def _occurrences(
        source: str,
        needle: str,
        spans: tuple[EvidenceSpan, ...],
    ) -> tuple[tuple[int, int], ...]:
        folded_needle = needle.casefold()
        if not folded_needle:
            return ()
        values: list[tuple[int, int]] = []
        for span in spans:
            folded_span = span.text.casefold()
            cursor = 0
            while True:
                found = folded_span.find(folded_needle, cursor)
                if found < 0:
                    break
                start = span.start + found
                end = start + len(needle)
                if source[start:end].casefold() == folded_needle:
                    values.append((start, end))
                cursor = found + 1
        return tuple(values)

    @classmethod
    def _event_excerpt(cls, event: EventFrame, source_text: str) -> str:
        """Build the shortest excerpt containing the event predicate and roles."""
        for span in event.evidence_spans:
            span.validate_source(source_text)
        required = (
            event.predicate_surface,
            *(argument.mention.text for argument in event.arguments),
        )
        occurrence_sets = tuple(
            cls._occurrences(source_text, value, event.evidence_spans)
            for value in required
        )
        if any(not values for values in occurrence_sets):
            raise V3ActionPlanningError("event_evidence_incomplete", "evidence")

        best: tuple[int, int] | None = None
        for predicate_start, predicate_end in occurrence_sets[0]:
            selected = [(predicate_start, predicate_end)]
            for alternatives in occurrence_sets[1:]:
                selected.append(
                    min(
                        alternatives,
                        key=lambda item: min(
                            abs(item[0] - predicate_start),
                            abs(item[1] - predicate_end),
                        ),
                    )
                )
            start = min(item[0] for item in selected)
            end = max(item[1] for item in selected)
            if best is None or end - start < best[1] - best[0]:
                best = (start, end)
        if best is None:
            raise V3ActionPlanningError("event_evidence_incomplete", "evidence")
        excerpt = source_text[best[0]:best[1]].strip()
        if not excerpt or len(excerpt) > 300:
            raise V3ActionPlanningError("event_evidence_out_of_bounds", "evidence")
        return excerpt

    @staticmethod
    def _references(
        candidate: GameplayActionCandidate,
        additional_references: tuple[GameplayResolvedReference, ...],
        visible_world,
    ) -> tuple[tuple[ResolvedConversationReference, ...], dict[str, str]]:
        resolved: list[ResolvedConversationReference] = []
        by_mention: dict[str, str] = {}
        by_mention_identity: dict[str, tuple[int, str]] = {}
        seen_references: set[tuple[str, int]] = set()
        all_references = (*candidate.resolved_references, *additional_references)
        for reference in all_references:
            if (
                reference.category is not GameplayResolvedReferenceKind.ENTITY
                or isinstance(reference.referent_id, bool)
                or not isinstance(reference.referent_id, int)
            ):
                raise V3ActionPlanningError(
                    "unsupported_reference_category",
                    "reference_mapping",
                )
            entity = visible_world.entities.get(reference.referent_id)
            if (
                entity is None
                or not entity.active
                or entity.id != reference.referent_id
                or entity.name != reference.name
            ):
                raise V3ActionPlanningError(
                    "canonical_reference_not_visible",
                    "reference_mapping",
                )
            mention = reference.mention.text.strip()
            key = mention.casefold()
            previous = by_mention.get(key)
            identity = (key, reference.referent_id)
            if previous is not None and (
                previous != reference.name
                or by_mention_identity[key][0] != reference.referent_id
            ):
                raise V3ActionPlanningError(
                    "conflicting_reference_mentions",
                    "reference_mapping",
                )
            if identity in seen_references:
                continue
            by_mention[key] = reference.name
            by_mention_identity[key] = (reference.referent_id, reference.name)
            seen_references.add(identity)
            resolved.append(
                ResolvedConversationReference(
                    mention=mention,
                    entity_id=reference.referent_id,
                    entity_name=reference.name,
                    match_kind="v3_action_checkpoint",
                )
            )
        return tuple(resolved), by_mention

    @staticmethod
    def _analysis(
        candidate: GameplayActionCandidate,
        event: EventFrame,
        act: UtteranceAct,
        evidence_excerpt: str,
    ) -> tuple[PlayerIntentAnalysis, tuple[str, ...]]:
        if act.speaker_role is not SpeakerRole.PLAYER:
            raise V3ActionPlanningError("event_not_player_scoped", "lowering")
        event_agents = {
            argument.mention.text.strip().casefold()
            for argument in event.arguments
            if argument.role.value == "agent"
        }
        if candidate.actor.text.strip().casefold() not in event_agents:
            raise V3ActionPlanningError("candidate_actor_mismatch", "lowering")

        targets = tuple(
            dict.fromkeys(
                mention.text
                for mention in candidate.target_mentions
                if mention.text.strip().casefold() in evidence_excerpt.casefold()
            )
        )
        external_mentions = tuple(
            dict.fromkeys(
                mention.text
                for mention in candidate.target_mentions
                if mention.text.strip().casefold() not in evidence_excerpt.casefold()
            )
        )
        is_dialogue = candidate.workflow is GameplayWorkflow.DIALOGUE
        step = IntentStep(
            index=0,
            source_excerpt=evidence_excerpt,
            actor=IntentActor.PLAYER,
            action=event.predicate_surface,
            modality=(
                IntentModality.DIALOGUE
                if is_dialogue
                else IntentModality.ATTEMPTED
            ),
            polarity=IntentPolarity.POSITIVE,
            reported_outcome=PlayerReportedOutcome.NOT_CLAIMED,
            target_mentions=targets,
            action_frame=SemanticActionFrame(
                predicate=event.predicate_surface,
                family=event.family,
                arguments=event.arguments,
            ),
        )
        return (
            PlayerIntentAnalysis(
                category=(
                    UtteranceCategory.DIALOGUE
                    if is_dialogue
                    else UtteranceCategory.ACTION
                ),
                steps=(step,),
                active_step_index=None if is_dialogue else 0,
                schema_version=2,
            ),
            external_mentions,
        )

    def prepare_next_action(
        self,
        resolver: TurnResolutionService,
        preview: V3ActionPreviewResult,
        context: TurnContext,
        player_input: str,
        *,
        recent_turns: list[TurnRecord] | None = None,
        manual_mode: bool = False,
    ) -> V3ActionPlanningResult:
        """Prepare only the next eligible action; never call the v3 interpreter."""
        if not isinstance(resolver, TurnResolutionService):
            raise TypeError("resolver must be a TurnResolutionService")
        if not isinstance(preview, V3ActionPreviewResult):
            raise TypeError("preview must be a V3ActionPreviewResult")
        if not isinstance(context, TurnContext):
            raise TypeError("context must be a TurnContext")
        if not isinstance(player_input, str) or not player_input.strip():
            raise ValueError("player_input must not be empty")
        if recent_turns is not None and (
            not isinstance(recent_turns, list)
            or any(not isinstance(item, TurnRecord) for item in recent_turns)
        ):
            raise TypeError("recent_turns must contain TurnRecord values")
        if not isinstance(manual_mode, bool):
            raise TypeError("manual_mode must be a boolean")

        selection = select_next_action(preview.checkpoint)
        if (
            selection.status is not ActionSelectionStatus.READY
            or selection.candidate is None
        ):
            raise V3ActionPlanningError(
                f"selection_{selection.status.value}",
                "selection",
            )
        candidate = selection.candidate
        if candidate.eligibility is not GameplayActionEligibility.ELIGIBLE:
            raise V3ActionPlanningError("selected_action_not_eligible", "selection")

        interpretation = preview.interpretation
        projection = preview.visible_projection
        if interpretation is None:
            raise V3ActionPlanningError("interpretation_not_available", "recovery")
        if not isinstance(projection, WorldContextProjection):
            raise V3ActionPlanningError("visible_projection_unavailable", "planning")

        event = next(
            (
                item for item in interpretation.events
                if item.local_id == candidate.source_event_id
            ),
            None,
        )
        if event is None:
            raise V3ActionPlanningError("selected_event_missing", "selection")
        act = next(
            (
                item for item in interpretation.utterance_acts
                if item.local_id == event.source_act_id
            ),
            None,
        )
        if act is None:
            raise V3ActionPlanningError("event_source_act_missing", "selection")

        active_character = context.active_character
        active_character_id = (
            getattr(active_character, "entity_id", None)
            if active_character is not None
            else None
        )
        actor_reference = next(
            (
                item for item in candidate.resolved_references
                if item.mention.text.strip().casefold()
                == candidate.actor.text.strip().casefold()
            ),
            None,
        )
        if (
            isinstance(active_character_id, bool)
            or not isinstance(active_character_id, int)
            or actor_reference is None
            or actor_reference.category is not GameplayResolvedReferenceKind.ENTITY
            or actor_reference.referent_id != active_character_id
        ):
            raise V3ActionPlanningError(
                "controlled_actor_not_verified",
                "reference_mapping",
            )

        evidence_excerpt = self._event_excerpt(event, player_input)
        analysis, external_mentions = self._analysis(
            candidate,
            event,
            act,
            evidence_excerpt,
        )
        event_reference_resolution = (
            preview.reference_resolutions.get(candidate.source_event_id)
            if preview.reference_resolutions is not None
            else None
        )
        supplemental_references = (
            event_reference_resolution.resolved_targets
            if event_reference_resolution is not None
            else ()
        )
        references, references_by_mention = self._references(
            candidate,
            supplemental_references,
            projection.world,
        )
        unresolved_external = tuple(
            mention
            for mention in external_mentions
            if mention.strip().casefold() not in references_by_mention
        )
        if unresolved_external:
            raise V3ActionPlanningError(
                "callback_reference_not_resolved",
                "reference_mapping",
            )

        plan = resolver.prepare_turn(
            context,
            evidence_excerpt,
            manual_mode=manual_mode,
            recent_turns=recent_turns,
            intent_analysis_override=analysis,
            intent_evidence_text=evidence_excerpt,
            context_projection_override=projection,
            resolved_references_override=references,
            additional_resolved_reference_mentions=external_mentions,
        )
        # Planning and proposal saw only this event's evidence. Restore the
        # original full utterance for durable request identity and transcript.
        plan = replace(
            plan,
            player_input=player_input.strip(),
            intent_evidence_text=player_input.strip(),
        )
        return V3ActionPlanningResult(
            candidate=candidate,
            event=event,
            intent_analysis=analysis,
            evidence_excerpt=evidence_excerpt,
            resolved_references=references,
            additional_reference_mentions=external_mentions,
            plan=plan,
        )
