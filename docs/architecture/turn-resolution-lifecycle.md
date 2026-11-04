# Durable turn-resolution lifecycle contract

**Status:** Proposed architecture contract (PR #28)
**Scope:** Native campaign turns and external adapters, including SillyTavern
**Implementation:** PRs #29-#30 (native automatic turns); adapter and manual-input continuation remain follow-ups

## 1. Purpose

A campaign turn must have one durable, auditable resolution whose domain consequences are applied at most once. Narrative generation is a separate, retryable projection of that committed resolution.

This contract closes a gap in the current native flow: `TurnResolutionService.prepare_turn()` currently generates DM prose and then asks `LLMWorldExtractor` to infer persistent operations from that prose. The resulting plan is applied and the narrative is stored in the same transaction. This is not yet the target pipeline: prose is acting as an intermediate source for proposed state changes, and a failure after the state commit cannot be recovered independently from narration.

This PR defines the target boundary and invariants only. It does not add a table, migration, service, API endpoint, or behaviour change.

## 2. Domain vocabulary and ownership

- **Turn request:** normalized player intent plus campaign scope, adapter identity, idempotency identity, and optional client metadata.
- **Turn context:** a consistent read snapshot of campaign, session, character, world, recent history, and campaign state revision.
- **Adjudication:** a validated decision about clarification, authority, required checks, and applicable rules.
- **Mechanics result:** deterministic result produced by the selected ruleset from trusted character/world data and dice inputs. The model may propose a check; it does not supply the authoritative total or mutate state.
- **Consequence proposal:** structured, typed domain operations proposed for a turn. A proposal is untrusted until application-level validation succeeds.
- **Committed resolution:** immutable record of the accepted request, context revision, adjudication/mechanics evidence, validated consequence set, and operation results.
- **Narration:** user-facing prose generated from the committed resolution and the relevant context. It is not an instruction to mutate domain state.

The application turn use case owns authorization, validation, idempotency, state transitions, and transaction boundaries. Rules engines own deterministic mechanics. Domain services own domain invariants. Repositories persist records using caller-owned transactions. Native API and integrations are adapters; none may implement a competing resolution pipeline.

## 3. Lifecycle

The durable lifecycle uses these conceptual states:

| State | Meaning | Allowed next states |
|---|---|---|
| `accepted` | Request identity and normalized input have been claimed durably. | `planning`, `rejected` |
| `planning` | Context/adjudication/mechanics/consequence proposal is being prepared outside a write transaction. | `awaiting_input`, `prepared`, `rejected`, retryable `accepted` |
| `awaiting_input` | A specific player decision or manual roll is required; the request and expected context revision remain durable. | `planning`, `rejected` |
| `prepared` | Immutable proposal and expected context revision are persisted; no domain consequences have been applied. | `committed`, `rejected` |
| `committed` | Consequences, operation results, resulting state revision, and the committed resolution are persisted atomically. | `narration_pending` |
| `narration_pending` | The committed resolution is awaiting user-facing prose. | `completed` |
| `completed` | Narration is persisted and the turn is fully presented. | terminal |
| `rejected` | The request/proposal was invalid, unauthorized, stale, or otherwise refused before consequence commit. | terminal |

A transient provider or infrastructure error before commit is an attempt failure, not evidence that domain state changed. It must be recorded as retry metadata (attempt count, safe error category, timestamps) and must not create a terminal committed result. A crash while `planning` is recoverable by reclaiming an expired attempt. A crash after commit resumes at `narration_pending`; it never reruns consequence application.

No transition may move a committed resolution back to planning or apply a second consequence set. A correction is a new, explicitly linked resolution, not mutation of historical committed data.

## 4. Required invariants

### 4.1 Idempotency and identity

1. Every request has a stable idempotency key scoped to its campaign and adapter/client namespace.
2. The request fingerprint covers normalized player input and all fields that can change its meaning (including relevant adapter turn/version identity and explicit decision inputs).
3. Repeating the same key and same fingerprint returns the existing lifecycle/result; it does not call the consequence applier again.
4. Repeating the same key with a different fingerprint is a conflict and must not overwrite the original request.
5. Adapter versioning is distinct from idempotency. A regeneration/version is a separate candidate resolution and may supersede a prior version only through an explicit adapter policy. Superseding a record must never silently undo already committed world changes.
6. Uniqueness must be enforced by the database, not only by a process-local lock or cache.

### 4.2 Context and stale-plan protection

1. Planning reads a consistent campaign snapshot and its monotonic state revision.
2. Provider/LLM work happens without holding a SQLite write transaction.
3. Before commit, the application opens a short `BEGIN IMMEDIATE` transaction and revalidates campaign scope, state revision, relevant context/history, actor authority, target identity, ownership, and operation preconditions.
4. A stale proposal is rejected or replanned from a fresh context; it is never applied against a different state than the one it was prepared for.
5. The committed record stores the revision it was based on and the resulting revision.

### 4.3 Atomic consequence commit

The following must commit or roll back together in one write transaction:

- accepted validated consequence operations and their deterministic domain mutations;
- operation-level outcomes and the resolution evidence needed to explain the result;
- transition to `committed` / `narration_pending`;
- the resulting campaign state revision and idempotency identity.

A partial consequence set is not a successful turn. If an operation fails and the contract requires all-or-nothing semantics, the transaction rolls back. If a future domain explicitly supports partial success, that policy must be represented in the typed resolution and tested; it must not be inferred from narrative wording.

### 4.4 Narration isolation

1. Narration starts only after the consequence transaction commits.
2. Narration input is the committed resolution plus an explicitly selected read context; it cannot modify the resolution or domain state.
3. Narration failure leaves the turn in `narration_pending` with committed consequences intact.
4. Retrying narration may produce a replacement narrative, but cannot reapply operations, reroll mechanics, or change committed outcomes.
5. Persist the final narrative and transition to `completed` atomically.
6. The UI/API must distinguish “consequences committed, narration pending” from “turn failed”.

### 4.5 Trust boundary for AI proposals

- AI output is an untrusted proposal, never an authorization grant.
- Actor, target, campaign scope, item ownership, resource balances, preconditions, and allowed operation types are resolved/validated by application and domain code.
- Mechanical values are recomputed by deterministic rules code.
- Narrative text is not parsed as the authoritative source of consequences.
- The transitional narrative extractor may remain behind a compatibility adapter while migration proceeds, but its output must be treated as an untrusted proposal and must not define final truth. The target design is a structured proposal channel independent of final prose.

## 5. Transaction and recovery boundaries

| Boundary | Work allowed | Transaction rule |
|---|---|---|
| Accept request | Normalize, fingerprint, claim idempotency identity | Short transaction; durable before expensive provider calls |
| Plan | Context read, adjudication, deterministic rolls, structured proposal generation | Read transaction only for snapshot; no write transaction held during provider calls |
| Store prepared plan | Persist immutable proposal and expected revision | Short transaction |
| Commit consequences | Revalidate + apply + store outcomes + lifecycle transition | One `BEGIN IMMEDIATE` transaction |
| Narrate | Generate prose from committed resolution | No domain write transaction |
| Complete narration | Store prose + mark completed | Short transaction; conditional on still being narration-pending |

Recovery rules:

- Expired planning attempts can be reclaimed with a lease/attempt token; a late worker must fail its conditional transition.
- A prepared plan is either committed after revalidation or rejected as stale; it is not blindly replayed.
- If the process stops after consequence commit, a worker/next request can discover `narration_pending` and continue narration.
- If the process stops during narration, narration can be retried safely.
- Manual rolls and clarification waits must be durable if they are part of a request that the product promises to resume after restart. Their submitted response is validated against the stored request and context revision.
- Recovery must not depend on in-memory `_pending_manual_rolls`, a local lock, or an integration process cache.

## 6. Relationship to existing persistence

The existing `turns` table and `TurnRecord` are historical records with narrative, operation counts, external turn ID, version, status, and optional snapshot. They are not yet a complete durable resolution lifecycle: they do not represent accepted/planning/prepared/narration-pending states, persisted proposals, attempt leases, or a separate narration result.

The existing `campaign_state_versions` mechanism supplies the monotonic revision primitive needed for stale-plan checks. The existing `TurnRepository` and turn history must be inspected and extended rather than duplicated. SillyTavern's external turn/version/snapshot lifecycle is an adapter concern and must map onto this shared application contract without replacing it.

No second “turns” table or parallel campaign revision counter should be introduced. The next implementation design must decide whether to evolve `turns` or add a narrowly scoped resolution record linked to it, based on concrete compatibility and data-retention analysis.

## 7. Migration plan

This contract is intentionally implemented incrementally:

1. **PR #28 (merged):** define lifecycle vocabulary, invariants, trust boundary, and recovery/transaction boundaries. Documentation only.
2. **PR #29:** add migration 022 and a linked `turn_resolutions` execution envelope, model, repository, lifecycle constraints, idempotency uniqueness, lease claims, and migration/model/repository tests. The live turn pipeline is not wired yet.
3. **PR #30:** wire native automatic turn execution to durable accept/prepare/commit/narration-pending/completed boundaries; generate typed consequence proposals from player intent; commit domain consequences, operation evidence, and the resulting revision atomically; retry narration without reapplying consequences. Migration 023 adds `resulting_revision` to the execution envelope.
4. **PR #31:** adapt SillyTavern to the same application use case and preserve regeneration/snapshot compatibility.
5. Follow-up work: durable manual-roll/clarification continuation, recovery worker/operational orchestration, and any multi-process deployment guarantees.

Each implementation PR must include failure-injection tests for its boundary and must preserve campaign isolation and existing API/adapter compatibility.

## 8. Explicit non-goals

- No schema or migration in this PR.
- No new generic workflow engine, message broker, event-sourcing framework, or distributed lock.
- No multi-worker deployment enablement.
- No VTT/UI work.
- No wholesale rewrite of `CampaignTurnService`, `TurnResolutionService`, or SillyTavern integration.
- No silent change to external turn identity, regeneration semantics, or historical turn records.
