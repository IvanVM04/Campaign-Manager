from __future__ import annotations

from dataclasses import dataclass, replace

from models.campaign_state import CampaignState
from models.mechanics import MechanicsDecision, MechanicsDecisionType, MechanicsResult
from models.turn_context import TurnContext
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
from services.context import ContextBuilder
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
    awaiting_manual_roll: bool = False


class TurnResolutionServiceError(RuntimeError):
    """
    Error base del servicio de resolución de turnos.
    """


class TurnResolutionService:
    """
    Prepara y aplica un turno en dos fases.

    prepare_turn():
        jugador -> DMService -> narrativa -> LLMWorldExtractor
        -> TurnResolutionPlan inmutable (sin mutar estado)

    apply_plan():
        TurnResolutionPlan + contexto fresco -> WorldService
        -> resultados de operaciones

    resolve_turn() conserva una API de compatibilidad que ejecuta
    ambas fases en secuencia. CampaignTurnService usa las fases
    por separado para no mantener SQLite abierta durante inferencia.

    Responsabilidades:

    - validar WorldState
    - validar entrada del jugador
    - generar narrativa mediante DMService
    - extraer operaciones mediante LLMWorldExtractor
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
        self.proposal_context_max_tokens = proposal_context_max_tokens

    # ============================================================
    # PUBLIC API
    # ============================================================

    def prepare_turn(
        self,
        turn_context: TurnContext | WorldState,
        player_input: str,
        *,
        recent_turns=None,
        manual_mode: bool = False,
        manual_rolls: tuple[int, ...] | None = None,
        decision_override: MechanicsDecision | None = None,
        proposal_from_intent: bool = False,
    ) -> TurnResolutionPlan:
        """
        Prepare a typed operation proposal; optionally preserve the legacy narrative-first path.

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

        if not isinstance(manual_mode, bool):
            raise TypeError("manual_mode must be a boolean")
        if decision_override is not None and not isinstance(
            decision_override, MechanicsDecision
        ):
            raise TypeError("decision_override must be a MechanicsDecision or None")
        if manual_rolls is not None and not isinstance(manual_rolls, tuple):
            raise TypeError("manual_rolls must be a tuple or None")

        mechanics_result = None
        decision = decision_override
        if decision is not None or self.mechanics_adjudicator is not None:
            try:
                if decision is None:
                    adjudicator = self.mechanics_adjudicator
                    if adjudicator is None:
                        raise TurnResolutionServiceError(
                            "mechanics adjudicator is required to produce a decision"
                        )
                    decision = adjudicator.adjudicate(context, normalized_input)
            except MechanicsAdjudicatorError as exc:
                raise TurnResolutionServiceError(
                    "mechanics adjudication failed"
                ) from exc

            if decision.decision is MechanicsDecisionType.CLARIFICATION:
                return TurnResolutionPlan(
                    player_input=normalized_input,
                    narrative=decision.question or "",
                    world_operations=(),
                    character_operations=(),
                    ordered_operations=(),
                    clarification_question=decision.question,
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

        if not isinstance(proposal_from_intent, bool):
            raise TypeError("proposal_from_intent must be a boolean")

        if proposal_from_intent:
            context_projection = None
            if self.context_builder is not None:
                mandatory_entity_ids: list[int] = []
                if context.active_character is not None:
                    entity_id = context.active_character.entity_id
                    if isinstance(entity_id, int) and not isinstance(entity_id, bool):
                        mandatory_entity_ids.append(entity_id)
                if context.active_character_entity is not None:
                    entity_id = context.active_character_entity.id
                    if isinstance(entity_id, int) and not isinstance(entity_id, bool):
                        if entity_id not in mandatory_entity_ids:
                            mandatory_entity_ids.append(entity_id)
                current_location_id = context.campaign.current_location_id
                if (
                    isinstance(current_location_id, int)
                    and not isinstance(current_location_id, bool)
                    and current_location_id not in mandatory_entity_ids
                ):
                    mandatory_entity_ids.append(current_location_id)
                try:
                    context_projection = self.context_builder.build_proposal_context(
                        context.world,
                        normalized_input,
                        max_estimated_tokens=self.proposal_context_max_tokens,
                        mandatory_entity_ids=mandatory_entity_ids,
                    )
                except Exception as exc:
                    raise TurnResolutionServiceError(
                        "proposal context selection failed"
                    ) from exc

            try:
                if context_projection is None:
                    operations = self.extractor.propose(
                        normalized_input,
                        context,
                        mechanics_result=mechanics_result,
                    )
                else:
                    operations = self.extractor.propose(
                        normalized_input,
                        context,
                        mechanics_result=mechanics_result,
                        context_projection=context_projection,
                    )
            except Exception as exc:
                raise TurnResolutionServiceError(
                    "LLMWorldExtractor failed to propose consequences"
                ) from exc
            narrative = ""
        else:
            try:
                if recent_turns is None:
                    if mechanics_result is None:
                        narrative = self.dm_service.generate(context, normalized_input)
                    else:
                        narrative = self.dm_service.generate(
                            context, normalized_input, mechanics_result=mechanics_result
                        )
                else:
                    if mechanics_result is None:
                        narrative = self.dm_service.generate(
                            context, normalized_input, recent_turns=recent_turns
                        )
                    else:
                        narrative = self.dm_service.generate(
                            context, normalized_input, recent_turns=recent_turns,
                            mechanics_result=mechanics_result,
                        )
            except Exception as exc:
                raise TurnResolutionServiceError(
                    "DMService failed to generate the turn"
                ) from exc

            if not isinstance(narrative, str):
                raise TurnResolutionServiceError(
                    "DMService returned a non-string narrative"
                )
            narrative = narrative.strip()
            if not narrative:
                raise TurnResolutionServiceError(
                    "DMService returned an empty narrative"
                )

            try:
                operations = self.extractor.extract(narrative, context)
            except Exception as exc:
                raise TurnResolutionServiceError(
                    "LLMWorldExtractor failed to extract operations"
                ) from exc


        if not isinstance(operations, list):
            raise TurnResolutionServiceError(
                "LLMWorldExtractor returned an invalid operations list"
            )

        if proposal_from_intent and any(
            isinstance(
                operation.operation if isinstance(operation, ReferencedOperation) else operation,
                CharacterOperation,
            )
            for operation in operations
        ):
            raise TurnResolutionServiceError(
                "character-state changes must come from deterministic mechanics, not an LLM proposal"
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
        """Backward-compatible convenience wrapper around prepare/apply."""
        plan = self.prepare_turn(
            turn_context,
            player_input,
            recent_turns=recent_turns,
        )
        return self.apply_plan(turn_context, plan, conn=conn)

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