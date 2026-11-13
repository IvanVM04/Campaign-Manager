from __future__ import annotations

from dataclasses import replace

from models.campaign_scope import CampaignScope
from models.turn_record import TurnRecord
from models.turn_resolution_record import TurnResolutionRecord
from models.turn_resolution_result import TurnResolutionResult
from repositories.campaign_state_version_repository import (
    CampaignStateVersionRepository,
)
from repositories.turn_repository import TurnRepository
from repositories.turn_resolution_repository import TurnResolutionRepository
from services.turns import (
    DurableTurnChallengeStateService,
    DurableTurnClarificationSubmissionService,
    DurableTurnManualRollSubmissionService,
    DurableTurnNarrationService,
    DurableTurnPreparation,
    DurableTurnPreparationMapper,
    DurableTurnPreparedCommitService,
    DurableTurnResultMapper,
    TurnResolutionCodec,
)
from services.turns.durable_turn_errors import DurableNativeTurnError
from services.turns.durable_turn_execution_service import DurableTurnExecutionService
from services.turns.turn_resolution_service import (
    TurnResolutionPlan,
    TurnResolutionService,
)
from services.world import WorldService


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
        self.prepared_commit_service = DurableTurnPreparedCommitService(
            scope=scope,
            resolver=resolver,
            revision_repository=self.revision_repository,
            resolution_repository=self.resolution_repository,
            context_loader=lambda conn, conversation_id=None: self._context_and_history(conn, conversation_id=conversation_id),
            operation_results_serializer=self._operation_results_json,
            error_type=DurableNativeTurnError,
        )
        self.clarification_submission_service = (
            DurableTurnClarificationSubmissionService(
                self,
                error_type=DurableNativeTurnError,
            )
        )
        self.manual_roll_submission_service = (
            DurableTurnManualRollSubmissionService(
                self,
                error_type=DurableNativeTurnError,
            )
        )
        self.narration_service = DurableTurnNarrationService(
            scope=scope,
            resolver=resolver,
            turn_repository=self.turn_repository,
            resolution_repository=self.resolution_repository,
            turn_execution_lock=turn_execution_lock,
            context_loader=lambda conn, conversation_id=None: self._context_and_history(
                conn, conversation_id=conversation_id
            ),
            error_type=DurableNativeTurnError,
        )

        self.execution_service = DurableTurnExecutionService(
            scope=scope,
            resolver=resolver,
            turn_repository=self.turn_repository,
            resolution_repository=self.resolution_repository,
            revision_repository=self.revision_repository,
            prepared_commit_service=self.prepared_commit_service,
            narration_service=self.narration_service,
            context_loader=lambda conn, conversation_id=None: self._context_and_history(
                conn, conversation_id=conversation_id
            ),
            turn_execution_lock=turn_execution_lock,
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

    def _context_and_history(self, conn, *, conversation_id: str | None = None):
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
            conversation_id=conversation_id,
            scope=self.scope,
            conn=conn,
        )
        return context, recent

    def _plan_from_record(self, record: TurnResolutionRecord) -> TurnResolutionPlan:
        return TurnResolutionCodec.plan_from_record(
            record,
            self.resolver.extractor.operation_parser,
        )

    def play_turn(
        self,
        player_input: str,
        *,
        idempotency_key: str | None = None,
        dice_mode: str = "automatic",
    ):
        return self.execution_service.play_turn(
            player_input,
            idempotency_key=idempotency_key,
            dice_mode=dice_mode,
        )

    def prepare_external_turn(
        self,
        player_input: str,
        *,
        external_turn_id: str,
        dice_mode: str = "automatic",
        conversation_id: str | None = None,
    ) -> DurableTurnPreparation:
        return self.execution_service.prepare_external_turn(
            player_input,
            external_turn_id=external_turn_id,
            dice_mode=dice_mode,
            conversation_id=conversation_id,
        )

    def get_external_clarification_state(self, external_turn_id: str) -> dict:
        return self.challenge_state_service.get_external_clarification_state(
            external_turn_id
        )

    @staticmethod
    def _required_resolution_id(record: TurnResolutionRecord) -> int:
        if record.id is None:
            raise DurableNativeTurnError(
                "persisted turn resolution has no database identifier"
            )
        return record.id

    @staticmethod
    def _require_resolution_record(
        record: TurnResolutionRecord | None,
    ) -> TurnResolutionRecord:
        if record is None:
            raise DurableNativeTurnError(
                "turn resolution disappeared after a successful persistence operation"
            )
        return record

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
        conversation_id: str | None = None,
    ):
        return self.clarification_submission_service.submit_clarification(
            pending_clarification_id,
            answer,
            adapter_namespace=adapter_namespace,
            defer_narration=defer_narration,
            answer_external_turn_id=answer_external_turn_id,
            conversation_id=conversation_id,
        )
    def _build_manual_roll_request(self, record, decision, context, revision):
        return self.execution_service.build_manual_roll_request(
            record,
            decision,
            context,
            revision,
        )

    def get_external_manual_roll_state(self, external_turn_id: str) -> dict:
        return self.challenge_state_service.get_external_manual_roll_state(
            external_turn_id
        )

    def submit_manual_roll(
        self,
        pending_roll_id: str,
        rolls: tuple[int, ...],
        *,
        adapter_namespace: str | None = None,
        defer_narration: bool = False,
        answer_external_turn_id: str | None = None,
        conversation_id: str | None = None,
    ):
        return self.manual_roll_submission_service.submit_manual_roll(
            pending_roll_id,
            rolls,
            adapter_namespace=adapter_namespace,
            defer_narration=defer_narration,
            answer_external_turn_id=answer_external_turn_id,
            conversation_id=conversation_id,
        )

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
        return self.narration_service.complete_external_narration(
            external_turn_id=external_turn_id,
            player_input=player_input,
            narrative=narrative,
            turn_version=turn_version,
        )

    def _result_from_completed_record(
        self,
        record: TurnResolutionRecord,
        turn: TurnRecord,
        *,
        already_processed: bool,
    ) -> TurnResolutionResult:
        return self.narration_service.result_from_completed_record(
            record,
            turn,
            already_processed=already_processed,
        )

    def _resume_narration(
        self,
        record: TurnResolutionRecord,
        *,
        already_processed: bool,
    ):
        return self.narration_service.resume_narration(
            record,
            already_processed=already_processed,
        )

    @staticmethod
    def _resolved_player_input(record: TurnResolutionRecord) -> str:
        return DurableTurnNarrationService._resolved_player_input(record)
