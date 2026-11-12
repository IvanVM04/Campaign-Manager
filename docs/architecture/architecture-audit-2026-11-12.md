# Architecture and modularity audit — 2026-11-12

**Repository:** IvanVM04/Campaign-Manager  
**Baseline:** `main` includes PR #202 (`1bf805c`). PR #201 extracted durable turn execution; PR #202 integrated combat transaction hardening, world operation coordination, bounded-context request schemas and the ordered migration registry.  
**Scope:** capability boundaries, durable turn workflow, LLM proposals, SillyTavern integration, snapshot migration and next structural hotspots.

## Executive assessment

The project is a modular monolith with eight implemented capability packages: campaign, characters, combat, context, llm_world, providers, turns and world. Do not rewrite it as microservices. The immediate cleanup objective was to remove the parallel legacy turn architecture, not replace the active one.

This cleanup consolidates the system around one turn contract: player intent is interpreted into a bounded structured proposal; deterministic mechanics and application code validate and commit consequences; narrative is generated from committed evidence; retries, clarifications, manual rolls and transcript versions resume the same durable resolution rather than replaying consequences.

## Verified design after this cleanup

### Capability boundaries

The old flat service re-export layer and runtime proxies remain retired. Bootstrap owns composition. API routers obtain request-scoped runtime services. The SillyTavern adapter is isolated under `integrations/adapters/silly_tavern` and owns active context/history and external transcript-state reads only.

No compatibility façade should be added merely to preserve an old import path. New code imports from the owning capability package.

### Single LLM proposal pipeline

`LLMWorldExtractor` exposes the structured player-intent `propose()` workflow. The old `extract()` / callable facade, narrative-first prompt builder and static legacy prompt sections have been removed.

The active path is:

`TurnResolutionService` -> `ContextBuilder.build_proposal_context()` -> `ProposalContextSelector` -> `LLMWorldProposalPromptBuilder` -> `LLMWorldResponseParser` -> `WorldService`.

Context selection preserves the active character and current location, expands dependencies, excludes secret events and creates a detached `WorldContextProjection`. Prompt, selected context, response and one repair request have independent bounded budgets. Model output is untrusted; semantic validation, authorization and mutation remain downstream.

The model receives player intent and confirmed mechanics, not already-generated narrative to reverse-engineer consequences. `TurnResolutionService` separates proposal, apply and narration phases. The durable coordinator commits before narration and does not hold a write transaction while calling a provider.

### SillyTavern integration

The deprecated `POST /integration/turn` narrative-first mutation endpoint and its `LegacySillyTavernTurnService` have been removed. The active extension contract remains:

- `POST /integration/context`
- `POST /integration/turn/resolve`
- `POST /integration/turn/roll`
- `POST /integration/turn/clarification`
- `GET /integration/turn/{external_turn_id}`
- `GET /integration/turn/{external_turn_id}/clarification`
- `GET /integration/turn/{external_turn_id}/manual-roll`
- `POST /integration/turn/complete`

The adapter façade keeps context/history and transcript-state reads. It does not perform mutation, narrative extraction or snapshot reconciliation. Completion requires a stable external turn ID.

### Historical snapshot data

The runtime `turns.snapshot` field, its repository and all restoration consumers have been removed. Migration 029 copies every non-null historical snapshot payload into `turn_snapshot_archive` and drops the column from the active `turns` table. The archive is inert and intentionally has no runtime reader or writer. Existing campaign/turn history is retained.

The migration is forward-only. It does not change earlier migration history. Migration tests cover payload preservation, column removal and safe rerun.

### Transactions and persistence

The durable turn workflow preserves stable external-turn idempotency, campaign revision checks and lease fencing, a short atomic commit for canonical state and durable resolution, narration/provider calls outside the write transaction, recovery after process restart or provider/narration failure, and no replay of consequences when narrative versions change.

The rules engine remains pure and repository-free. Application services own transaction boundaries and pass the caller-owned connection to repositories.

## World visibility and deployment boundary

The earlier audit found that `GET /world` and `GET /world/events` could expose events marked `secret=true`, although memory search and export already filtered them. The central `WorldVisibilityPolicy` now applies the same player-safe rule to the world overview, event collection, memory search/context and export paths. Collection filtering happens before search, pagination and total calculation.

The application remains single-user/local-first. `X-Campaign-Id` is campaign selection, not authentication, and CORS is not an authorization boundary. No unauthenticated GM bypass is provided. A GM read model, multi-user access or remote deployment requires verified identity plus per-campaign authorization before secret data can be exposed. Keep the documented loopback bind and single-process runtime assumptions until that work is implemented.

## Combat profile and NPC metadata boundary

NPC/player attack-profile selection is isolated in `services/combat/attack_profile_resolver.py`. It reads canonical character/equipment or campaign-scoped creature state on the attack transaction connection and returns an immutable `ResolvedCombatAttackProfile`. Weapon and natural-attack numerical bonuses are derived in the pure `rules_engine`; the application resolver does not persist state or roll dice.

Encounter creation merges supplied NPC melee profiles, natural attacks and defenses into one creature-state save inside the existing `IMMEDIATE` transaction. Runtime resolution validates persisted metadata again and fails closed if it is malformed. The legacy single `npc_melee_attack` field remains a read fallback for already-persisted creatures; new data writes the list form plus that first-profile field during migration.

## Verified boundaries and remaining structural work

| Area | Current finding | Next safe improvement |
|---|---|---|
| `DurableNativeTurnService` | Stable public façade/composition point; request idempotency, planning leases, pre-commit recovery and typed failures are behind dedicated collaborators (PR #201). | Preserve the public API, lease fencing, challenge continuation and restart recovery; decompose only when a new lifecycle boundary owns a distinct invariant. |
| `CombatAttackService` | Coordinates attack validation, effects, rolls and atomic HP/encounter persistence; profile selection now belongs to `AttackProfileResolver`. | Keep the facade as the transaction owner; add future weapon/action families through typed profile contracts and deterministic rules helpers. |
| `CombatEncounterService` | Every mutating encounter use case owns one explicit `IMMEDIATE` transaction; `complete()` now uses the shared transaction helper. | Failure-injection tests cover create, death-save HP synchronization, turn/effect expiration, completion, movement and reaction rollback. Keep canonical HP and encounter projections in the same transaction. |
| `WorldService` | Stable facade for world state and appliers; mixed turn-operation dispatch/transaction coordination extracted to `WorldTurnOperationCoordinator`. | Preserve the facade signature, shared `WorldState` identity, operation ordering, reference resolution and caller-owned connection semantics. |
| `models/schemas.py` | Backward-compatible import facade over campaign, character, world, turn and integration schema modules. | Production routers import from the owning bounded context; keep facade exports and OpenAPI contracts stable. |
| `migrations.py` | Ordered historical functions 001–029 plus the explicit `MIGRATIONS` metadata/runner registry. | Keep historical bodies in chronological order; use [the migration catalogue](migration-catalog-2026-11-12.md) and preserve fresh/upgrade/idempotency tests. No schema-version change in this consolidation. |

## Consolidation integrated in PR #202

- Combat transaction ownership was made uniform for encounter completion and failure-injection tests verify rollback across writes to encounter snapshots, canonical character HP and timed effects.
- `WorldService.apply_turn_operations()` remains the public entrypoint and delegates to `WorldTurnOperationCoordinator`; caller-supplied connections and in-memory state identity are preserved.
- API request schemas are split into campaign, character, world, turn and integration modules. `models.schemas` remains a compatibility facade; routers now import their bounded-context schemas directly.
- The migration runner now uses a contiguous, named `MigrationDefinition` registry and has a [human-readable migration catalogue](migration-catalog-2026-11-12.md). Historical migration functions remain in their original file/order; `CURRENT_VERSION` stays 29.

## Cleanup disposition

### Retired

- RuntimeProxy and module-level runtime proxies.
- CampaignTurnService.
- Flat service re-export modules.
- Narrative-first `LLMWorldExtractor.extract()` and callable facade.
- Legacy static extraction prompt builder and its prompt-section modules.
- Deprecated `POST /integration/turn` endpoint and `LegacySillyTavernTurnService`.
- `WorldSnapshotRepository`, runtime `TurnRecord.snapshot` and `turns.snapshot` column.
- Regeneration/retry tests that exercised only snapshot restoration and narrative-first mutation.

### Preserved

- The current durable native and SillyTavern endpoints.
- External-turn idempotency, version/status history and challenge recovery.
- Historical snapshot JSON in `turn_snapshot_archive`.
- Earlier migration functions and schema upgrade history.

Do not recreate retired paths. Any future external integration must call the durable resolve/complete lifecycle and carry a stable external turn identity.

## Acceptance policy

Every implementation PR starts from the latest integrated `main`, has one coherent architectural objective, searches production/tests/scripts/docs for all affected consumers, preserves contracts/campaign scope/idempotency/transaction ownership, updates package and global docs, and passes Ruff, deterministic Python tests, JavaScript tests, required Pyright scopes, repository-wide Pyright and both CodeQL checks. Live Ollama and manual SillyTavern smoke tests are reported separately.

Do not merge while a required CI check is failed, pending, cancelled or skipped.
