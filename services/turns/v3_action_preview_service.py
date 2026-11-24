"""Opt-in v3 semantic preview for durable turn planning.

The service builds a backend action checkpoint and, when separately enabled,
evaluates world-fact candidates into durable receipts and typed operations.
It never commits state or adjudicates mechanics.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from models.player_action_checkpoint import (
    FactValidationReceipt,
    PlayerActionCheckpoint,
)
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
    GameplayActionCandidate,
    GameplayActionEligibility,
    GameplayActionReason,
    GameplayProcessingState,
    GameplayResolvedReference,
    GameplayResolvedReferenceKind,
    GameplayUnlockCondition,
    GameplayWorkflow,
    SpeakerRole,
    TurnInterpretationV3,
    TurnInterpretationV3ValidationError,
)
from models.resolved_conversation_reference import (
    ResolvedConversationGroupReference,
    ResolvedConversationReference,
)
from models.semantic_frames import SemanticActionFrame, SemanticMention
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from operations.world_operations import WorldOperation
from services.context import ContextBuilder, ConversationReferenceResolver
from services.context.entity_reference_resolver import EntityReferenceResolver
from services.turns.intent_interpreter import IntentInterpreter
from services.turns.player_action_selector import (
    ActionReferenceResolution,
    ActionSelection,
    ActionSelectorError,
    action_reference_mentions,
    build_action_checkpoint,
    select_next_action,
)
from services.turns.player_turn_v3_prompt import (
    V3_RESPONSE_SCHEMA,
    EvidenceSpanAlignmentError,
    align_v3_evidence_span_offsets,
    build_v3_shadow_prompt,
)
from services.turns.world_fact_policy import (
    FactDecision,
    FactDecisionStatus,
    FactEndpointResolution,
    evaluate_world_facts,
)


class V3ActionPreviewError(RuntimeError):
    """Content-free failure while preparing the opt-in v3 action preview."""

    def __init__(self, code: str, stage: str) -> None:
        self.code = code
        self.stage = stage
        super().__init__(f"v3 action preview failed ({stage}:{code})")


@dataclass(frozen=True, slots=True)
class V3ActionPreviewResult:
    checkpoint: PlayerActionCheckpoint
    selection: ActionSelection
    event_count: int
    excluded_event_count: int
    fact_candidate_count: int = 0
    fact_accepted_count: int = 0
    fact_already_present_count: int = 0
    fact_pending_count: int = 0
    fact_rejected_count: int = 0
    world_fact_operations: tuple[WorldOperation, ...] = ()
    interpretation: TurnInterpretationV3 | None = None
    visible_projection: object | None = None
    reference_resolutions: dict[str, ActionReferenceResolution] | None = None


class V3ActionPreviewService:
    """Interpret one turn with v3 and derive one safe action focus.

    The model supplies only evidence-bound semantic records. The preview
    resolves entity mentions against a bounded visible-world projection and
    delegates eligibility/dependency decisions to the existing deterministic
    selector. Its result is diagnostic and is not passed to mechanics or writes.
    """

    # Only first-person singular is safely identical to the controlled actor.
    # Plural agents and possessives must go through canonical resolution.
    _FIRST_PERSON_ACTOR_FORMS = frozenset({"yo", "me"})

    def __init__(
        self,
        intent_interpreter: IntentInterpreter,
        context_builder: ContextBuilder,
        *,
        max_context_bytes: int = 4096,
        reference_resolver: EntityReferenceResolver | None = None,
        conversation_reference_resolver: ConversationReferenceResolver | None = None,
        world_facts_enabled: bool = False,
    ) -> None:
        if not isinstance(intent_interpreter, IntentInterpreter):
            raise TypeError("intent_interpreter must be an IntentInterpreter")
        if not isinstance(context_builder, ContextBuilder):
            raise TypeError("context_builder must be a ContextBuilder")
        if (
            isinstance(max_context_bytes, bool)
            or not isinstance(max_context_bytes, int)
            or max_context_bytes <= 0
        ):
            raise ValueError("max_context_bytes must be a positive integer")
        if reference_resolver is not None and not isinstance(
            reference_resolver, EntityReferenceResolver
        ):
            raise TypeError("reference_resolver must be an EntityReferenceResolver")
        if conversation_reference_resolver is not None and not isinstance(
            conversation_reference_resolver, ConversationReferenceResolver
        ):
            raise TypeError(
                "conversation_reference_resolver must be a ConversationReferenceResolver"
            )
        self.intent_interpreter = intent_interpreter
        self.context_builder = context_builder
        self.max_context_bytes = max_context_bytes
        if not isinstance(world_facts_enabled, bool):
            raise TypeError("world_facts_enabled must be a boolean")
        self.reference_resolver = reference_resolver or EntityReferenceResolver()
        self.conversation_reference_resolver = (
            conversation_reference_resolver or ConversationReferenceResolver(self.reference_resolver)
        )
        self.world_facts_enabled = world_facts_enabled

    def _interpret(
        self,
        context: TurnContext,
        player_input: str,
        recent_turns: list[TurnRecord] | None,
    ) -> TurnInterpretationV3:
        try:
            v2_prompt, _sizes = self.intent_interpreter._build_prompt(
                context,
                player_input,
                recent_turns=recent_turns,
                evidence_text=player_input,
            )
            prompt = build_v3_shadow_prompt(
                v2_prompt,
                expected_evidence=player_input,
                max_prompt_bytes=self.intent_interpreter.max_prompt_bytes,
            )
        except Exception:  # noqa: BLE001 - expose only a safe preview-stage error
            raise V3ActionPreviewError("prompt_construction_failed", "prompt") from None

        try:
            raw = self.intent_interpreter.provider.generate_structured(
                prompt,
                schema=V3_RESPONSE_SCHEMA,
            )
        except Exception:  # noqa: BLE001 - expose only a safe provider-stage error
            raise V3ActionPreviewError("provider_error", "provider") from None
        if not isinstance(raw, str):
            raise V3ActionPreviewError("provider_returned_non_text", "provider")

        try:
            aligned, _realigned = align_v3_evidence_span_offsets(
                raw,
                source_text=player_input,
            )
            return TurnInterpretationV3.from_json(
                aligned,
                source_text=player_input,
            )
        except EvidenceSpanAlignmentError as exc:
            raise V3ActionPreviewError(exc.code, "evidence_alignment") from None
        except TurnInterpretationV3ValidationError as exc:
            raise V3ActionPreviewError(exc.code, "schema_validation") from None
        except Exception:  # noqa: BLE001 - keep decoder errors content-free
            raise V3ActionPreviewError("decoder_error", "schema_validation") from None

    def _visible_world(
        self,
        context: TurnContext,
        interpretation: TurnInterpretationV3,
        player_input: str,
        active_character_id: int,
        *,
        additional_queries: tuple[str, ...] = (),
    ):
        queries: list[str] = []
        for event in interpretation.events:
            for argument in event.arguments:
                queries.append(argument.mention.text)
        for act in interpretation.utterance_acts:
            if act.addressee_mention is not None:
                queries.append(act.addressee_mention.text)
        # Facts are independent of action frames. Their endpoints must be
        # requested explicitly so the bounded visible projection can resolve
        # them without broadening to the entire campaign world.
        for fact in interpretation.world_facts:
            queries.append(fact.subject.text)
            if fact.object is not None:
                queries.append(fact.object.text)
        for link in interpretation.discourse_links:
            if link.link_type.value == "callback" and link.anchor_candidate is not None:
                queries.append(link.anchor_candidate)
        queries.extend(additional_queries)
        normalized_queries = tuple(dict.fromkeys(
            value.strip()[:120]
            for value in queries
            if isinstance(value, str) and value.strip()
        ))[:64]
        mandatory_ids = [active_character_id]
        current_location_id = getattr(context.campaign, "current_location_id", None)
        if (
            isinstance(current_location_id, int)
            and not isinstance(current_location_id, bool)
            and current_location_id > 0
            and current_location_id not in mandatory_ids
        ):
            mandatory_ids.append(current_location_id)
        try:
            projection = self.context_builder.build_proposal_context(
                context.world,
                player_input,
                max_estimated_bytes=self.max_context_bytes,
                mandatory_entity_ids=mandatory_ids,
                supplemental_queries=normalized_queries,
                character_entity_id=active_character_id,
            )
        except Exception:  # noqa: BLE001 - context errors must fail closed
            raise V3ActionPreviewError("visible_context_failed", "reference_resolution") from None

        active_entity = projection.world.entities.get(active_character_id)
        if (
            active_entity is None
            or not active_entity.active
            or active_entity.id != active_character_id
        ):
            raise V3ActionPreviewError(
                "active_character_not_visible",
                "reference_resolution",
            )
        return projection

    def _resolved_reference(
        self,
        world,
        mention: SemanticMention,
        *,
        active_character_id: int,
        actor: bool,
        player_is_speaker: bool = False,
    ) -> tuple[GameplayResolvedReference | None, bool]:
        normalized = self.reference_resolver.normalize(mention.text)
        if actor and normalized in self._FIRST_PERSON_ACTOR_FORMS:
            if not player_is_speaker:
                return None, False
            entity = world.entities.get(active_character_id)
            if entity is not None and entity.active and entity.id == active_character_id:
                return (
                    GameplayResolvedReference(
                        mention=mention,
                        category=GameplayResolvedReferenceKind.ENTITY,
                        referent_id=active_character_id,
                        name=entity.name,
                    ),
                    False,
                )

        result = self.reference_resolver.resolve(world, mention.text)
        if result.status == "ambiguous":
            return None, True
        if result.status != "resolved" or len(result.candidates) != 1:
            return None, False
        candidate = result.candidates[0]
        entity = world.entities.get(candidate.entity_id)
        if (
            entity is None
            or not entity.active
            or entity.id != candidate.entity_id
        ):
            return None, False
        return (
            GameplayResolvedReference(
                mention=mention,
                category=GameplayResolvedReferenceKind.ENTITY,
                referent_id=candidate.entity_id,
                name=entity.name,
            ),
            False,
        )

    def _fact_endpoint_reference(
        self,
        world,
        mention: SemanticMention,
    ) -> ResolvedConversationReference | None:
        """Resolve one fact endpoint only against the bounded visible world."""
        resolution = self.reference_resolver.resolve(world, mention.text)
        if resolution.status != "resolved" or len(resolution.candidates) != 1:
            return None
        candidate = resolution.candidates[0]
        entity = world.entities.get(candidate.entity_id)
        if (
            entity is None
            or not entity.active
            or entity.id != candidate.entity_id
        ):
            return None
        return ResolvedConversationReference(
            mention=mention.text,
            entity_id=candidate.entity_id,
            entity_name=entity.name,
            match_kind=candidate.match_kind,
        )

    def _fact_endpoint_resolutions(
        self,
        interpretation: TurnInterpretationV3,
        world,
    ) -> dict[str, FactEndpointResolution]:
        resolutions: dict[str, FactEndpointResolution] = {}
        for fact in interpretation.world_facts:
            resolutions[fact.local_id] = FactEndpointResolution(
                subject_reference=self._fact_endpoint_reference(
                    world, fact.subject
                ),
                object_reference=(
                    self._fact_endpoint_reference(world, fact.object)
                    if fact.object is not None
                    else None
                ),
            )
        return resolutions

    def _callback_mentions(
        self,
        interpretation: TurnInterpretationV3,
    ) -> dict[str, tuple[SemanticMention, ...]]:
        by_event: dict[str, dict[str, SemanticMention]] = {}
        for link in interpretation.discourse_links:
            if link.link_type.value != "callback" or link.anchor_candidate is None:
                continue
            if not link.source_ref.startswith("event:"):
                continue
            mention = SemanticMention(link.anchor_candidate)
            key = mention.text.strip().casefold()
            if not key:
                continue
            event_id = link.source_ref.removeprefix("event:")
            by_event.setdefault(event_id, {}).setdefault(key, mention)
        return {
            event_id: tuple(mentions.values())
            for event_id, mentions in by_event.items()
        }

    @staticmethod
    def _callback_analysis(
        event,
        callback_mentions: tuple[SemanticMention, ...],
    ) -> PlayerIntentAnalysis:
        targets = tuple(
            item.mention for item in event.arguments
            if item.role.value in {
                "patient", "theme", "recipient", "source", "destination",
                "instrument", "location", "path", "beneficiary", "companion",
                "experiencer", "owner", "holder", "container",
            }
        )
        mentions = tuple(dict.fromkeys((*targets, *callback_mentions)))
        evidence = " ".join(span.text for span in event.evidence_spans)
        dialogue = event.family.value in {"communication", "social"}
        step = IntentStep(
            index=0,
            source_excerpt=evidence,
            actor=IntentActor.PLAYER,
            action=event.predicate_surface,
            modality=IntentModality.DIALOGUE if dialogue else IntentModality.ATTEMPTED,
            polarity=(
                IntentPolarity.POSITIVE
                if event.polarity.value == "positive"
                else IntentPolarity.NEGATIVE
            ),
            reported_outcome=PlayerReportedOutcome.NOT_CLAIMED,
            target_mentions=tuple(item.text for item in mentions),
            action_frame=SemanticActionFrame(
                predicate=event.predicate_surface,
                family=event.family,
                arguments=event.arguments,
            ),
        )
        category = UtteranceCategory.DIALOGUE if dialogue else UtteranceCategory.ACTION
        return PlayerIntentAnalysis(
            category=category,
            steps=(step,),
            active_step_index=None if dialogue else 0,
            schema_version=2,
        )

    def _reference_resolutions(
        self,
        interpretation: TurnInterpretationV3,
        world,
        active_character_id: int,
        *,
        recent_turns: list[TurnRecord] | None = None,
        player_input: str = "",
    ) -> dict[str, ActionReferenceResolution]:
        acts = {item.local_id: item for item in interpretation.utterance_acts}
        callback_mentions = self._callback_mentions(interpretation)
        resolutions: dict[str, ActionReferenceResolution] = {}
        for event in interpretation.events:
            act = acts.get(event.source_act_id)
            if act is None:
                raise V3ActionPreviewError(
                    "event_source_act_missing",
                    "reference_resolution",
                )
            actor_mention, targets = action_reference_mentions(event, act)
            if actor_mention is None:
                # The selector will exclude events without one unambiguous agent.
                continue
            actor_reference, actor_ambiguous = self._resolved_reference(
                world,
                actor_mention,
                active_character_id=active_character_id,
                actor=True,
                player_is_speaker=act.speaker_role is SpeakerRole.PLAYER,
            )
            resolved_targets: list[GameplayResolvedReference] = []
            unresolved_targets: list[SemanticMention] = []
            ambiguous_targets: list[SemanticMention] = []
            direct_target_keys = {
                item.text.strip().casefold() for item in targets
            }
            extra_targets = tuple(
                item
                for item in callback_mentions.get(event.local_id, ())
                if item.text.strip().casefold() not in direct_target_keys
            ) if act.speaker_role is SpeakerRole.PLAYER else ()
            callback_references = ()
            if extra_targets:
                try:
                    callback_result = self.conversation_reference_resolver.resolve(
                        world,
                        self._callback_analysis(event, extra_targets),
                        recent_turns=recent_turns or [],
                        current_input=player_input,
                    )
                    callback_references = callback_result.references
                except Exception:  # noqa: BLE001 - callbacks fail closed
                    callback_references = ()
            for target in targets:
                reference, ambiguous = self._resolved_reference(
                    world,
                    target,
                    active_character_id=active_character_id,
                    actor=False,
                )
                if reference is not None:
                    resolved_targets.append(reference)
                elif ambiguous:
                    ambiguous_targets.append(target)
                else:
                    unresolved_targets.append(target)
            for target in extra_targets:
                matches = [
                    item for item in callback_references
                    if item.mention.strip().casefold() == target.text.strip().casefold()
                ]
                if len(matches) == 1 and isinstance(matches[0], ResolvedConversationReference):
                    match = matches[0]
                    entity = world.entities.get(match.entity_id)
                    if entity is not None and entity.active and entity.id == match.entity_id:
                        resolved_targets.append(
                            GameplayResolvedReference(
                                mention=target,
                                category=GameplayResolvedReferenceKind.ENTITY,
                                referent_id=match.entity_id,
                                name=entity.name,
                            )
                        )
                    else:
                        unresolved_targets.append(target)
                elif any(isinstance(item, ResolvedConversationGroupReference) for item in matches) or len(matches) > 1:
                    ambiguous_targets.append(target)
                else:
                    unresolved_targets.append(target)
            resolutions[event.local_id] = ActionReferenceResolution(
                actor_reference=actor_reference,
                actor_ambiguous=actor_ambiguous,
                visibility_verified=True,
                resolved_targets=tuple(resolved_targets),
                unresolved_targets=tuple(unresolved_targets),
                ambiguous_targets=tuple(ambiguous_targets),
                extra_target_mentions=tuple(extra_targets),
            )
        return resolutions

    @staticmethod
    def _validate_restored_candidate_references(
        candidate: GameplayActionCandidate,
        baseline: GameplayActionCandidate,
        world,
        active_character_id: int,
    ) -> None:
        """Validate stored backend references while allowing clarified targets.

        Action identity is immutable across a clarification, but target
        mentions and their canonical bindings may legitimately be enriched.
        Checkpoint CAS enforces that this can happen only from AWAITING_INPUT;
        recovery independently verifies every stored binding against the
        current bounded visible-world projection.
        """
        if (
            candidate.local_id != baseline.local_id
            or candidate.actor != baseline.actor
            or candidate.action_type != baseline.action_type
            or candidate.dependency_event_ids != baseline.dependency_event_ids
        ):
            raise ValueError("stored action identity differs from its interpretation")

        stored_references = set(candidate.resolved_references)
        if not set(baseline.resolved_references).issubset(stored_references):
            raise ValueError("stored action discarded an original canonical reference")

        target_keys = {
            item.text.strip().casefold()
            for item in candidate.target_mentions
        }
        original_target_reference_keys = {
            item.mention.text.strip().casefold()
            for item in baseline.resolved_references
            if item.mention.text.strip().casefold()
            != baseline.actor.text.strip().casefold()
        }
        actor_key = candidate.actor.text.strip().casefold()
        actor_references = []
        for reference in candidate.resolved_references:
            if reference.category is not GameplayResolvedReferenceKind.ENTITY:
                raise ValueError("stored action reference has an unsupported category")
            entity = world.entities.get(reference.referent_id)
            if (
                entity is None
                or not entity.active
                or entity.id != reference.referent_id
                or entity.name != reference.name
            ):
                raise ValueError("stored action reference is no longer visible and active")

            mention_key = reference.mention.text.strip().casefold()
            if mention_key == actor_key:
                if reference.referent_id != active_character_id:
                    raise ValueError("stored player actor reference changed identity")
                actor_references.append(reference)
            elif (
                mention_key not in target_keys
                and mention_key not in original_target_reference_keys
            ):
                raise ValueError("stored target reference is not bound to a target mention")

        if len(actor_references) > 1:
            raise ValueError("stored action has more than one canonical player actor")
        if (
            candidate.eligibility
            in {
                GameplayActionEligibility.ELIGIBLE,
                GameplayActionEligibility.BLOCKED_BY_DEPENDENCY,
            }
            and len(actor_references) != 1
        ):
            raise ValueError("executable action is missing its canonical player actor")

    def restore(
        self,
        checkpoint: PlayerActionCheckpoint,
        context: TurnContext,
        player_input: str,
        *,
        recent_turns: list[TurnRecord] | None = None,
    ) -> V3ActionPreviewResult:
        """Rebuild trusted runtime references from a persisted interpretation.

        No LLM call is made. Stored canonical references are checked against
        the same visible snapshot before a checkpoint may resume.
        """
        if not isinstance(checkpoint, PlayerActionCheckpoint):
            raise TypeError("checkpoint must be a PlayerActionCheckpoint")
        if checkpoint.schema_version < 2 or checkpoint.interpretation_json is None:
            raise V3ActionPreviewError("legacy_checkpoint_not_resumable", "recovery")
        if checkpoint.source_sha256 != __import__("hashlib").sha256(
            player_input.encode("utf-8")
        ).hexdigest():
            raise V3ActionPreviewError("checkpoint_source_mismatch", "recovery")
        try:
            interpretation = TurnInterpretationV3.from_json(
                checkpoint.interpretation_json,
                source_text=player_input,
            )
        except TurnInterpretationV3ValidationError:
            raise V3ActionPreviewError("stored_interpretation_invalid", "recovery") from None
        active = context.active_character
        active_id = getattr(active, "entity_id", None) if active is not None else None
        if isinstance(active_id, bool) or not isinstance(active_id, int) or active_id < 1:
            raise V3ActionPreviewError("active_character_unavailable", "recovery")
        projection = self._visible_world(
            context, interpretation, player_input, active_id
        )
        world = projection.world
        try:
            resolutions = self._reference_resolutions(
                interpretation,
                world,
                active_id,
                recent_turns=recent_turns,
                player_input=player_input,
            )
            baseline = build_action_checkpoint(
                interpretation,
                resolution_id=checkpoint.resolution_id,
                context_revision=checkpoint.context_revision,
                source_text=player_input,
                active_character_id=active_id,
                reference_resolutions=resolutions,
                fact_validation_receipts=checkpoint.fact_validation_receipts,
            ).checkpoint
            expected = {
                node.candidate.source_event_id: node.candidate
                for node in baseline.nodes
            }
            stored = {
                node.candidate.source_event_id: node.candidate
                for node in checkpoint.nodes
            }
            if set(expected) != set(stored):
                raise ValueError("stored action graph differs from its interpretation")
            for event_id, candidate in expected.items():
                previous = stored[event_id]
                self._validate_restored_candidate_references(
                    previous,
                    candidate,
                    world,
                    active_id,
                )
        except Exception:  # noqa: BLE001 - recovery must fail closed
            raise V3ActionPreviewError("stored_references_invalid", "recovery") from None
        selection = select_next_action(checkpoint)
        return V3ActionPreviewResult(
            checkpoint=checkpoint,
            selection=selection,
            event_count=len(interpretation.events),
            excluded_event_count=len(interpretation.events) - len(checkpoint.nodes),
            interpretation=interpretation,
            visible_projection=projection,
            reference_resolutions=resolutions,
        )

    def resolve_target_clarification(
        self,
        preview: V3ActionPreviewResult,
        event_id: str,
        answer: str,
        *,
        context: TurnContext,
        player_input: str,
    ) -> tuple[V3ActionPreviewResult, GameplayActionCandidate, tuple[str, ...]]:
        """Resolve one pending target mention using only the current visible-world projection.

        The player's answer supplies a lookup query, never a canonical identifier.
        A unique active entity must be found by the visibility-aware resolver.
        The persisted candidate continues to bind the original event mention to
        that canonical entity, so the action text and evidence remain unchanged.
        """
        from models.player_action_checkpoint import ActionExecutionState

        if not isinstance(preview, V3ActionPreviewResult):
            raise TypeError("preview must be a V3ActionPreviewResult")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event_id must not be empty")
        if not isinstance(answer, str) or not answer.strip() or len(answer.strip()) > 500:
            raise ValueError("clarification answer must contain 1-500 characters")
        if not isinstance(context, TurnContext):
            raise TypeError("context must be a TurnContext")
        if not isinstance(player_input, str) or not player_input.strip():
            raise ValueError("player_input must not be empty")
        active_character = context.active_character
        active_character_id = (
            getattr(active_character, "entity_id", None)
            if active_character is not None
            else None
        )
        if (
            isinstance(active_character_id, bool)
            or not isinstance(active_character_id, int)
            or active_character_id < 1
        ):
            raise V3ActionPreviewError(
                "active_character_unavailable",
                "clarification",
            )
        interpretation = preview.interpretation
        if not isinstance(interpretation, TurnInterpretationV3):
            raise V3ActionPreviewError(
                "clarification_interpretation_unavailable",
                "clarification",
            )
        projection = self._visible_world(
            context,
            interpretation,
            player_input,
            active_character_id,
            additional_queries=(answer.strip(),),
        )
        node = next(
            (
                item for item in preview.checkpoint.nodes
                if item.candidate.source_event_id == event_id
            ),
            None,
        )
        if node is None or node.state is not ActionExecutionState.AWAITING_INPUT:
            raise V3ActionPreviewError(
                "clarification_action_not_pending",
                "clarification",
            )
        if set(node.clarification_slots) != {"target"}:
            raise V3ActionPreviewError(
                "unsupported_clarification_slots",
                "clarification",
            )
        resolution = (
            preview.reference_resolutions.get(event_id)
            if preview.reference_resolutions is not None
            else None
        )
        if not isinstance(resolution, ActionReferenceResolution):
            raise V3ActionPreviewError(
                "clarification_reference_state_unavailable",
                "clarification",
            )
        candidate = node.candidate
        unresolved = {
            item.text.strip().casefold()
            for item in (*resolution.unresolved_targets, *resolution.ambiguous_targets)
        }
        missing_mentions = tuple(
            item for item in candidate.target_mentions
            if item.text.strip().casefold() in unresolved
        )
        if not missing_mentions:
            raise V3ActionPreviewError(
                "clarification_target_not_missing",
                "clarification",
            )
        original_mention = missing_mentions[0]
        lookup = self.reference_resolver.resolve(
            projection.world,
            answer.strip(),
        )
        if lookup.status != "resolved" or len(lookup.candidates) != 1:
            raise V3ActionPreviewError(
                "clarification_answer_not_unique",
                "clarification",
            )
        match = lookup.candidates[0]
        if match.entity_id is None:
            raise V3ActionPreviewError(
                "clarification_answer_not_unique",
                "clarification",
            )
        entity = projection.world.entities.get(match.entity_id)
        if (
            entity is None
            or not entity.active
            or entity.id != match.entity_id
            or isinstance(entity.id, bool)
            or not isinstance(entity.id, int)
            or entity.id < 1
        ):
            raise V3ActionPreviewError(
                "clarification_entity_not_visible",
                "clarification",
            )
        if any(
            item.category is GameplayResolvedReferenceKind.ENTITY
            and item.referent_id == entity.id
            for item in candidate.resolved_references
        ):
            raise V3ActionPreviewError(
                "clarification_entity_already_bound",
                "clarification",
            )
        bound_reference = GameplayResolvedReference(
            mention=original_mention,
            category=GameplayResolvedReferenceKind.ENTITY,
            referent_id=entity.id,
            name=entity.name,
        )
        updated_references = (*candidate.resolved_references, bound_reference)
        remaining_unresolved = tuple(
            item for item in resolution.unresolved_targets
            if item.text.strip().casefold() != original_mention.text.strip().casefold()
        )
        remaining_ambiguous = tuple(
            item for item in resolution.ambiguous_targets
            if item.text.strip().casefold() != original_mention.text.strip().casefold()
        )
        remaining_slots = (
            ("target",)
            if remaining_unresolved or remaining_ambiguous
            else ()
        )
        if remaining_slots:
            eligibility = GameplayActionEligibility.REQUIRES_CLARIFICATION
            reason = (
                GameplayActionReason.AMBIGUOUS_REFERENCE
                if remaining_ambiguous
                else GameplayActionReason.UNRESOLVED_REFERENCE
            )
            workflow = GameplayWorkflow.CLARIFICATION
            unlock_condition = candidate.unlock_condition
            processing_state = GameplayProcessingState.AWAITING_INPUT
        elif candidate.dependency_event_ids:
            eligibility = GameplayActionEligibility.BLOCKED_BY_DEPENDENCY
            reason = GameplayActionReason.DEPENDENCY_PENDING
            workflow = (
                GameplayWorkflow.DIALOGUE
                if candidate.action_type in {"communication", "social"}
                else GameplayWorkflow.MECHANICS
            )
            unlock_condition = GameplayUnlockCondition.DEPENDENCY_SUCCESS
            processing_state = GameplayProcessingState.PENDING
        else:
            eligibility = GameplayActionEligibility.ELIGIBLE
            reason = GameplayActionReason.ELIGIBLE
            workflow = (
                GameplayWorkflow.DIALOGUE
                if candidate.action_type in {"communication", "social"}
                else GameplayWorkflow.MECHANICS
            )
            unlock_condition = candidate.unlock_condition
            processing_state = GameplayProcessingState.PENDING

        updated_candidate = replace(
            candidate,
            eligibility=eligibility,
            reason=reason,
            workflow=workflow,
            unlock_condition=unlock_condition,
            processing_state=processing_state,
            resolved_references=updated_references,
        )
        updated_resolution = replace(
            resolution,
            resolved_targets=(*resolution.resolved_targets, bound_reference),
            unresolved_targets=remaining_unresolved,
            ambiguous_targets=remaining_ambiguous,
            visibility_verified=True,
        )
        updated_map = dict(preview.reference_resolutions or {})
        updated_map[event_id] = updated_resolution
        updated_preview = replace(
            preview,
            visible_projection=projection,
            reference_resolutions=updated_map,
        )
        return updated_preview, updated_candidate, remaining_slots

    def action_clarification_question(
        self,
        preview: V3ActionPreviewResult,
        event_id: str,
        clarification_slots: tuple[str, ...],
    ) -> str:
        """Produce a bounded, neutral question from one unresolved backend mention."""
        if not isinstance(preview, V3ActionPreviewResult):
            raise TypeError("preview must be a V3ActionPreviewResult")
        node = next(
            (
                item for item in preview.checkpoint.nodes
                if item.candidate.source_event_id == event_id
            ),
            None,
        )
        if node is None or set(clarification_slots) != {"target"}:
            raise V3ActionPreviewError(
                "unsupported_clarification_slots",
                "clarification",
            )
        resolution = (
            preview.reference_resolutions.get(event_id)
            if preview.reference_resolutions is not None
            else None
        )
        if not isinstance(resolution, ActionReferenceResolution):
            raise V3ActionPreviewError(
                "clarification_reference_state_unavailable",
                "clarification",
            )
        missing = (*resolution.unresolved_targets, *resolution.ambiguous_targets)
        if not missing:
            raise V3ActionPreviewError(
                "clarification_target_not_missing",
                "clarification",
            )
        mention = missing[0].text.strip()
        return (
            f"No he podido identificar con seguridad «{mention}». "
            "¿A qué persona u objeto te refieres?"
        )

    def preview(
        self,
        context: TurnContext,
        player_input: str,
        *,
        resolution_id: int,
        context_revision: int,
        recent_turns: list[TurnRecord] | None = None,
    ) -> V3ActionPreviewResult:
        if not isinstance(context, TurnContext):
            raise TypeError("context must be a TurnContext")
        if not isinstance(player_input, str) or not player_input.strip():
            raise ValueError("player_input must not be empty")
        active_character = context.active_character
        active_character_id = (
            getattr(active_character, "entity_id", None)
            if active_character is not None
            else None
        )
        if (
            isinstance(active_character_id, bool)
            or not isinstance(active_character_id, int)
            or active_character_id < 1
        ):
            raise V3ActionPreviewError(
                "active_character_unavailable",
                "reference_resolution",
            )

        interpretation = self._interpret(context, player_input, recent_turns)
        visible_projection = self._visible_world(
            context,
            interpretation,
            player_input,
            active_character_id,
        )
        visible_world = visible_projection.world
        try:
            resolutions = self._reference_resolutions(
                interpretation,
                visible_world,
                active_character_id,
                recent_turns=recent_turns,
                player_input=player_input,
            )
        except V3ActionPreviewError:
            raise
        except Exception:  # noqa: BLE001 - resolver errors must fail closed
            raise V3ActionPreviewError(
                "reference_resolution_failed",
                "reference_resolution",
            ) from None
        fact_decisions: tuple[FactDecision, ...] = ()
        fact_receipts: tuple[FactValidationReceipt, ...] = ()
        fact_operations: tuple[WorldOperation, ...] = ()
        if self.world_facts_enabled and interpretation.world_facts:
            try:
                fact_decisions = evaluate_world_facts(
                    interpretation,
                    visible_world,
                    self._fact_endpoint_resolutions(
                        interpretation,
                        visible_world,
                    ),
                )
                fact_receipts = tuple(
                    decision.to_receipt() for decision in fact_decisions
                )
                raw_fact_operations = tuple(
                    operation
                    for decision in fact_decisions
                    if decision.status is FactDecisionStatus.ACCEPTED
                    for operation in decision.operations
                )
                if any(
                    not isinstance(operation, WorldOperation)
                    for operation in raw_fact_operations
                ):
                    raise TypeError("world-fact policy returned a non-world operation")
                fact_operations = tuple(
                    operation
                    for operation in raw_fact_operations
                    if isinstance(operation, WorldOperation)
                )
            except Exception:  # noqa: BLE001 - optional fact preview fails closed
                raise V3ActionPreviewError(
                    "fact_policy_failed",
                    "fact_policy",
                ) from None

        try:
            built = build_action_checkpoint(
                interpretation,
                resolution_id=resolution_id,
                context_revision=context_revision,
                source_text=player_input,
                active_character_id=active_character_id,
                reference_resolutions=resolutions,
                fact_validation_receipts=fact_receipts,
            )
            selection = select_next_action(built.checkpoint)
        except (ActionSelectorError, TypeError, ValueError):
            raise V3ActionPreviewError("action_graph_rejected", "selection") from None

        status_counts = {
            status: sum(
                decision.status is status for decision in fact_decisions
            )
            for status in FactDecisionStatus
        }
        return V3ActionPreviewResult(
            checkpoint=built.checkpoint,
            selection=selection,
            event_count=len(interpretation.events),
            excluded_event_count=len(built.excluded_event_ids),
            fact_candidate_count=len(fact_decisions),
            fact_accepted_count=status_counts[FactDecisionStatus.ACCEPTED],
            fact_already_present_count=status_counts[FactDecisionStatus.ALREADY_PRESENT],
            fact_pending_count=status_counts[FactDecisionStatus.NEEDS_CLARIFICATION],
            fact_rejected_count=status_counts[FactDecisionStatus.REJECTED],
            world_fact_operations=fact_operations,
            interpretation=interpretation,
            visible_projection=visible_projection,
            reference_resolutions=resolutions,
        )
