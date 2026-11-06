"""Regression tests for legacy turn-service import compatibility."""


def test_durable_turn_collaborators_reexport_canonical_package_classes():
    from services.durable_turn_challenge_state_service import (
        DurableTurnChallengeStateService as LegacyChallengeStateService,
    )
    from services.durable_turn_clarification_submission_service import (
        DurableTurnClarificationSubmissionService as LegacyClarificationService,
    )
    from services.durable_turn_manual_roll_submission_service import (
        DurableTurnManualRollSubmissionService as LegacyManualRollService,
    )
    from services.durable_turn_narration_service import (
        DurableTurnNarrationService as LegacyNarrationService,
    )
    from services.durable_turn_preparation_mapper import (
        DurableTurnPreparation as LegacyPreparation,
        DurableTurnPreparationMapper as LegacyPreparationMapper,
    )
    from services.durable_turn_prepared_commit_service import (
        DurableTurnPreparedCommitService as LegacyPreparedCommitService,
    )
    from services.durable_turn_result_mapper import (
        DurableTurnResultMapper as LegacyResultMapper,
    )
    from services.turns import (
        DurableTurnChallengeStateService,
        DurableTurnClarificationSubmissionService,
        DurableTurnManualRollSubmissionService,
        DurableTurnNarrationService,
        DurableTurnPreparation,
        DurableTurnPreparationMapper,
        DurableTurnPreparedCommitService,
        DurableTurnResultMapper,
    )

    assert LegacyChallengeStateService is DurableTurnChallengeStateService
    assert LegacyClarificationService is DurableTurnClarificationSubmissionService
    assert LegacyManualRollService is DurableTurnManualRollSubmissionService
    assert LegacyNarrationService is DurableTurnNarrationService
    assert LegacyPreparation is DurableTurnPreparation
    assert LegacyPreparationMapper is DurableTurnPreparationMapper
    assert LegacyPreparedCommitService is DurableTurnPreparedCommitService
    assert LegacyResultMapper is DurableTurnResultMapper
