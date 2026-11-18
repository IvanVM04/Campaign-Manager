> **Historical proposal — superseded by the implemented durable lifecycle.** This file records the original PR #28 design and its then-future migration plan. Its statements that the current flow is narrative-first, that manual-roll/clarification continuation is a follow-up, and that `turn_resolutions` is not implemented are obsolete. Use [the active turn-pipeline contract](turn-pipeline-compatibility.md), [durable execution boundary](durable-turn-execution-boundary.md), [SillyTavern adapter contract](sillytavern-durable-turn-adapter.md) and the [current system state](current-state-2026-11-18.md) for present behaviour. The original proposal is retained unchanged below for architectural history.

# Durable turn-resolution lifecycle contract

**Status:** implemented current application contract, verified 2026-11-18  
**Code baseline:** `f4fb3914ebab4579118863796e6f6d4b7183d0cf` (PR #255)  
**Schema:** 34  
**Scope:** native campaign turns and external adapters, including SillyTavern.

This page describes the implemented durable lifecycle. The historical design was proposed in PR #28 and implemented incrementally in PRs #29–#31 and subsequent hardening. The document is no longer a proposal. Current source and tests take precedence if a future implementation changes a detail.

## 1. Purpose and authority

A logical player action has one durable resolution. Domain consequences are committed at most once. Narration is a separate, retryable presentation of the committed outcome.

| Responsibility | Owner |
|---|---|
| Request identity, idempotency, lifecycle transitions and recovery | Durable turn application services |
| Intent interpretation | `IntentInterpreter` and validated `PlayerIntentAnalysis` |
| Canonical identity and visible-reference selection | Deterministic context/application resolvers |
| Mechanics decision | `MechanicsAdjudicator` |
| Random rolls and supported calculations | Deterministic rules/application code |
| Candidate world consequences | Structured LLM proposal pipeline |
| Permission, semantic validation and mutation | Domain/application services and world appliers |
| Persistence | Repositories using caller-owned transactions |
| Presentation | Native `DMService` or an external client such as SillyTavern |

LLM output is untrusted. It cannot assign canonical IDs, grant permissions, select dice results, write SQLite or override committed mechanics. Narration is not a source of world operations.

## 2. Domain vocabulary

- **Turn request:** player input plus campaign scope, idempotency/adapter identity, conversation identity when applicable, and roll mode.
- **Turn context:** consistent campaign/session/character/world/history projection plus the captured campaign revision.
- **Intent analysis:** validated, versioned semantic interpretation of the player's message. V1 remains readable; V2 carries action frames and directed relation claims.
- **Challenge:** a durable clarification or manual-roll request that pauses the same logical turn.
- **Prepared plan:** validated structure/proposal and expected context revision persisted before domain mutation.
- **Committed resolution:** the durable record of the accepted intent, validated consequences, mechanics/operation evidence and resulting campaign revision.
- **Narration:** user-facing prose based on committed evidence. It never authorizes another mutation.

## 3. Implemented lifecycle

The durable record uses these lifecycle states:

| State | Meaning | Allowed next states |
|---|---|---|
| `accepted` | The logical request identity has been claimed. | `planning`, `rejected` |
| `planning` | Context, intent, mechanics and consequence proposal are being prepared. Provider work is outside write transactions. | `accepted` (retry/reclaim), `awaiting_input`, `prepared`, `rejected` |
| `awaiting_input` | A player clarification or manual d20 result is required; challenge details and context revision are persisted. | `planning`, `rejected` |
| `prepared` | Proposal and expected revision are persisted; domain consequences have not yet been applied. | `committed`, `rejected` |
| `committed` | Consequences, operation results and resulting revision were committed atomically. | `narration_pending` |
| `narration_pending` | Consequences are committed; narration or its persistence still needs completion. | `completed` |
| `completed` | Presentation is persisted. | terminal |
| `rejected` | The request/proposal was rejected before consequence commit. | terminal |

A commit never returns to planning. A new player correction after a committed turn is a new logical action; pending clarification is not.

## 4. Entry points

### Native API

- `POST /turn` — start or resume a native durable turn; optional `Idempotency-Key`; `dice_mode` is `automatic` or `manual`.
- `POST /turn/clarification` — submit a response to a pending clarification.
- `POST /turn/roll` — submit the requested manual d20 result(s).
- `GET /turns` — read campaign/session transcript records.

### SillyTavern adapter

- `POST /integration/context` — context/history projection.
- `POST /integration/turn/resolve` — claim and resolve the player action before SillyTavern narration.
- `POST /integration/turn/clarification` and `/roll` — continue the original request.
- `GET /integration/turn/{external_turn_id}` — transcript state.
- `GET /integration/turn/{external_turn_id}/clarification` and `/manual-roll` — challenge recovery projections.
- `POST /integration/turn/complete` — persist narrative/version against the already committed resolution. It does not apply consequences.

SillyTavern uses a stable `external_turn_id` for the player action and a required `conversation_id` to scope history and challenge ownership. The old narrative-first `POST /integration/turn` endpoint is removed and returns 404. See the [adapter contract](sillytavern-durable-turn-adapter.md).

## 5. Intent, mechanics and consequence stages

The production turn path uses separate roles:

1. `IntentInterpreter` receives current player evidence, bounded same-chat history and compact visible context. It returns one `PlayerIntentAnalysis`.
2. Model output is schema-checked and literal evidence is validated. Deterministic resolvers attach canonical entity IDs only after campaign, activity, visibility and ambiguity checks.
3. `MechanicsAdjudicator` runs only for an actionable, non-clarification active step with a usable active character. It returns a mechanics decision, not a roll result.
4. Application/rules code computes supported mechanics. Automatic dice use the backend random source; manual mode requests player-supplied values and validates them against the stored challenge.
5. The structured consequence proposer receives the same validated analysis, trusted resolved references, bounded detached world projection and confirmed mechanics. It does not reinterpret the raw player message.
6. Domain services validate permissions, scope, entity existence, ownership, resource constraints and operation preconditions before applying mutations.
7. Narration uses the committed result.

Questions, reports, hypotheticals, negations, non-actionable observations and ambiguous references must not accidentally authorize mechanics or persistent operations.

## 6. Durable challenge continuation

Clarification and manual-roll challenges are stored with the durable resolution (including challenge state in the persisted adjudication payload). They are not merely held in a transient service dictionary.

- A challenge is tied to its original resolution and, for the external adapter, its conversation.
- The answer/result is validated against the stored challenge and context revision.
- The original intent analysis is reused for manual-roll continuation.
- Pending-intent clarification applies literal, bounded edits to the stored analysis and preserves untouched fields.
- Accepted manual-roll submissions are idempotent; conflicting results for the same accepted challenge are rejected.
- SillyTavern can query challenge state again after a browser/extension restart.
- Repeated clarification rounds continue the same durable turn; the answer is not treated as a new player action.

The current clarification primitive is not the full product-level configurable uncertainty system. A calibrated confidence threshold and general resumable checkpoint model for arbitrary partially resolved compound steps remain future requirements (see product requirements FR-AI-11–14).

## 7. Idempotency, stale-context protection and transactions

1. The request has a stable identity scoped by campaign and adapter/client namespace.
2. A request fingerprint covers fields that alter meaning, including player input, session, dice mode and conversation identity where applicable.
3. Same identity plus same fingerprint returns/resumes the existing request; a conflicting fingerprint is rejected.
4. Planning reads a consistent context and campaign revision.
5. Provider calls and narration occur outside SQLite write transactions.
6. Before commit, the application checks campaign scope, current revision, request/challenge identity, lease ownership, and operation preconditions.
7. Consequence application, operation outcomes, resolution transition and resulting campaign revision commit together in a short `BEGIN IMMEDIATE` transaction.
8. Failures roll back database changes and restore the in-memory publication boundary; stale plans are rejected/replanned rather than applied to a different world.

The campaign-local `TurnExecutionLock` serializes workflows inside the supported single process. It is not a distributed lock and does not support multiple Uvicorn workers.

## 8. Narration, retries and regeneration

- Consequences commit before the client generates or stores the narrative.
- A narration/provider failure after commit leaves the resolution resumable at `narration_pending`.
- Retrying the same logical request cannot repeat damage, resource consumption, event creation, item transfer or mechanics.
- SillyTavern swipes/regenerations create transcript/narrative versions against the same committed outcome. They do not restore snapshots, rerun the rules engine or apply world operations again.
- The completion endpoint validates identity/version and persists presentation only.

There is no background recovery worker. Recovery is request-driven by a retry or a client reading the durable turn/challenge state. Do not describe or build a worker as if it already exists.

## 9. Persistence and migrations

The durable execution envelope is stored in `turn_resolutions`, linked to transcript/turn records and protected by database constraints and lifecycle-specific repository checks. The record includes conversation scope, lifecycle state, versioned `intent_json`, proposal/mechanics/adjudication evidence, context/resulting revisions and lease/retry metadata.

- Migration 022 introduced the durable resolution envelope.
- Migration 023 added the resulting campaign revision.
- Migration 033 added persisted versioned intent analysis and source fingerprint, with protection against editing committed evidence.
- Migration 034 added SillyTavern conversation identity and scoped history indexes.
- Current `CURRENT_VERSION` is 34.

Historical snapshot JSON is retained in the inert `turn_snapshot_archive` table by migration 029. It is not read/restored at runtime.

## 10. Explicit limitations

- One active-character pointer currently drives the campaign turn context; configurable simultaneous multi-PJ control is not implemented.
- NPC delegation requests/approvals/revocation are product requirements, not current domain contracts.
- The confidence threshold and arbitrary partial compound-turn checkpointing described in product v0.2 are not yet implemented.
- Supported mechanics remain a deterministic subset of D&D 5e 2014.
- The application is local, single-user, single-process and single-worker.
- A green deterministic CI run does not prove live Ollama semantic quality or a real SillyTavern session.

## 11. Historical design record

PR #28 introduced the initial proposal and invariants; PRs #29–#31 delivered the initial durable store/native flow/adapter integration. This page now documents the implemented contract. The historical PR descriptions and earlier architecture snapshots remain evidence of their original proposal/implementation sequence, not current status.
