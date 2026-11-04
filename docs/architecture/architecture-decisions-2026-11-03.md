# Architecture decisions

**Date:** 2026-11-03  
**Baseline:** `main` at `5fbcb86f357350de9b77f386344d7babf6f681c0`

This is the decision record for the current consolidation phase. Each decision distinguishes what we keep, what we change and what we deliberately defer.

## ADR-001 — Keep a local-first modular monolith

**Status:** Accepted

**Decision:** Keep one deployable application with explicit internal modules and adapters.

**Why:** The product is a single-player local campaign manager. Current scale and deployment goals do not justify distributed services. SQLite, a campaign-scoped runtime and a single process are appropriate for the MVP.

**Consequences:**
- Keep campaign isolation inside one application process.
- Do not introduce service-to-service APIs, message brokers or distributed transactions.
- Keep the single-worker deployment restriction explicit.
- Make module boundaries stronger before considering deployment decomposition.

## ADR-002 — Keep D&D rules deterministic and ruleset-specific

**Status:** Accepted

**Decision:** Mechanical calculations belong in `rules_engine/<ruleset>`, independent from FastAPI, persistence and LLM providers.

**Why:** Model output is probabilistic and must not be the authority for dice, modifiers, damage or state invariants. A future ruleset must not silently mix with the 2014 implementation.

**Consequences:**
- AI may propose intent interpretation, circumstances, check type and DC within a validated contract.
- The rules engine calculates outcomes from trusted inputs.
- Character mechanics are mutated only through authorized application commands.
- A 2024 ruleset, if added, is a separate module and configuration, not scattered conditionals.

## ADR-003 — SQLite remains the MVP persistence engine

**Status:** Accepted

**Decision:** Retain SQLite and the migration-based schema for the local-first MVP.

**Why:** The deployment is local/single-user and current repository boundaries already support explicit transactions and campaign scoping.

**Consequences:**
- Preserve foreign keys, campaign scoping and migration tests.
- Use short write transactions and `BEGIN IMMEDIATE` where a use case requires serialized validation + mutation.
- Do not migrate to PostgreSQL for hypothetical scale.
- Revisit only if multi-user/remote deployment or measured write contention becomes a real requirement.

## ADR-004 — Campaign scope is mandatory at application and repository boundaries

**Status:** Accepted

**Decision:** Every campaign-owned operation must carry an explicit campaign ID/scope; no implicit campaign-1 fallback.

**Why:** Multiple campaigns in one local installation must remain isolated.

**Consequences:**
- Keep `X-Campaign-Id` as a selector, not an authentication credential.
- Repository methods must include campaign ownership in queries and mutations.
- Database constraints/triggers remain defence in depth.
- Background tasks must carry explicit campaign scope.

## ADR-005 — Use one application contract for turn consequences

**Status:** Accepted as target; implementation incomplete

**Decision:** Native API and external clients should be adapters around a shared application-level turn/consequence contract. They may differ in who generates prose, but not in authorization, mechanics verification, domain validation or persistence guarantees.

**Why:** The current native `/turn` and SillyTavern `/integration/turn` paths have different authority and rules guarantees.

**Target sequence:**

1. Receive player intent and client metadata.
2. Build a consistent campaign context.
3. Interpret intent and resolve clarification.
4. Adjudicate circumstances and produce a validated mechanics request.
5. Resolve deterministic mechanics.
6. Produce structured world-consequence proposals.
7. Validate actor authority, target identity, preconditions and campaign scope.
8. Persist the accepted resolution atomically with idempotency metadata.
9. Generate or regenerate narrative from the committed resolution.

**Consequences:**
- Narrative text is not a command source of truth.
- External adapters cannot bypass the application use case.
- Narration retries must not reapply mechanics or world consequences.
- Keep compatibility wrappers while migrating clients.

## ADR-006 — Character mechanics are canonical; encounter PC state is a projection

**Status:** Accepted

**Decision:** Persistent `CharacterState` owns a player character's durable mechanical state. An encounter stores the state needed to resolve its turn order and combat, but PC values synchronized with the character record must be committed atomically.

**Why:** The same PC participates in campaign play outside combat and must not acquire conflicting HP/condition values.

**Consequences:**
- HP mutation must use one application use case aware of active encounter participation.
- Keep the current equality check and atomic HP update.
- Decide NPC persistence separately before extending the model.
- Do not persist multiple competing condition representations.

## ADR-007 — Persistent effects are authoritative; effective conditions are derived

**Status:** Accepted

**Decision:** Persistent effects own source, identity, duration and lifecycle. Effective conditions are computed projections consumed by rules and application services.

**Why:** This avoids stale duplicated state as campaign-time and round/turn durations evolve.

**Consequences:**
- Campaign clock advancement and due effect expiry remain atomic.
- Design round/turn duration expiry before implementing it.
- Consumers should query/project effective conditions rather than mutate them independently.

## ADR-008 — Introduce ports and Unit of Work selectively

**Status:** Accepted

**Decision:** Add interfaces only around meaningful boundaries: transaction ownership, provider calls, and application-facing persistence contracts. Do not abstract every class or SQL statement.

**Why:** Repositories already offer useful seams and optional connection injection. The actual gap is the lack of an explicit application transaction contract and concrete dependencies in services.

**Consequences:**
- Start with a small Unit of Work/transaction runner used by one critical use case.
- Preserve SQLite-specific implementation in infrastructure.
- Avoid a generic repository framework or ORM migration.

## ADR-009 — API routes are transport adapters

**Status:** Accepted

**Decision:** FastAPI routes should validate transport data, call use cases and serialize results. They should not own game rules, transaction logic or service composition.

**Consequences:**
- Extract routers by capability without changing public paths.
- Keep one composition root.
- Centralize stable error mapping.
- Preserve middleware campaign scoping and compatibility during migration.

## ADR-010 — Single-process runtime is an explicit MVP constraint

**Status:** Accepted for MVP

**Decision:** Keep process-local runtime caches and locks for now, but document their limitations and provide lifecycle invalidation.

**Why:** Distributed locking and multi-worker cache coherence are unnecessary for the current local deployment.

**Consequences:**
- Do not run multiple Uvicorn workers against the current runtime model.
- Add cache eviction/invalidation and provider settings before runtime count/configuration grows materially.
- Persist pending manual rolls only if restart-resilient manual rolling is required by the product.

## ADR-011 — No VTT until the core campaign loop is reliable

**Status:** Accepted

**Decision:** Defer tactical maps, token movement, fog of war and real-time tabletop collaboration.

**Why:** They add UI and synchronization complexity before character, world, rules and turn resolution are complete.

**Consequences:** Focus on the standalone campaign and AI-DM experience first.


## ADR-012 — Make turn resolution durable and narration retryable

**Status:** Accepted as target; implementation incomplete (PR #28 contract)

**Decision:** A turn is a durable application lifecycle. Its accepted request identity, prepared consequence proposal, atomic consequence commit, and narration completion are distinct stages. Consequences are committed exactly once; narration is generated only after commit and can be retried without replaying domain mutations.

**Why:** The current native path generates prose before extracting persistent operations and stores the narrative alongside consequence application. Historical `TurnRecord` data and campaign state revisions provide useful foundations, but do not yet represent a restart-resilient lifecycle or a separately retryable narration stage.

**Consequences:**
- Use one shared application contract for native API and external adapters.
- Enforce idempotency in persistence using campaign + adapter namespace + request key and a request fingerprint.
- Revalidate the prepared context revision and domain preconditions inside the consequence commit transaction.
- Persist the accepted resolution and its outcomes atomically with domain mutations.
- Treat AI consequence output as untrusted structured proposals; narrative is not the source of truth.
- Generate narration after commit; narration retries never reapply consequences or reroll mechanics.
- Evolve the existing turn persistence deliberately; do not create a parallel turn history or revision system.
- Keep SQLite, short write transactions, and the current single-process deployment constraint.

See [Durable turn-resolution lifecycle contract](turn-resolution-lifecycle.md) for lifecycle states, transition rules, transaction boundaries, recovery, and migration sequencing.
