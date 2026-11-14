from __future__ import annotations

from dataclasses import dataclass, replace

from models.campaign_state import CampaignState
from models.mechanics import MechanicsDecision, MechanicsDecisionType, MechanicsResult
from models.pending_intent_correction import PendingIntentCorrection
from models.player_intent_analysis import PlayerIntentAnalysis
from models.resolved_conversation_reference import ResolvedConversationReference
from models.resolved_world_reference import ResolvedWorldReference
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.turn_resolution_result import TurnResolutionResult
from models.world_state import WorldState
from operations.character_operations import (
    CharacterOperation,
)
from operations.referenced_operation import ReferencedOperation
from operations.world_operations import WorldOperation
from rules_engine.dnd5e_2014.character_checks import (
    ability_check_for_character,
    raw_ability_check_for_character,
    saving_throw_for_character,
)
from rules_engine.dnd5e_2014.core.dice import DiceRoller
from services.context import (
    ContextBuilder,
    ConversationReferenceResolver,
    WorldReferenceResolver,
)
from services.context.discourse_context_builder import DiscourseContextBuilder
from services.llm_world import LLMWorldExtractor
from services.turns.dm_service import DMService
from services.turns.mechanics_adjudicator import (
    MechanicsAdjudicator,
    MechanicsAdjudicatorError,
)
from services.world import WorldService


@dataclass(frozen=True)
class TurnResolutionPlan:
    """Immutable result of the non-persistent planning phase."""

    player_input: str
    narrative: str
    world_operations: tuple
    character_operations: tuple
    ordered_operations: tuple
    mechanics_result: MechanicsResult | None = None
    clarification_question: str | None = None
    mechanics_decision: MechanicsDecision | None = None
    intent_analysis: PlayerIntentAnalysis | None = None
    intent_evidence_text: str | None = None
    awaiting_manual_roll: bool = False
    intent_corrections: tuple[PendingIntentCorrection, ...] = ()


class TurnResolutionServiceError(RuntimeError):
    """Failure while preparing or applying a turn-resolution plan."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class TurnResolutionService:
    """
    Prepara y aplica un turno en dos fases.

    prepare_turn():
        player intent -> deterministic mechanics + structured proposal
        -> immutable TurnResolutionPlan (without mutating state)

    apply_plan():
        TurnResolutionPlan + fresh context -> WorldService
        -> operation results

    generate_narrative():
        context + applied consequences -> DMService -> presentation

    resolve_turn() is a convenience sequence for non-durable callers.
    DurableNativeTurnService keeps commit and narration as separate phases.

    Responsabilidades:

    - validar WorldState
    - validar entrada del jugador
    - proponer consecuencias estructuradas desde la intención del jugador
    - generar narración después de aplicar las consecuencias
    - aplicar y persistir operaciones de forma consistente
        mediante WorldService
    - devolver TurnResolutionResult

    NO debe:

    - acceder directamente a WorldApplier
    - acceder a SQLite
    - persistir directamente
    - conocer Ollama
    - conocer el modelo LLM
    - construir prompts
    - interpretar JSON
    - implementar reglas de dominio
    - reconstruir el contexto después de resolver el turno
    """

    def __init__(
        self,
        dm_service: DMService,
        extractor: LLMWorldExtractor,
        world_service: WorldService,
        mechanics_adjudicator: MechanicsAdjudicator | None = None,
        dice_roller: DiceRoller | None = None,
        context_builder: ContextBuilder | None = None,
        proposal_context_max_tokens: int = 4096,
    ) -> None:

        if not isinstance(
            dm_service,
            DMService,
        ):
            raise TypeError(
                "dm_service must be a DMService"
            )

        if not isinstance(
            extractor,
            LLMWorldExtractor,
        ):
            raise TypeError(
                "extractor must be a LLMWorldExtractor"
            )

        if not isinstance(
            world_service,
            WorldService,
        ):
            raise TypeError(
                "world_service must be a WorldService"
            )

        if mechanics_adjudicator is not None and not isinstance(
            mechanics_adjudicator, MechanicsAdjudicator
        ):
            raise TypeError("mechanics_adjudicator must be a MechanicsAdjudicator or None")
        if dice_roller is not None and not isinstance(dice_roller, DiceRoller):
            raise TypeError("dice_roller must be a DiceRoller or None")
        if context_builder is not None and not isinstance(context_builder, ContextBuilder):
            raise TypeError("context_builder must be a ContextBuilder or None")
        if (
            isinstance(proposal_context_max_tokens, bool)
            or not isinstance(proposal_context_max_tokens, int)
            or proposal_context_max_tokens <= 0
        ):
            raise ValueError("proposal_context_max_tokens must be a positive integer")

        self.dm_service = dm_service
        self.extractor = extractor
        self.world_service = world_service
        self.mechanics_adjudicator = mechanics_adjudicator
        self.dice_roller = dice_roller or DiceRoller()
        self.context_builder = context_builder
        self.conversation_reference_resolver = ConversationReferenceResolver()
        self.world_reference_resolver = WorldReferenceResolver()
        self.proposal_context_max_tokens = proposal_context_max_tokens

    # ============================================================
    # PUBLIC API
    # ============================================================

    @staticmethod
    def _recent_context_queries(recent_turns: list[TurnRecord] | None) -> tuple[str, ...]:
        """Build bounded, player-visible retrieval signals for conversational references."""
        if not isinstance(recent_turns, list):
            return ()
        queries: list[str] = []
        seen: set[str] = set()
        # Retrieval and discourse resolution share one bounded history window.
        for item in recent_turns[-DiscourseContextBuilder.MAX_HISTORY_TURNS :]
            if isinstance(item, dict):
                values = (item.get("player_input", ""), item.get("narrative", ""))
            else:
                values = (
                    getattr(item, "player_input", ""),
                    getattr(item, "narrative", ""),
                )
            for value in values:
                if not isinstance(value, str):
                    continue
                normalized = value.strip()[:300]
                key = normalized.casefold()
                if normalized and key not in seen:
                    queries.append(normalized)
                    seen.add(key)
        return tuple(queries)

    def prepare_turn(
        self,
        turn_context: TurnContext | WorldState,
        player_input: str,
        *,
        manual_mode: bool = False,
        manual_rolls: tuple[int, ...] | None = None,
        decision_override: MechanicsDecision | None = None,
        intent_analysis_override: PlayerIntentAnalysis | None = None,
        recent_turns: list[TurnRecord] | None = None,
        intent_evidence_text: str | None = None,
        pending_intent_analysis: PlayerIntentAnalysis | None = None,
        pending_correction_evidence_text: str | None = None,
    ) -> TurnResolutionPlan:
        """
        Prepare a typed operation proposal from the player's intent.

        This phase performs no database access or state mutation.
        """
        if isinstance(turn_context, TurnContext):
            context = turn_context
        elif isinstance(turn_context, WorldState):
            context = TurnContext(
                campaign=CampaignState(),
                current_session=None,
                active_character=None,
                world=turn_context,
            )
        else:
            raise TypeError(
                "turn_context must be a TurnContext or WorldState"
            )

        self._validate_world(context.world)
        normalized_input = self._validate_player_input(player_input)
        if not normalized_input:
            raise TurnResolutionServiceError(
                "player_input must not be empty"
            )
        normalized_evidence_text = (
            normalized_input
            if intent_evidence_text is None
            else self._validate_player_input(intent_evidence_text)
        )
        if not normalized_evidence_text or len(normalized_evidence_text) > 20000:
            raise TurnResolutionServiceError(
                "intent evidence must contain 1 to 20000 characters"
            )

        if not isinstance(manual_mode, bool):
            raise TypeError("manual_mode must be a boolean")
        if decision_override is not None and not isinstance(
            decision_override, MechanicsDecision
        ):
            raise TypeError("decision_override must be a MechanicsDecision or None")
        if manual_rolls is not None and not isinstance(manual_rolls, tuple):
            raise TypeError("manual_rolls must be a tuple or None")
        if intent_analysis_override is not None and not isinstance(
            intent_analysis_override, PlayerIntentAnalysis
        ):
            raise TypeError(
                "intent_analysis_override must be a PlayerIntentAnalysis or None"
            )
        if recent_turns is not None and not isinstance(recent_turns, list):
            raise TypeError("recent_turns must be a list of TurnRecord values or None")
        if pending_intent_analysis is not None and not isinstance(
            pending_intent_analysis, PlayerIntentAnalysis
        ):
            raise TypeError("pending_intent_analysis must be a PlayerIntentAnalysis or None")
        if pending_intent_analysis is not None:
            if decision_override is not None or intent_analysis_override is not None:
                raise ValueError(
                    "pending semantic correction cannot be combined with interpretation overrides"
                )
            if (
                not isinstance(pending_correction_evidence_text, str)
                or not pending_correction_evidence_text.strip()
                or len(pending_correction_evidence_text) > 5000
            ):
                raise TurnResolutionServiceError(
                    "pending correction evidence must contain 1 to 5000 characters"
                )
        elif pending_correction_evidence_text is not None:
            raise ValueError(
                "pending_correction_evidence_text requires pending_intent_analysis"
            )

        mechanics_result = None
        decision = decision_override
        intent_analysis = intent_analysis_override
        intent_corrections: tuple[PendingIntentCorrection, ...] = ()
        if pending_intent_analysis is not None:
            if self.mechanics_adjudicator is None:
                raise TurnResolutionServiceError(
                    "pending correction requires the shared language adjudicator"
                )
            try:
                correction_result = self.mechanics_adjudicator.understand_pending(
                    context,
                    normalized_input,
                    pending_analysis=pending_intent_analysis,
                    correction_evidence_text=pending_correction_evidence_text or "",
                    recent_turns=recent_turns,
                    evidence_text=normalized_evidence_text,
                )
                corrected_analysis = pending_intent_analysis
                for correction in correction_result.corrections:
                    corrected_analysis = correction.apply(
                        corrected_analysis,
                        player_evidence_text=normalized_evidence_text,
                        resolution_pending=True,
                        committed=False,
                    )
                    if not correction.matches_analysis(correction_result.analysis):
                        raise ValueError(
                            "provider re-analysis does not reflect its explicit correction"
                        )
                intent_analysis = correction_result.analysis
                decision = correction_result.mechanics_decision
                intent_corrections = correction_result.corrections
            except (MechanicsAdjudicatorError, TypeError, ValueError) as exc:
                raise TurnResolutionServiceError(
                    "pending intent correction failed validation"
                ) from exc
        elif (
            intent_analysis is None
            and decision is None
            and self.mechanics_adjudicator is not None
        ):
            try:
                intent_analysis, inferred_decision = self.mechanics_adjudicator.understand(
                    context,
                    normalized_input,
                    recent_turns=recent_turns,
                    evidence_text=normalized_evidence_text,
                )
                if decision is None:
                    decision = inferred_decision
            except MechanicsAdjudicatorError as exc:
                raise TurnResolutionServiceError(
                    "shared language understanding failed"
                ) from exc
        elif intent_analysis is None:
            intent_analysis = PlayerIntentAnalysis.conservative_legacy(
                normalized_evidence_text
            )

        if intent_analysis.requires_clarification:
            return TurnResolutionPlan(
                player_input=normalized_input,
                narrative=intent_analysis.clarification_question or "",
                world_operations=(),
                character_operations=(),
                ordered_operations=(),
                clarification_question=intent_analysis.clarification_question,
                mechanics_decision=decision,
                intent_analysis=intent_analysis,
                intent_evidence_text=normalized_evidence_text,
                intent_corrections=intent_corrections,
            )
        if not intent_analysis.is_actionable and not (
            decision is not None
            and decision.decision is MechanicsDecisionType.CLARIFICATION
        ):
            decision = MechanicsDecision(decision=MechanicsDecisionType.NONE)

        if decision is not None:
            if decision.decision is MechanicsDecisionType.CLARIFICATION:
                return TurnResolutionPlan(
                    player_input=normalized_input,
                    narrative=decision.question or "",
                    world_operations=(),
                    character_operations=(),
                    ordered_operations=(),
                    clarification_question=decision.question,
                    mechanics_decision=decision,
                    intent_analysis=intent_analysis,
                    intent_evidence_text=normalized_evidence_text,
                    intent_corrections=intent_corrections,
                )

            character = context.active_character
            conditions = context.active_character_conditions
            if character is not None and decision.decision in {
                MechanicsDecisionType.ABILITY_CHECK,
                MechanicsDecisionType.SKILL_CHECK,
            }:
                decision = replace(
                    decision,
                    disadvantage=(
                        decision.disadvantage or conditions.ability_checks_have_disadvantage
                    ),
                )
            elif character is not None and decision.decision is MechanicsDecisionType.SAVING_THROW:
                decision = replace(
                    decision,
                    disadvantage=(
                        decision.disadvantage or conditions.saving_throws_have_disadvantage
                    ),
                )

            if manual_mode and manual_rolls is None and decision.decision in {
                MechanicsDecisionType.ABILITY_CHECK,
                MechanicsDecisionType.SKILL_CHECK,
                MechanicsDecisionType.SAVING_THROW,
            }:
                return TurnResolutionPlan(
                    player_input=normalized_input,
                    narrative="",
                    world_operations=(),
                    character_operations=(),
                    ordered_operations=(),
                    mechanics_decision=decision,
                    intent_analysis=intent_analysis,
                    intent_evidence_text=normalized_evidence_text,
                    intent_corrections=intent_corrections,
                    awaiting_manual_roll=True,
                )
            if decision.decision is MechanicsDecisionType.ABILITY_CHECK:
                if character is None or decision.ability is None or decision.dc is None:
                    raise TurnResolutionServiceError(
                        "ability check requires an active character, ability and DC"
                    )
                check = raw_ability_check_for_character(
                    character=character,
                    roller=self.dice_roller,
                    ability=decision.ability,
                    dc=decision.dc,
                    advantage=decision.advantage,
                    disadvantage=decision.disadvantage,
                    situational_modifier=decision.situational_modifier,
                    manual_rolls=manual_rolls,
                )
                mechanics_result = MechanicsResult(decision, check)
            elif decision.decision is MechanicsDecisionType.SKILL_CHECK:
                if character is None or decision.skill is None or decision.dc is None:
                    raise TurnResolutionServiceError(
                        "skill check requires an active character, skill and DC"
                    )
                check = ability_check_for_character(
                    character=character,
                    roller=self.dice_roller,
                    skill=decision.skill,
                    dc=decision.dc,
                    advantage=decision.advantage,
                    disadvantage=decision.disadvantage,
                    situational_modifier=decision.situational_modifier,
                    manual_rolls=manual_rolls,
                    ability_override=decision.ability,
                )
                mechanics_result = MechanicsResult(decision, check)
            elif decision.decision is MechanicsDecisionType.SAVING_THROW:
                if character is None or decision.ability is None or decision.dc is None:
                    raise TurnResolutionServiceError(
                        "saving throw requires an active character, ability and DC"
                    )
                check = saving_throw_for_character(
                    character=character,
                    roller=self.dice_roller,
                    ability=decision.ability,
                    dc=decision.dc,
                    advantage=decision.advantage,
                    disadvantage=decision.disadvantage,
                    situational_modifier=decision.situational_modifier,
                    manual_rolls=manual_rolls,
                )
                mechanics_result = MechanicsResult(decision, check)

        context_projection = None
        resolved_references: tuple[ResolvedConversationReference, ...] = ()
        resolved_world_references: tuple[ResolvedWorldReference, ...] = ()
        if self.context_builder is not None and intent_analysis.allows_world_proposal:
            mandatory_entity_ids: list[int] = []
            if context.active_character is not None:
                entity_id = context.active_character.entity_id
                if isinstance(entity_id, int) and not isinstance(entity_id, bool):
                    mandatory_entity_ids.append(entity_id)
            if context.active_character_entity is not None:
                entity_id = context.active_character_entity.id
                if (
                    isinstance(entity_id, int)
                    and not isinstance(entity_id, bool)
                    and entity_id not in mandatory_entity_ids
                ):
                    mandatory_entity_ids.append(entity_id)
            current_location_id = context.campaign.current_location_id
            if (
                isinstance(current_location_id, int)
                and not isinstance(current_location_id, bool)
                and current_location_id not in mandatory_entity_ids
            ):
                mandatory_entity_ids.append(current_location_id)
            try:
                semantic_queries = tuple(
                    dict.fromkeys(
                        [
                            *(
                                mention
                                for step in intent_analysis.steps
                                for mention in step.target_mentions
                            ),
                            *(
                                argument.mention.text
                                for step in intent_analysis.steps
                                if step.action_frame is not None
                                for argument in step.action_frame.arguments
                            ),
                            *(
                                mention
                                for claim in intent_analysis.relation_claims
                                for mention in (
                                    claim.subject.text,
                                    claim.object.text,
                                    (
                                        claim.attributed_to.text
                                        if claim.attributed_to is not None
                                        else None
                                    ),
                                )
                                if mention is not None
                            ),
                            *self._recent_context_queries(recent_turns),
                        ]
                    )
                )
                context_projection = self.context_builder.build_proposal_context(
                    context.world,
                    normalized_input,
                    max_estimated_tokens=self.proposal_context_max_tokens,
                    mandatory_entity_ids=mandatory_entity_ids,
                    supplemental_queries=semantic_queries,
                    character_entity_id=(
                        context.active_character.entity_id
                        if context.active_character is not None
                        else None
                    ),
                )
                discourse_history = DiscourseContextBuilder.scope_history(
                    recent_turns or (),
                    normalized_input,
                )
                reference_result = self.conversation_reference_resolver.resolve(
                    context_projection.world,
                    intent_analysis,
                    recent_turns=discourse_history,
                    current_input=normalized_input,
                )
                resolved_references = reference_result.references
                if reference_result.clarification_question:
                    question = reference_result.clarification_question
                    return TurnResolutionPlan(
                        player_input=normalized_input,
                        narrative=question,
                        world_operations=(),
                        character_operations=(),
                        ordered_operations=(),
                        clarification_question=question,
                        mechanics_decision=decision,
                        intent_analysis=intent_analysis,
                        intent_evidence_text=normalized_evidence_text,
                        intent_corrections=intent_corrections,
                    )
                typed_reference_result = self.world_reference_resolver.resolve(
                    context_projection.world,
                    intent_analysis,
                    recent_turns=discourse_history,
                    current_input=normalized_input,
                    character_entity_id=(
                        context.active_character.entity_id
                        if context.active_character is not None
                        else None
                    ),
                )
                resolved_world_references = typed_reference_result.references
                if typed_reference_result.clarification_question:
                    question = typed_reference_result.clarification_question
                    return TurnResolutionPlan(
                        player_input=normalized_input,
                        narrative=question,
                        world_operations=(),
                        character_operations=(),
                        ordered_operations=(),
                        clarification_question=question,
                        mechanics_decision=decision,
                        intent_analysis=intent_analysis,
                        intent_evidence_text=normalized_evidence_text,
                        intent_corrections=intent_corrections,
                    )
            except Exception as exc:
                raise TurnResolutionServiceError(
                    "proposal context selection failed"
                ) from exc

        try:
            if not intent_analysis.allows_world_proposal:
                operations = []
            elif context_projection is None:
                operations = self.extractor.propose(
                    normalized_input,
                    context,
                    mechanics_result=mechanics_result,
                    intent_analysis=intent_analysis,
                    recent_turns=recent_turns,
                    resolved_references=resolved_references,
                    resolved_world_references=resolved_world_references,
                )
            else:
                operations = self.extractor.propose(
                    normalized_input,
                    context,
                    mechanics_result=mechanics_result,
                    intent_analysis=intent_analysis,
                    recent_turns=recent_turns,
                    context_projection=context_projection,
                    resolved_references=resolved_references,
                    resolved_world_references=resolved_world_references,
                )
        except Exception as exc:
            raise TurnResolutionServiceError(
                "LLMWorldExtractor failed to propose consequences"
            ) from exc
        narrative = ""

        if not isinstance(operations, list):
            raise TurnResolutionServiceError(
                "LLMWorldExtractor returned an invalid operations list"
            )

        if any(
            isinstance(
                operation.operation if isinstance(operation, ReferencedOperation) else operation,
                CharacterOperation,
            )
            for operation in operations
        ):
            raise TurnResolutionServiceError(
                "character-state changes must come from deterministic mechanics, not an LLM proposal",
                code="character_operation_not_allowed",
            )

        normalized_operations = []
        for operation in operations:
            if isinstance(operation, ReferencedOperation):
                inner_operation = operation.operation
                if not isinstance(
                    inner_operation,
                    (WorldOperation, CharacterOperation),
                ):
                    raise TurnResolutionServiceError(
                        "LLMWorldExtractor returned an invalid referenced operation"
                    )
                normalized_operations.append(operation)
            elif isinstance(operation, (WorldOperation, CharacterOperation)):
                normalized_operations.append(operation)
            else:
                raise TurnResolutionServiceError(
                    "LLMWorldExtractor returned an invalid operation"
                )

        def get_operation(operation):
            if isinstance(operation, ReferencedOperation):
                return operation.operation
            return operation

        ordered_operations = tuple(normalized_operations)
        world_operations = tuple(
            operation
            for operation in ordered_operations
            if isinstance(get_operation(operation), WorldOperation)
        )
        character_operations = tuple(
            operation
            for operation in ordered_operations
            if isinstance(get_operation(operation), CharacterOperation)
        )

        return TurnResolutionPlan(
            player_input=normalized_input,
            narrative=narrative,
            world_operations=world_operations,
            character_operations=character_operations,
            ordered_operations=ordered_operations,
            mechanics_result=mechanics_result,
            mechanics_decision=decision,
            intent_analysis=intent_analysis,
            intent_evidence_text=normalized_evidence_text,
            intent_corrections=intent_corrections,
        )

    def generate_narrative(
        self,
        turn_context: TurnContext,
        player_input: str,
        *,
        recent_turns=None,
        mechanics_result: MechanicsResult | None = None,
        committed_resolution: str | None = None,
    ) -> str:
        """Generate presentation prose after the consequence commit."""
        try:
            return self.dm_service.generate(
                turn_context,
                player_input,
                recent_turns=recent_turns,
                mechanics_result=mechanics_result,
                committed_resolution=committed_resolution,
            ).strip()
        except Exception as exc:
            raise TurnResolutionServiceError(
                "DMService failed to narrate committed turn"
            ) from exc

    def apply_plan(
        self,
        turn_context: TurnContext | WorldState,
        plan: TurnResolutionPlan,
        *,
        conn=None,
    ) -> TurnResolutionResult:
        """Apply a previously prepared plan inside the caller's transaction."""
        if isinstance(turn_context, TurnContext):
            context = turn_context
        elif isinstance(turn_context, WorldState):
            context = TurnContext(
                campaign=CampaignState(),
                current_session=None,
                active_character=None,
                world=turn_context,
            )
        else:
            raise TypeError(
                "turn_context must be a TurnContext or WorldState"
            )
        if not isinstance(plan, TurnResolutionPlan):
            raise TypeError("plan must be a TurnResolutionPlan")

        if plan.awaiting_manual_roll:
            raise TurnResolutionServiceError(
                "manual roll must be submitted before applying the turn"
            )

        if plan.clarification_question is not None:
            return TurnResolutionResult(
                player_input=plan.player_input,
                narrative=plan.clarification_question,
            )

        try:
            operation_results = self.world_service.apply_turn_operations(
                plan.world_operations,
                plan.character_operations,
                campaign_id=context.campaign.campaign_id,
                conn=conn,
                ordered_operations=plan.ordered_operations,
            )
        except Exception as exc:
            raise TurnResolutionServiceError(
                "WorldService failed to apply operations"
            ) from exc

        return TurnResolutionResult(
            player_input=plan.player_input,
            narrative=plan.narrative,
            operations=plan.world_operations,
            character_operations=plan.character_operations,
            operation_results=tuple(operation_results),
            mechanics_result=plan.mechanics_result,
        )

    def resolve_turn(
        self,
        turn_context: TurnContext | WorldState,
        player_input: str,
        *,
        recent_turns=None,
        conn=None,
    ) -> TurnResolutionResult:
        """Convenience wrapper: prepare, apply, then narrate for non-durable callers."""
        plan = self.prepare_turn(turn_context, player_input)
        result = self.apply_plan(turn_context, plan, conn=conn)
        if conn is not None or plan.awaiting_manual_roll:
            return result
        if plan.clarification_question is not None:
            return result

        context = (
            turn_context
            if isinstance(turn_context, TurnContext)
            else TurnContext(
                campaign=CampaignState(),
                current_session=None,
                active_character=None,
                world=turn_context,
            )
        )
        narrative = self.generate_narrative(
            context,
            plan.player_input,
            recent_turns=recent_turns,
            mechanics_result=plan.mechanics_result,
        )
        if not narrative:
            raise TurnResolutionServiceError("DMService returned an empty narrative")
        return replace(result, narrative=narrative)

    # ============================================================
    # VALIDATION
    # ============================================================

    @staticmethod
    def _validate_world(
        world: WorldState,
    ) -> None:

        if not isinstance(
            world,
            WorldState,
        ):
            raise TypeError(
                "world must be a WorldState"
            )

    @staticmethod
    def _validate_player_input(
        player_input: str,
    ) -> str:

        if not isinstance(
            player_input,
            str,
        ):
            raise TypeError(
                "player_input must be a string"
            )

        return player_input.strip()