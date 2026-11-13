# Campaign Manager — architecture map for maintainers and coding agents

**Verified base:** `main` at `60def5d19167ccd31ebce82d8f2d1fe4a72c26e0` (2026-11-13, PR #215 merged).  
**Purpose:** provide one fast, source-linked navigation map. This is an index and work register, not a replacement for package documentation or lifecycle contracts.

> **Phase 1 retrieval update — PR #212:** the SillyTavern action is now the
> primary retrieval query and configured campaign-scope wording is an independent
> optional query. The context pipeline merges and deduplicates the two signals;
> descriptive entity matching can resolve a role inside a longer player sentence
> and still reports ambiguity on comparable candidates while retaining their
> descriptive evidence for retrieval (without resolving one canonical ID).
> Pronoun continuity and semantic paraphrase matching remain open work. See the
> [AI world-understanding roadmap](../quality/ai-world-understanding-roadmap-2026-11-12.md).

## Current P0 — shared language understanding

PR #215 merged the versioned `PlayerIntentAnalysis` contract, shared
mechanics/proposal interpretation and durable evidence persistence (migration
033); its deterministic tests and CodeQL checks passed. Live Ollama and manual
SillyTavern acceptance remain open. [PR #216](https://github.com/IvanVM04/Campaign-Manager/pull/216)
extends this P0 work with a bounded visibility-filtered conversation resolver,
chat-scoped durable history (migration 034) and native Ollama JSON Schema
generation. It must pass complete deterministic CI before merge; live model
and multi-chat SillyTavern acceptance remain separate gates. Do not start
Character Builder or broad gameplay expansion until the P0 live gates are
recorded. See the [P0 specification](../quality/language-understanding-priority-2026-11-13.md).

## How to work in this repository

Read in this order before editing:

1. This map for package ownership, major entrypoints and current refactoring risks.
2. The current architecture audit for priorities and verified dispositions.
3. The capability dependency matrix before adding or moving imports.
4. The relevant package README for local responsibilities and TODOs.
5. The matching lifecycle, persistence or LLM-boundary contract before touching those invariants.
6. The quality audit before changing workflows, tests or checks.

Use code search only after identifying the owning package. Prefer canonical package imports and inspect consumers before removing a module, route, field or test. Dated audits record historical states; do not execute old recommendations without revalidation.

## Repository shape

For per-module detail outside the eight service packages, see [the shared-layer module catalogue](module-catalog-2026-11-12.md). For multi-layer edits, use the [change-impact map](change-impact-map-2026-11-12.md) to identify consumers, transaction participants and required regression tests.

| Layer | Owns | Must not own |
|---|---|---|
| api | FastAPI routers, input/output mapping, HTTP error translation and request-bound runtime access | composition, repositories created per request, domain rules or long-running workflows |
| bootstrap | Composition root and per-campaign runtime construction | transport contracts, business decisions or domain persistence rules |
| integrations/adapters | External-client translation and adapter façades | API routers, bootstrap imports or capability-package ownership |
| models | Domain state, value objects, typed projections and transport schemas where explicitly named | repositories, provider calls or service orchestration |
| operations | Typed world/character commands and operation references | parsing model text or performing mutations |
| repositories | SQLite persistence and aggregate hydration | FastAPI, LLM calls, turn orchestration or game-rule decisions |
| rules_engine | Deterministic D&D mechanics and immutable rules data | models, repositories, SQLite, HTTP, providers or orchestration |
| services | Application use cases grouped by capability | inward dependencies on API/bootstrap or arbitrary cross-package imports |
| tests | Observable contract, regression, migration, boundary and integration coverage | weakening assertions to make refactors easier |

The intended shape is a local-first modular monolith. Do not introduce microservices, a message bus, vector database, distributed cache or a generic service framework without a concrete product requirement.

## Composition and request path

- app.py creates the FastAPI application and middleware.
- bootstrap/campaign_runtime.py creates CampaignRuntimeFactory and composes per-campaign collaborators.
- api/runtime_context.py binds the selected CampaignRuntime to the current request.
- api/routers obtains services through get_current_runtime(); routers translate transport, they do not construct runtime objects.
- A runtime is process-local and cached by campaign. The current supported deployment assumption is one process/worker.

## Main execution paths

### Native durable turn

1. api/routers/turns.py receives the native turn request.
2. The request-scoped CampaignRuntime exposes DurableNativeTurnService.
3. `DurableNativeTurnService` is the stable façade; `DurableTurnExecutionService` owns request identity/idempotency, planning leases, proposal preparation and recovery before commit.
4. services/turns/turn_resolution_service.py orchestrates mechanics and player-intent proposal preparation.
5. services/context builds a detached, ranked WorldContextProjection for the intent.
6. services/llm_world builds a bounded proposal prompt, calls the injected provider and validates model output.
7. services/world applies typed operations using repositories inside the caller-owned transaction.
8. DurableNativeTurnService persists the result before narration; narration/retries must never replay committed consequences.

Critical contracts: turn-resolution lifecycle, durable persistence, idempotency keys, revision fencing, lease fencing, short write transactions, recovery after provider/narration failure.

### SillyTavern

- integrations/adapters/silly_tavern/context_adapter.py translates active context/history and external transcript-state contracts.
- integrations/adapters/silly_tavern/service.py is a thin read-only façade exposing context and transcript-state queries.
- bootstrap/campaign_runtime.py wires the adapter; durable turn services own all state-changing operations.
- The supported mutation lifecycle is resolve -> challenge continuation (if needed) -> complete.
- The narrative-first POST /integration/turn route, LegacySillyTavernTurnService and snapshot restoration have been removed.
- Migrations 029–034 archive legacy snapshots, persist character rest data, aliases and event epistemic metadata, save shared intent evidence, and add SillyTavern chat identity. The branch schema version is 34.

### Combat attack

1. api/routers/combat.py validates transport schemas and obtains the current runtime.
2. services/combat/combat_attack_service.py owns the atomic use case, loading state, applying the calculated result and synchronizing canonical HP with encounter projections.
3. rules_engine/dnd5e_2014/combat owns attack rolls, damage modifiers, hit-point transitions, death saves, conditions and movement mechanics.
4. repositories own persistence. The attack and both HP snapshots must remain within one IMMEDIATE transaction.

A combatant's CharacterState or CreatureState is canonical for HP; EncounterState combatants are projections that must be checked for staleness before write.

## Capability package catalogue

### services/campaign

| Module | Responsibility | Next improvement / guard |
|---|---|---|
| campaign_state_service.py | Campaign/session state and turn-context assembly | Keep world mutation behind the world state port. Runtime invalidation/shutdown lives in the bootstrap factory; add lifecycle hooks only when campaign deletion/configuration workflows need them. |
| campaign_clock_service.py | Campaign clock reads, advancement and effect-expiry coordination | Preserve deterministic expiry and campaign-scoped reads. |
| persistent_effect_service.py | Persisted campaign effect lifecycle | Audit effect lifecycle transaction ownership with combat, without creating a second source of condition state. |
| effective_condition_service.py | Derived ConditionSet from active effects | Keep it a projection; do not persist duplicate condition flags. |

### services/characters

| Module | Responsibility | Next improvement / guard |
|---|---|---|
| character_creation_service.py | Character/entity creation and optional activation | Revisit owned versus caller-provided connection support; retain the documented creation transaction contract until changed with tests. |
| character_service.py | Character state use cases such as HP changes | Keep canonical HP mutation here for characters outside combat; combat transactions pass their connection. |
| character_sheet_query_service.py | Detached D&D character-sheet projection | Extend only when corresponding persisted data and deterministic projections exist. |
| character_applier.py | Applies validated CharacterOperation values | Keep it a thin adapter; do not allow model output to bypass operation validation. |

### services/combat

| Module | Responsibility | Next improvement / guard |
|---|---|---|
| combat_attack_service.py | Atomic attack use case, validation, profile selection orchestration, result persistence and HP synchronization | Attack-profile resolution is already isolated in `AttackProfileResolver`; add future action families only through typed profiles and pure rules helpers. |
| combat_encounter_service.py | Encounter lifecycle, initiative, turn advancement, death saves, movement and reactions; one `IMMEDIATE` transaction per mutation | Preserve the tested rollback contract: canonical HP, timed effects and encounter projections must roll back together. Add new mutations to the failure-injection matrix. |
| weapon_equipment_service.py | Equipment queries/mutations and derived armor/attack profiles | Preserve one source of weapon/equipment truth and document unsupported weapon properties. |
| rules_engine/dnd5e_2014/combat/attack.py | Deterministic attack roll and damage result | Keep independent of services and persistence. |
| rules_engine/dnd5e_2014/combat/damage.py | Damage types, resistance/vulnerability and HP clamping | Keep modifier order explicit and tested. |
| rules_engine/dnd5e_2014/combat/hit_points.py | HP/death-track transitions after damage | New pure rules boundary; no models, repositories or application imports. |
| rules_engine/dnd5e_2014/combat/death_saves.py | Death-save rolls and track progression | Share death-track invariants with hit-point transitions through tests, not service imports. |
| rules_engine/dnd5e_2014/combat/conditions.py | ConditionSet and attack-advantage rules | Keep derived condition lookup in campaign services; this module applies rule semantics only. |
| rules_engine/dnd5e_2014/combat/movement.py | Grid distance, movement and opportunity-attack triggers | Add rules only with explicit 2014 rules references and deterministic tests. |

### services/context

| Module | Responsibility | Next improvement / guard |
|---|---|---|
| memory_search_service.py | Deterministic retrieval/export from supplied WorldState | Remain persistence-free; do not make this a second canonical world store. |
| context_builder.py | Public orchestration façade for context construction | Keep narrative rendering and bounded proposal-context selection explicit. |
| context_expander.py | One-hop relationship/dependency expansion | Preserve deterministic and bounded expansion. |
| context_ranker.py | Stable relevance scoring and ordering | Avoid nondeterministic score sources; maintain ranking regression tests. |
| context_renderer.py | Narrative context and recent-history rendering | Keep character budgets and transport rendering separate. |
| proposal_context_selector.py | Intent-specific context projection and dependency-aware bundle selection | Preserve mandatory facts and fail closed if mandatory context exceeds budget; collect large-campaign probes. |

### services/llm_world

| Module | Responsibility | Next improvement / guard |
|---|---|---|
| llm_world_extractor.py | Single structured player-intent proposal workflow | Keep proposals bounded and fail closed on invalid or unsupported output. |
| llm_world_context_renderer.py | Dynamic campaign/context rendering | Keep it distinct from static prompt instructions and the proposal context selector. |
| llm_world_proposal_prompt_builder.py | Single player-intent structured proposal prompt | Keep bounded, typed and driven by the registry allowlist. |
| llm_world_proposal_validator.py | Structured response validation and one compact repair | Keep one repair only, bounded input/output and fail-closed behavior. |
| llm_world_response_parser.py | Strict response decoding and trust gate | Reject unsupported/internal-only operations before domain object construction. |
| operation_registry.py | Typed operation catalog, schema, examples and model-proposable classification | The registry is not authorization; domain permission/existence checks remain outside this package. |
| operation_parser.py | Structural parser for typed operations | No repository, mutation or domain-permission behavior. |

### services/providers

| Module | Responsibility | Next improvement / guard |
|---|---|---|
| llm_provider.py | Minimal provider port and normalized provider error | Keep the port small; add capabilities only when an actual provider requires them. |
| ollama_provider.py | Ollama HTTP adapter | Keep timeout/transport error translation deterministic and testable. |
| llm_settings.py | Role-specific models, URLs, limits and timeout validation | Keep settings validated at composition time; no hidden retries. |
| fake_llm_provider.py | Deterministic provider double | Keep production and tests on the same narrow provider contract. |

### services/turns

| Module | Responsibility | Next improvement / guard |
|---|---|---|
| dm_service.py | Narrative generation, separate from consequences | Apply active-character event visibility; label rumors/inferences and superseded history; narrate only authorized context. |
| mechanics_adjudicator.py | Structured mechanics proposal and validation | It does not roll dice or mutate world state. |
| turn_resolution_service.py | Structured player-intent proposal, mechanics orchestration, application and non-durable narration wrapper | Preserve proposal/apply/narrate ordering; durable orchestration owns commit-before-narration. |
| durable_native_turn_service.py | Stable public lifecycle façade and collaborator composition | Keep transport and lifecycle routing outside this service; preserve its public contract while new use cases are extracted behind it. |
| durable_turn_execution_service.py | Request identity/idempotency, planning leases, proposal preparation and pre-commit recovery | Preserve exact request fingerprint semantics, campaign scope, lease fencing and the one prepared-commit hand-off. |
| durable_turn_errors.py | Stable typed codes for durable lifecycle failures | Lifecycle transitions and API mapping must use codes/types, never exception-message matching. |
| durable_turn_challenge_state_service.py | Read-only challenge state projection | Keep detached and campaign-scoped. |
| durable_turn_clarification_submission_service.py | Clarification submission and recovery | Keep revision/lease fencing and retry behavior. |
| durable_turn_manual_roll_submission_service.py | Manual roll submission and recovery | Preserve deterministic dice ownership and exactly-once consequence application. |
| durable_turn_prepared_commit_service.py | Atomic prepared-resolution commit boundary | Do not include provider calls or narration inside the write transaction. |
| durable_turn_preparation_mapper.py | Internal preparation to public response mapping | Keep it an adapter, not a rules authority. |
| durable_turn_result_mapper.py | Durable record to public result mapping | Keep serialization stable and side-effect free. |
| durable_turn_narration_service.py | Native/external narration completion | Never replay operations after commit; narrator evidence includes only successful operations that actually changed state. |
| turn_resolution_codec.py | Canonical JSON codec for durable records | Keep schema/codec compatibility explicit and tested. |
| turn_execution_lock.py | Process-local shared lock | Single-process limitation must remain documented until distributed coordination is a real requirement. |

### services/world

| Module | Responsibility | Next improvement / guard |
|---|---|---|
| world_service.py | Campaign-scoped state façade and applier publication | Mixed world/character turn dispatch is delegated to `WorldTurnOperationCoordinator`; preserve operation order, shared state identity and caller-owned transactions. |
| world_query_service.py | Filtered/paginated entity read model | Keep reads detached, stable and campaign-scoped. |
| world_collection_query_service.py | Item/resource/relation/event read projections | Apply trusted active-character visibility before filtering/pagination; expose provenance/currentness but not internal known-by character IDs. |
| world_applier.py | Typed operation dispatch | Keep dispatch deterministic and fail closed. |
| world_entity_applier.py | Entity operation family | Keep operation-specific validation and repository writes together. |
| world_item_applier.py | Item/instance/transfer operation family | Keep inventory ownership and location invariants atomic. |
| world_relation_applier.py | Relation operation family | Preserve both endpoints and campaign isolation. |
| world_resource_applier.py | Resource and balance operation family | Preserve non-negative balances and transfer atomicity. |
| world_serializer.py | Domain dataclass serialization | Treat output as a contract; inspect every consumer before changing it. |
| world_state_port.py | Minimal world state protocol | Keep the port small and implementation-free. |

## Shared layers and notable hotspots

| Area | Current shape | Disposition |
|---|---|---|
| migrations.py | Ordered historical migrations 001–032 and a contiguous `MIGRATIONS` metadata/runner registry | Historical functions stay chronological; use [the migration catalogue](migration-catalog-2026-11-12.md), preserve idempotency and old-data upgrade tests. |
| models/schemas.py | Compatibility facade; bounded-context modules own campaign, character, world, turn and integration request DTOs | Production routers import the owning module; retain facade exports and verify OpenAPI stability. |
| models/combat_api_schemas.py | Combat-specific API contracts | Keep combat schemas isolated from unrelated API requests. |
| models/turn_context.py and models/world_context_projection.py | Shared application input and detached context projection | Keep the projection typed and detached from mutable runtime state. |
| repositories/turn_repository.py | Turn/transcript persistence | Preserve campaign scope and connection/transaction ownership. |
| repositories/turn_resolution_repository.py | Durable in-flight state persistence | Preserve lease fencing, uniqueness and atomic transitions. |
| repositories/world_repository.py | Canonical world persistence | Preserve one canonical state source and caller-owned transaction behavior. |
| bootstrap/campaign_runtime.py | Per-campaign composition root and runtime cache | Shutdown and selective invalidation are implemented/tested; defer cache eviction until measured pressure and an in-flight request policy justify it. |
| app.py | FastAPI app and middleware wiring | Keep thin; no business use cases belong here. |
| api/routers | Transport-facing endpoint groups | Keep each route handler focused on validation, service call and response mapping. |

## Retired paths and preserved history

The narrative-first `POST /integration/turn`, `LegacySillyTavernTurnService`,
`LLMWorldExtractor.extract()`, legacy prompt builder/modules,
`WorldSnapshotRepository`, `TurnRecord.snapshot` and runtime
`turns.snapshot` column are retired. Do not recreate them as compatibility
shims or parallel processing paths.

Migration 029 preserves historical non-null snapshot JSON in the inert
`turn_snapshot_archive` table. The archive is retained for data preservation,
not runtime restoration. All supported integrations use the durable
resolve/complete lifecycle.

## Priority backlog

The structural backlog for the supported local single-player, single-process
scope is closed. Do not schedule broad service decomposition or infrastructure
work without a demonstrated defect or new product requirement.

| Priority | Area | Current next step | Why |
|---|---|---|---|
| P1 | Live acceptance | Run and record the Ollama + SillyTavern smoke test | Deterministic CI cannot prove local model quality or extension lifecycle behavior. |
| P2 | Context / LLM | Add representative medium/large campaign probes for ranking, dependency bundles, mandatory facts, budget exhaustion and non-mutation | Validate scale and proposal quality before adding retrieval infrastructure. |
| P2 | Critical branches | Continue targeted stale-revision, rollback, lease-fencing/recovery and effect-expiry tests when a missing path is identified | Coverage is diagnostic; do not impose an arbitrary global threshold. |
| P3 | Characters | Build typed character creation and progression | Current state/sheet/Hit Dice/rest slice is a foundation, not a complete character builder. |
| P3 | Equipment and combat | Add class/resource-aware equipment and combat mechanics for one selected playable slice | Avoid generic counters or speculative rules that do not share a typed source of truth. |
| P3 | Adventure loop | Deliver one complete first adventure with clues, NPC continuity, rewards and persistence | The priority is an end-to-end playable experience. |

Completed structural milestones: PRs #198–#203. Character/combat state
consistency and Hit Dice/rest slice: PR #204. Test-suite contract organization:
PR #205. See the [engineering readiness and gameplay roadmap](engineering-readiness-and-gameplay-roadmap-2026-11-12.md)
for indicative module-readiness estimates and hour ranges.

## AI world-understanding roadmap

The PR #211 branch introduces `services/context/entity_reference_resolver.py` as the deterministic identity-matching collaborator used by memory retrieval and proposal projection diagnostics. See the [entity reference-resolution contract](../quality/entity-reference-resolution-2026-11-12.md).

The AI-quality phase is tracked in the [AI world-understanding roadmap](../quality/ai-world-understanding-roadmap-2026-11-12.md). PRs #210–#213 strengthen the evidence, references, retrieval and player-intent contract. PR #214 consolidates event provenance, active-character visibility, temporal supersession and committed-only narration grounding across the read/turn boundary. This does not justify a vector database, another extraction pipeline or a monolithic prompt.

## Current proposal assessment

The only world-consequence proposal flow uses player intent and confirmed
mechanics. The turn/application boundary selects a bounded
`WorldContextProjection`; `LLMWorldProposalPromptBuilder` renders it;
the response parser enforces the model-proposable allowlist; the world
application boundary performs semantic validation and mutation. Prompt,
selected context, response and one repair have independent budgets.

There is no narrative-first extraction API or static legacy prompt builder.
Narrative generation is a presentation phase after durable consequences are
committed.

## Validation boundaries

The PR #205 head passed deterministic Python tests (1,406 passed, 4 deselected as real_llm), JavaScript tests, Ruff, both Pyright scopes and both CodeQL language checks. Live Ollama requests and manual SillyTavern sessions remain separate, opt-in acceptance checks and are not recorded as passed. A green CI run does not claim those live checks passed.
