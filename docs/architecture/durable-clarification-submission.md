# Durable clarification submission boundary

## Responsibility

`DurableTurnClarificationSubmissionService` coordinates the clarification-specific
submission lifecycle previously embedded in `DurableNativeTurnService`:

- validates challenge identifiers, answers, adapter ownership, and external reply IDs;
- preserves idempotent retries across awaiting, prepared, committed, and completed states;
- acquires and fences planning leases while re-running adjudication;
- persists follow-up clarification or manual-roll challenges;
- prepares and commits resolved plans through the existing prepared-commit boundary;
- recovers prepared clarification submissions and resumes narration.

The collaborator receives the native turn service as its owner of shared repositories,
resolver, context loading, result mapping, and transaction collaborators. It does not
own those dependencies or alter their lifecycle.

## Invariants preserved

- Challenge identity and adapter namespace checks remain unchanged.
- Planning leases continue to use the existing repository claim and expected lease token.
- Stale context/revision checks and rejection transitions remain in place.
- Prepared records are committed through `DurableTurnPreparedCommitService`.
- Narration remains a separate resumable phase.
- Persisted JSON, database schema, and public method signatures are unchanged.

Manual-roll submission remains in `DurableNativeTurnService` for a separate extraction,
because its accepted-roll replay and dice validation rules differ from clarification
answer handling.
