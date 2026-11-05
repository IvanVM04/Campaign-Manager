# Durable prepared challenge commit boundary

The durable native turn pipeline has multiple entry points that eventually
apply a prepared plan: native turns, clarification answers and manual-roll
submissions. Each path must compare the same campaign snapshot, apply domain
consequences and advance the resolution lifecycle in one immediate transaction.

## Ownership

`DurableTurnPreparedCommitService` owns that shared commit boundary:

- verifies the campaign revision against the revision captured during planning;
- reloads context and recent history and rejects a changed snapshot;
- applies the prepared plan inside the same immediate transaction;
- rejects unsuccessful consequence application;
- persists the resulting revision and operation results;
- advances `prepared -> committed -> narration_pending` atomically.

`DurableNativeTurnService` remains responsible for challenge-specific work:
identity validation, challenge-token checks, lease claims, collecting answers or
dice, planning, and mapping the result into the existing API response. Its
public methods remain compatible.

## Invariants

- Lease ownership and fencing remain with the caller and repository.
- The prepared record is still written before this service is called.
- Context/revision validation and consequence application share one transaction.
- Both lifecycle transitions are committed together with the domain changes.
- Narration remains a separate resumable phase.
- No persisted JSON, schema, route, or extension contract changes.
