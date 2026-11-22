"""Opt-in v3 semantic preview for durable turn planning.

The service builds a backend action checkpoint and, when separately enabled,
evaluates world-fact candidates into durable receipts and typed operations.
It never commits state or adjudicates mechanics.
"""
from __future__ import annotations

from dataclasses import dataclass

from models.player_action_checkpoint import PlayerActionCheckpoint
from models.player_turn_interpretation_v3 import (
    GameplayResolvedReference,
    GameplayResolvedReferenceKind,
    SpeakerRole,
    TurnInterpretationV3,
    TurnInterpretationV3ValidationError,
)
from models.resolved_conversation_reference import ResolvedConversationReference
from models.semantic_frames import SemanticMention
from services.turns.world_fact_policy import (
    FactDecisionStatus,
    FactEndpointResolution,
    evaluate_world_facts,
)
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from services.context import ContextBuilder
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
    world_fact_operations: tuple = ()


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
        self.intent_interpreter = intent_interpreter
        self.context_builder = context_builder
        self.max_context_bytes = max_context_bytes
        if not isinstance(world_facts_enabled, bool):
            raise TypeError("world_facts_enabled must be a boolean")
        self.reference_resolver = reference_resolver or EntityReferenceResolver()
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
    ):
        queries: list[str] = []
        for event in interpretation.events:
            for argument in event.arguments:
                queries.append(argument.mention.text)
        for act in interpretation.utterance_acts:
            if act.addressee_mention is not None:
                queries.append(act.addressee_mention.text)
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
        return projection.world

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

    def _reference_resolutions(
        self,
        interpretation: TurnInterpretationV3,
        world,
        active_character_id: int,
    ) -> dict[str, ActionReferenceResolution]:
        acts = {item.local_id: item for item in interpretation.utterance_acts}
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
            resolutions[event.local_id] = ActionReferenceResolution(
                actor_reference=actor_reference,
                actor_ambiguous=actor_ambiguous,
                visibility_verified=True,
                resolved_targets=tuple(resolved_targets),
                unresolved_targets=tuple(unresolved_targets),
                ambiguous_targets=tuple(ambiguous_targets),
            )
        return resolutions

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
        visible_world = self._visible_world(
            context,
            interpretation,
            player_input,
            active_character_id,
        )
        try:
            resolutions = self._reference_resolutions(
                interpretation,
                visible_world,
                active_character_id,
            )
        except V3ActionPreviewError:
            raise
        except Exception:  # noqa: BLE001 - resolver errors must fail closed
            raise V3ActionPreviewError(
                "reference_resolution_failed",
                "reference_resolution",
            ) from None
        try:
            built = build_action_checkpoint(
                interpretation,
                resolution_id=resolution_id,
                context_revision=context_revision,
                source_text=player_input,
                active_character_id=active_character_id,
                reference_resolutions=resolutions,
            )
            selection = select_next_action(built.checkpoint)
        except (ActionSelectorError, TypeError, ValueError):
            raise V3ActionPreviewError("action_graph_rejected", "selection") from None
        return V3ActionPreviewResult(
            checkpoint=built.checkpoint,
            selection=selection,
            event_count=len(interpretation.events),
            excluded_event_count=len(built.excluded_event_ids),
        )
