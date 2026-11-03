# Current architecture map

**Snapshot:** 2026-11-03  
**Repository:** `IvanVM04/Campaign-Manager`  
**Baseline:** `main` at `5fbcb86f357350de9b77f386344d7babf6f681c0` (PR #18)  
**Method:** static source and repository-tree inspection. No local checkout or test execution was performed for this document.

## 1. Executive view

Campaign Manager is currently a **single-process, local-first modular monolith** built around FastAPI, SQLite, campaign-scoped service graphs, an in-memory `WorldState`, LLM-backed narrative/extraction services, a separate D&D 5e (2014) rules package, and a SillyTavern adapter.

That is still the right deployment and architectural direction for the product. The project does not need microservices, event streaming infrastructure, a distributed lock service, or a wholesale rewrite.

The main architectural issue is not the choice of monolith. It is that the codebase has grown from a world-state backend into several partially overlapping application workflows while most application code still lives in layer-oriented global packages (`services/`, `repositories/`, `models/`) and a single large API module.

The current architecture is best described as **a layered monolith with some domain isolation and explicit orchestration seams**, not yet as a fully enforced hexagonal architecture.

## 2. Repository shape

At the audited baseline, the repository tree contains 187 tracked files, including:

- 88 files under `models/`, `operations/`, `repositories/`, `rules_engine/` and `services/` combined only when counting those application packages (this is a file-count inventory, not a measure of code size).
- 75 Python test files under `tests/`.
- 2 JavaScript test files in the SillyTavern integration.
- 6 existing domain/architecture documents plus this new audit set.

The principal packages are:

| Package | Current responsibility |
|---|---|
| `models/` | Dataclasses, enums, state objects, request/response schemas and turn results. |
| `operations/` | Typed world and character mutation commands, including operation references. |
| `repositories/` | SQLite persistence and campaign-scoped data access. |
| `services/` | Application orchestration, domain use cases, LLM integration and state coordination. |
| `rules_engine/dnd5e_2014/` | Deterministic, ruleset-specific mechanical calculations. |
| `integrations/sillytavern/` | JavaScript extension and client-side turn-state handling. |
| `docs/` | Product, architecture and domain notes. |
| `tests/` | Python unit/integration tests and JavaScript integration tests. |

The package layout is currently organized primarily by technical layer. Domain boundaries therefore depend on import discipline and conventions rather than package-level enforcement.

## 3. Runtime composition and request scope

### Current composition

`app.py` creates a global `CampaignRuntimeFactory`. Middleware resolves the `X-Campaign-Id` header and binds the matching `CampaignRuntime` to a request-local `ContextVar`.

`CampaignRuntimeFactory`:

1. validates the campaign exists;
2. caches one runtime per campaign ID;
3. builds repositories, services, world state, provider and turn lock;
4. exposes manual invalidation.

A runtime owns the campaign-scoped world/service graph and a `TurnExecutionLock`. The lock is an in-process `threading.RLock`; it is not a distributed lock.

The README documents the local, single-process deployment boundary. That restriction is consistent with the implementation and must remain explicit.

### Composition debt

There are two composition styles in `app.py`:

- the active per-campaign `CampaignRuntimeFactory`;
- older top-level factory functions and compatibility proxies that remain in the module.

The proxies resolve through the request `ContextVar` and preserve compatibility with existing routes/tests. This is understandable during migration, but it makes the composition boundary harder to see and leaves old construction code beside the new runtime model.

The runtime factory also constructs `OllamaProvider()` directly, uses its defaults, and keeps runtimes in an unbounded dictionary. Those are lifecycle/configuration concerns, not reasons to replace the runtime model.

## 4. Current request paths

There are two distinct turn-entry paths. They share parts of the domain infrastructure but do not have the same contract.

### A. Native Campaign Manager turn: `POST /turn`

Current path:

```text
FastAPI route
  -> CampaignTurnService
      -> read fresh TurnContext + recent history
      -> release SQLite connection
      -> TurnResolutionService.prepare_turn
          -> MechanicsAdjudicator (structured LLM proposal)
          -> deterministic D&D check/save resolution where applicable
          -> DMService narrative generation
          -> LLMWorldExtractor
          -> OperationParser
          -> typed world operations
      -> open BEGIN IMMEDIATE transaction
      -> reload context and recent history
      -> reject stale plan if context changed
      -> apply operations through WorldService
      -> persist turn and state atomically
```

Important properties:

- Provider/LLM work is performed outside the authoritative write transaction.
- A fresh context/history comparison protects the commit from stale plans.
- Clarification and pending manual-roll states can return before world mutation.
- The LLM extractor rejects `CharacterOperation` values. Narrative extraction is therefore not an authorized way to change character mechanics.
- Manual pending rolls are stored in the `CampaignTurnService` instance's memory, not in SQLite; they are short-lived and lost on process restart.

The pipeline is safer than the original all-in-one transaction flow, but the **narrative is still generated before world consequences are extracted, validated and committed**. The current implementation therefore does not yet implement the desired consequence-first, commit-then-narrate pipeline.

### B. SillyTavern turn: `POST /integration/turn`

Current path:

```text
SillyTavern generates narrative
  -> FastAPI integration route
  -> SillyTavernIntegrationService
      -> LLMWorldExtractor
      -> OperationParser
      -> typed world operations
      -> BEGIN IMMEDIATE transaction
          -> validate external_turn_id / version / payload
          -> restore prior snapshot when reconciling a regeneration
          -> apply operations
          -> persist turn and snapshot
      -> commit
```

SillyTavern owns narrative generation in this path. Campaign Manager supplies context and processes the returned narrative into persistent world changes.

The integration has meaningful versioning, idempotency and snapshot-reconciliation behaviour. However, this path does not run the native `MechanicsAdjudicator` and deterministic check pipeline. The extractor rejects character-mechanical operations, so this integration must not be treated as a complete D&D adjudication path.

The two paths are legitimate adapters, but their shared application contract is not yet explicit enough. Future work should make the distinction deliberate and prevent the adapter from bypassing authoritative mechanics or consequence validation.

## 5. Other major workflows

### Combat

- `CombatEncounterService` manages encounter lifecycle, initiative and turn progression.
- `CombatAttackService` performs attack resolution and persists encounter/character HP changes transactionally.
- Rules calculations live in `rules_engine/dnd5e_2014/combat/` and `rules_engine/dnd5e_2014/weapons/`.
- Encounter state is a persisted combat snapshot. Player-character HP is also stored in `character_states`; the attack service checks that the two values agree before resolving an attack and updates them together.

This is a useful transactional boundary, but it creates a deliberate duplicated representation of some mechanical state. The ownership and synchronization contract must be documented and tested whenever new mechanics are added.

The current combat implementation is a partial rules slice, not a complete D&D combat engine. The attack service explicitly rejects unsupported special/ammunition weapon behaviour.

### Persistent effects and campaign clock

- `PersistentEffectService` manages campaign-scoped effects attached to entities.
- `EffectiveConditionService` projects applicable effects into condition data used by consumers such as combat.
- `CampaignClockService.advance()` advances fictional time under `BEGIN IMMEDIATE` and expires due campaign-time effects in the same transaction.

The effect is a persistent campaign entity; the clock is campaign-level state; combat conditions are consumed as a derived/effective representation. This is a good direction, provided derived conditions are not independently persisted as a second source of truth.

### World state

`WorldService` owns a mutable in-memory `WorldState` for a campaign, delegates mutations to appliers and persistence to repositories. It uses working copies for atomic multi-operation application. The database is the durable record; the in-memory world is a runtime representation that must be reloaded or restored consistently after failures and regeneration.

## 6. Persistence and transaction model

- SQLite is the only persistence adapter currently visible.
- Schema evolution is centralized in `migrations.py`; `CURRENT_VERSION = 20`.
- Repositories accept caller-supplied connections in many operations, allowing services to compose multi-repository transactions.
- Several services still import `get_conn()` directly and choose transaction boundaries themselves.
- Campaign scoping is represented by `CampaignScope` in multiple repositories, and migrations add campaign ownership/reference safeguards.
- Turn history stores external IDs, versions, status and snapshots to support SillyTavern reconciliation.

The ability to pass a shared connection is a useful transaction seam. The weakness is that transaction ownership is distributed across service methods rather than represented by a named Unit of Work/application transaction abstraction.

## 7. Rules engine boundary

The rules engine is the clearest architectural boundary in the repository:

- it is separated by ruleset (`dnd5e_2014`);
- core dice, abilities, proficiency and skills are isolated;
- checks, saves, initiative, attacks, damage and conditions have deterministic modules;
- tests can exercise the rules package without starting FastAPI or an LLM.

Keep this isolation. Do not move rules calculations into API routes, prompt code, or persistence repositories.

The current implemented scope remains partial. The presence of a rules package must not be confused with complete character progression, spellcasting or combat coverage.

## 8. External interfaces

- FastAPI is the backend API and currently defines routes, middleware, serialization, error translation and legacy composition in `app.py`.
- SillyTavern is an external client adapter, implemented in JavaScript and served through the API.
- No standalone player-facing web frontend is present in the audited tree.
- VTT/tactical map infrastructure is not present and remains out of MVP scope.

## 9. Intended target shape

Retain a modular monolith and evolve toward explicit ports/adapters:

```text
HTTP API / SillyTavern adapter / future Web UI
                 |
                 v
        Application use cases
   turn orchestration, combat, clock,
   campaign management, effect lifecycle
                 |
        +--------+---------+
        |                  |
        v                  v
   Domain models      Rulesets
   invariants         D&D 5e 2014
        |                  |
        +--------+---------+
                 |
          Application ports
                 |
        +--------+---------+
        |                  |
        v                  v
   SQLite adapter      LLM adapters
   repositories        provider clients
```

This is a direction, not a request to introduce every layer immediately. Add abstractions where they protect a real domain or transaction boundary.

## 10. Verification limits

This document is based on static inspection of the default-branch tree and selected source ranges. It does not claim:

- that Python, Ruff or JavaScript tests were executed during this audit;
- that all routes, imports, migrations or SQL constraints were exhaustively inspected;
- that concurrency behaviour was tested under multiple processes;
- that the current D&D implementation is rules-complete.

The CI workflow defines Python tests excluding `real_llm`, Ruff lint and JavaScript tests. A green workflow run must be checked separately before merging changes.
