# Durable challenge state boundary

The durable turn lifecycle stores clarification and manual-roll challenges inside
the turn-resolution record. Clients need a read-only projection of that state so
they can recover a pending prompt after a reload without receiving internal
adjudication details.

## Ownership

`DurableTurnChallengeStateService` owns the read side of that boundary:

- validates external turn identities used by challenge-state lookups;
- scopes resolution lookup to the `sillytavern` adapter namespace and campaign;
- projects clarification state, accepted-answer identity and the active transcript;
- projects manual-roll state while omitting the opaque challenge token, submitted
  dice and internal mechanics decision from the public payload.

`DurableNativeTurnService` remains the public facade and delegates the two
read operations to this collaborator. Existing route and extension contracts
are unchanged.

## Deliberately not extracted yet

Challenge submission is still coordinated by `DurableNativeTurnService`.
Submitting an answer or roll is not a simple state projection: it claims a
planning lease, checks the campaign revision, prepares a plan, writes a prepared
record, commits consequences atomically and advances the lifecycle. Moving that
transactional flow requires a separate extraction with explicit dependencies
and failure-injection tests; it should not be mixed into a read-side refactor.

The next lifecycle slices can therefore be extracted independently:

1. clarification/manual-roll submission orchestration;
2. external narration versioning and completion;
3. the remaining native planning/commit coordinator.

## Invariants

- No database schema or persisted JSON shape changes.
- Challenge identifiers remain opaque and adapter-scoped.
- Manual-roll state does not expose internal adjudication decisions.
- A completed manual roll is recoverable only when the accepted reply has a
  persisted external message identity.
- Existing facade methods remain available to API routers and callers.
- This extraction does not change lock ownership, lease fencing, revision
  checks, or transaction boundaries.
