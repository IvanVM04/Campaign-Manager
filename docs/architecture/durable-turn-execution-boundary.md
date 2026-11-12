# Durable turn execution boundary

**Status:** implemented behind the stable `DurableNativeTurnService` façade.  
**Scope:** native campaign turns and the shared durable resolution path used by external adapters.

## Ownership

The public service remains the composition and compatibility façade. It retains the API used by routers, bootstrap and the SillyTavern integration; callers do not construct the execution collaborator directly.

| Component | Owns | Does not own |
|---|---|---|
| `DurableNativeTurnService` | Stable public methods, composition of collaborators, context/history loading, continuation routing | Request claim/planning state machine internals |
| `DurableTurnExecutionService` | Request fingerprint and idempotency lookup, resolution claim, planning lease, plan preparation, durable challenge/prepared-plan transitions, pre-commit recovery | HTTP, provider implementation, rules, SQL statements, narrative generation |
| `DurableTurnPreparedCommitService` | Short atomic revalidation and application of prepared consequences; transition to committed/narration-pending | Provider calls, narrative, request identity |
| Challenge services | Clarification/manual-roll validation, submission, recovery and challenge read models | Initial request acceptance or independent campaign mutation |
| `DurableTurnNarrationService` | Native narration resume, external transcript versions and completion | Applying world consequences or rerolling mechanics |
| `durable_turn_errors.py` | Stable error identities shared by collaborators and API mapping | Lifecycle decisions based on message text |

## Execution sequence

1. Read a consistent campaign/context/history snapshot and current campaign revision in a read transaction.
2. Normalize the request identity and calculate its fingerprint from player input, session identity and dice mode.
3. In a short `IMMEDIATE` transaction, load or create the campaign-scoped resolution identity. Repeated identity with a different fingerprint is rejected; matching completed/in-flight identities resume their existing state.
4. Claim planning with a lease token. The token fences off a late worker after another attempt reclaims the expired lease.
5. Prepare mechanics and structured consequence proposals outside a write transaction. A manual roll or clarification transitions to `awaiting_input` and stores the challenge evidence; no consequence is applied.
6. Persist the immutable proposal and mechanics evidence as `prepared`, conditionally on the attempt's planning lease.
7. Hand the prepared plan to `DurableTurnPreparedCommitService`. It opens one `IMMEDIATE` transaction, rechecks campaign revision/context/history, applies all validated consequences, records operation outcomes/resulting revision and advances the resolution to `narration_pending`.
8. Native callers resume narration after commit. External adapters receive the committed preparation and complete the presentation through the existing external lifecycle.

Provider calls and narration are outside the write transaction. A stale or failed prepared commit rolls back the consequence application. A post-commit narration failure is recoverable from `narration_pending` and must never call the proposal/applier again for that resolution.

## Typed failure contract

Lifecycle logic must branch on typed error codes, not on the wording of an exception message.

| Error code | Meaning | Persisted handling |
|---|---|---|
| `conflict` | Request identity, lease or challenge conflict | Leave the existing durable state unchanged |
| `stale_context` | Campaign revision or context/history changed before commit | Reject the prepared resolution; do not apply consequences |
| `operation_validation_failed` | A proposed consequence set failed application validation | Reject the prepared resolution; commit transaction rolls back |
| `character_operation_not_allowed` | The model proposed a character-state operation outside the proposal contract | Reject the planning attempt and surface an invalid-model-response API error |
| `turn_execution_failed` | Unexpected internal execution failure | Release/requeue only if the current worker still owns the planning lease; expose a sanitized 500 |

The exception chain still has precedence for provider outages and malformed provider/model output, so those continue mapping to their existing 503/502 API contracts. The durable error code is stable for programmatic handling; messages remain diagnostic text and are not a control-flow contract.

## Protected invariants

- One resolution identity per campaign/adapter namespace/idempotency key.
- The fingerprint semantics remain unchanged: normalized player input, session ID and dice mode.
- Only the current lease token may transition a planning attempt.
- Planning and provider work never hold a SQLite write transaction.
- Revision/context/history are revalidated immediately before consequence application.
- Consequence mutations, operation evidence, resulting revision and lifecycle transition remain atomic.
- Narration retries never replay consequences or mechanics.
- Clarification and manual-roll submissions resume the original resolution, preserving their challenge identity.
- Campaign scoping and the existing process-local turn lock remain unchanged.

## Explicit non-goals

This extraction does not add a background worker, queue, event bus, distributed lock, new table, retry scheduler or multi-process guarantee. The runtime and turn lock remain process-local; the supported deployment model remains single-process/local-first. It also does not split the public native/SillyTavern APIs or change their request/response contracts.

Future decomposition should happen only where a continuation or lifecycle stage owns a distinct invariant and can be independently validated. Do not split collaborators merely to reduce line count.
