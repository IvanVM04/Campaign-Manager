# Durable manual-roll submission boundary

## Responsibility

`DurableTurnManualRollSubmissionService` coordinates submission and recovery of
manual dice challenges previously embedded in `DurableNativeTurnService`:

- validates challenge identifiers, die results, and optional external reply IDs;
- verifies challenge identity and adapter ownership;
- preserves accepted-roll replay and rejects conflicting duplicate submissions;
- checks the saved context revision and fences planning with repository leases;
- resolves the prepared plan using the persisted mechanics decision;
- commits through `DurableTurnPreparedCommitService` and resumes narration.

The collaborator receives the native turn service as the owner of shared repositories,
resolver, context loading, result mapping, and commit coordination. The public
`DurableNativeTurnService.submit_manual_roll()` method remains as a compatibility
boundary for API routes and adapters.

## Invariants preserved

- Die results remain one or two non-boolean integers in the inclusive range 1–20.
- The number of submitted dice must match the challenge's required count.
- Challenge IDs, adapter namespaces, and external reply identity remain validated.
- Accepted rolls are idempotent; conflicting values or reply IDs are rejected.
- Stale context revisions are rejected before applying the roll.
- Planning leases and expected lease-token fencing remain in place.
- Prepared commits and narration recovery use the existing collaborators.
- Persisted JSON, database schema, and public method signatures are unchanged.

Manual-roll challenge construction remains in `DurableNativeTurnService` because
both initial turn planning and clarification submission use that shared operation.
