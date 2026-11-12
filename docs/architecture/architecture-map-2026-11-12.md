# Campaign Manager — architecture map for maintainers and coding agents

**Verified baseline:** main at eb57316d9b060bb3a09b0b6b08c7282e07fce192 (2026-11-12, PR #195).  
**Purpose:** provide one fast, source-linked navigation map. This is an index and work register, not a replacement for package documentation or lifecycle contracts.

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
3. services/turns/durable_native_turn_service.py coordinates the durable lifecycle, idempotency, leases and recovery.
4. services/turns/turn_resolution_service.py orchestrates mechanics and player-intent proposal preparation.
5. services/context builds a detached, ranked WorldContextProjection for the intent.
6. services/llm_world builds a bounded proposal prompt, calls the injected provider and validates model output.
7. services/world applies typed operations using repositories inside the caller-owned transaction.
8. DurableNativeTurnService persists the result before narration; narration/retries must never replay committed consequences.

Critical contracts: turn-resolution lifecycle, durable persistence, idempotency keys, revision fencing, lease fencing, short write transactions, recovery after provider/narration failure.

### SillyTavern

- integrations/adapters/silly_tavern/context_adapter.py translates active read/context and external transcript-state contracts.
- integrations/adapters/silly_tavern/service.py is a thin façade with an injected legacy processor.
- services/turns/legacy_silly_tavern_turn_service.py owns the deprecated narrative-first mutation and snapshot-regeneration path.
- bootstrap/campaign_runtime.py creates the context adapter and legacy processor separately and injects both into the façade.
- POST /integration/turn remains deprecated but operational. Its usage has not been proven to be zero.
- WorldSnapshotRepository serializes state into JSON stored in the nullable turns.snapshot column; these are not dedicated snapshot tables.

Do not delete the old route, legacy processor, snapshot repository or snapshot column until deployed usage and supported-client migration gates are evidenced.

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
| campaign_state_service.py | Campaign/session state and turn-context assembly | Keep world mutation behind the world state port; add explicit invalidation on campaign lifecycle changes. |
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
| combat_attack_service.py | Atomic attack use case, validation, profile selection orchestration, result persistence and HP synchronization | Continue extracting attack-profile resolution and transaction-boundary collaborators. Do not duplicate D&D rules here. |
| combat_encounter_service.py | Encounter lifecycle, initiative, turn advancement, death saves, movement and reactions | Split only along independently testable use cases; keep encounter/character/creature/effect updates atomic. |
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
| context_builder.py | Public orchestration façade for context construction | Keep narrative budgets and proposal token budgets distinct. |
| context_expander.py | One-hop relationship/dependency expansion | Preserve deterministic and bounded expansion. |
| context_ranker.py | Stable relevance scoring and ordering | Avoid nondeterministic score sources; maintain ranking regression tests. |
| context_renderer.py | Narrative context and recent-history rendering | Keep character budgets and transport rendering separate. |
| proposal_context_selector.py | Intent-specific context projection and dependency-aware bundle selection | Preserve mandatory facts and fail closed if mandatory context exceeds budget; collect large-campaign probes. |

### services/llm_world

| Module | Responsibility | Next improvement / guard |
|---|---|---|
| llm_world_extractor.py | Coordinates legacy extract() and active propose() APIs | Retain extract() only for verified compatibility consumers; keep output untrusted. |
| llm_world_prompt_builder.py | Stable façade for legacy narrative-extraction prompt | Static instructions are decomposed; do not confuse source split with a smaller prompt. |
| legacy_prompt_sections/ | Ordered static instruction modules | Preserve byte-for-byte composition until a separate quality-measured prompt revision. |
| llm_world_context_renderer.py | Dynamic campaign/context rendering | Keep it distinct from static prompt instructions and the proposal context selector. |
| llm_world_proposal_prompt_builder.py | Active player-intent structured proposal prompt | Keep bounded, typed and independent of the legacy extraction prompt. |
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
| dm_service.py | Narrative generation, separate from consequences | Keep provider calls outside write transactions and narrate committed evidence. |
| mechanics_adjudicator.py | Structured mechanics proposal and validation | It does not roll dice or mutate world state. |
| turn_resolution_service.py | Non-persistent planning, mechanics orchestration and plan application | Continue reducing orchestration complexity; retain legacy branch only while supported consumers exist. |
| durable_native_turn_service.py | Public durable coordinator, lifecycle façade, continuation and recovery | Next major decomposition candidate: split public lifecycle use cases while preserving this façade and all lease/idempotency invariants. |
| durable_turn_challenge_state_service.py | Read-only challenge state projection | Keep detached and campaign-scoped. |
| durable_turn_clarification_submission_service.py | Clarification submission and recovery | Keep revision/lease fencing and retry behavior. |
| durable_turn_manual_roll_submission_service.py | Manual roll submission and recovery | Preserve deterministic dice ownership and exactly-once consequence application. |
| durable_turn_prepared_commit_service.py | Atomic prepared-resolution commit boundary | Do not include provider calls or narration inside the write transaction. |
| durable_turn_preparation_mapper.py | Internal preparation to public response mapping | Keep it an adapter, not a rules authority. |
| durable_turn_result_mapper.py | Durable record to public result mapping | Keep serialization stable and side-effect free. |
| durable_turn_narration_service.py | Native/external narration completion | Never replay operations after a committed resolution. |
| turn_resolution_codec.py | Canonical JSON codec for durable records | Keep schema/codec compatibility explicit and tested. |
| turn_execution_lock.py | Process-local shared lock | Single-process limitation must remain documented until distributed coordination is a real requirement. |
| legacy_silly_tavern_turn_service.py | Quarantined narrative-first endpoint and snapshot regeneration | Remove with the deprecated route only after external usage/sign-off gates. |

### services/world

| Module | Responsibility | Next improvement / guard |
|---|---|---|
| world_service.py | Campaign-scoped state façade, operation dispatch and transaction coordination | Review atomicity and dispatch decomposition; preserve caller-owned transactions. |
| world_query_service.py | Filtered/paginated entity read model | Keep reads detached, stable and campaign-scoped. |
| world_collection_query_service.py | Item/resource/relation/event read projections | Keep secret-event visibility out of generic serialization; apply explicit policy before player exposure. |
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
| migrations.py | Ordered historical migrations in one 2,298-line module | Do not move historical functions casually. A future split needs an explicit migration import registry and replay tests. |
| models/schemas.py | Broad transport/domain request schema module | Split by API bounded context when schemas have stable owners; retain import compatibility during migration. |
| models/combat_api_schemas.py | Combat-specific API contracts | Keep combat schemas isolated from unrelated API requests. |
| models/turn_context.py and models/world_context_projection.py | Shared application input and detached context projection | Keep the projection typed and detached from mutable runtime state. |
| repositories/turn_repository.py | Turn/transcript persistence | Preserve campaign scope and connection/transaction ownership. |
| repositories/turn_resolution_repository.py | Durable in-flight state persistence | Preserve lease fencing, uniqueness and atomic transitions. |
| repositories/world_repository.py | Canonical world persistence | Preserve one canonical state source and caller-owned transaction behavior. |
| repositories/world_snapshot_repository.py | Legacy JSON snapshot serialization/restoration | Compatibility-only while the deprecated narrative-first route is supported. |
| bootstrap/campaign_runtime.py | Per-campaign composition root and runtime cache | Keep composition here; make cache shutdown/eviction a separately justified change. |
| app.py | FastAPI app and middleware wiring | Keep thin; no business use cases belong here. |
| api/routers | Transport-facing endpoint groups | Keep each route handler focused on validation, service call and response mapping. |

## Protected compatibility and data

Do not remove these based on names or age alone:

- Deprecated POST /integration/turn.
- services/turns/legacy_silly_tavern_turn_service.py.
- integrations/adapters/silly_tavern/service.py active read/context façade.
- repositories/world_snapshot_repository.py and existing JSON payloads.
- Nullable turns.snapshot column and its migration history.
- Legacy extract() and its stable builder façade while the narrative-first consumer branch remains.
- Migration tests and deterministic integration tests for active contracts.

Removal requires code/test/script/external-client consumer searches, production usage evidence where applicable, a data-retention decision and tests in the same implementation PR.

## Priority backlog

| Priority | Area | Concrete next step | Why now |
|---|---|---|---|
| P0 | Quality gate | Keep CI summary, repository-wide Pyright and both CodeQL checks green | Already configured and required by main protection. |
| P1 | Combat | Extract attack profile selection from CombatAttackService | It still parses NPC metadata, creates synthetic character state and chooses weapons/natural attacks inside one large use case. |
| P1 | Turns | Decompose DurableNativeTurnService behind its stable public façade | It still coordinates multiple lifecycle operations in a 778-line module; preserve idempotency, lease fencing and restart semantics. |
| P1 | Combat | Review CombatEncounterService's transaction ownership across encounter, character/creature HP and effects | A partial write would create divergent canonical and encounter projections. |
| P2 | World | Map WorldService dispatch/transaction boundaries and split only along operation families | Keep existing appliers and caller connection behavior authoritative. |
| P2 | Models | Split broad schemas by bounded context | Improves discovery; do not introduce breakage in transport imports. |
| P2 | Tests | Maintain focused tests for each extracted collaborator and split only mixed-responsibility integration files | Test modules are executable contract documentation. |
| P3 | Migrations | Add a migration index before considering file-level extraction | History is ordered and data-preserving; file count is not a reason to refactor. |
| P3 | Runtime | Define lifecycle invalidation/shutdown only when multi-campaign or deployment needs justify it | Current runtime/locks are process-local by design. |

## Current prompt assessment

The active durable proposal flow uses TurnResolutionService -> ContextBuilder -> ProposalContextSelector -> LLMWorldProposalPromptBuilder and has bounded context, full-prompt, response and one-repair budgets. Operation metadata is centralized, and model output remains untrusted.

The legacy narrative-first extract() path still uses the decomposed static instruction modules and a full snapshot rendering. Its 46,851-character source prompt was split into ordered modules by PR #194 without changing rendered output; that change improved maintainability, not model context size. Do not spend more time shortening the active proposal prompt unless real model probes demonstrate a quality issue. If legacy extract() is used externally, its prompt/context budgets and migration plan should be assessed separately.

## Validation boundaries

The latest integrated baseline had successful CI summary, Ruff, deterministic Python tests, both Pyright checks and both CodeQL language checks. Live Ollama requests and manual SillyTavern sessions remain separate, opt-in integration checks. A green CI run does not claim those live checks passed.
