# Shared-layer module catalogue — 2026-11-12

**Verified against:** `main` at `eb57316d9b060bb3a09b0b6b08c7282e07fce192` plus the in-flight architecture branch for the new hit-point rules module.  
**Navigation rule:** the global [architecture map](architecture-map-2026-11-12.md) describes capability packages and end-to-end flows. This catalogue covers the shared layers, public transport surfaces, persistence and validation hotspots. It is intentionally a navigation and improvement register, not a proposal to split every file.

## Read this before changing shared layers

- Read the package or module contract before changing a public DTO, repository method, operation or rules-engine function.
- Preserve campaign scope and caller-owned SQLite connections. A helper must not quietly open a second connection inside a caller's transaction.
- Keep the rules engine pure: primitive/value contracts in, deterministic rules results out.
- Keep model-facing schemas, domain state and API presentation types conceptually separate even where some currently share a module.
- Treat migrations as ordered history. Do not rename, reorder or relocate a migration function without a deliberate registry and replay strategy.
- Add a cross-layer dependency only after updating the dependency matrix and architecture-boundary tests.
- Where this catalogue marks a concern for review, it does not imply a confirmed defect. Verify it with tests and call sites before changing behavior.

## Application entrypoints and composition

| Path | Current responsibility | Improvement / guard |
|---|---|---|
| `app.py` | Creates the FastAPI application, middleware and router registrations. | Keep it as transport composition only. Route registration should remain discoverable; do not move use-case construction here. |
| `bootstrap/__init__.py` | Public package surface for runtime composition. | Export only stable composition contracts. |
| `bootstrap/campaign_runtime.py` | `CampaignRuntimeFactory`, request runtime graph, per-campaign cache and dependency wiring. | Preserve the single composition root. Next review: lifecycle invalidation, shutdown and cache eviction only if deployment requirements justify them. Keep provider, context and integration dependencies visible in this file. |
| `database.py` | SQLite connection helpers, transaction boundaries and database initialization. | Keep connection and transaction ownership explicit. Review nested transaction behavior and shared-connection assumptions before adding repository conveniences. |
| `migrations.py` | Ordered schema/data migrations 001–029. | This is historical, data-sensitive code. Add a migration index and replay fixture before any file split; preserve idempotency, foreign keys and historical data. |
| `start.bat` | Local Windows startup entrypoint. | Keep aligned with the documented install/run path; avoid embedding configuration defaults that differ from application settings. |
| `scripts/bootstrap_demo.py` | Creates deterministic demo campaign/world content. | Keep demo data reproducible and safe to run against an explicitly selected database. Add assertions for idempotency/reset semantics before changing it. |
| `scripts/ci/coverage_summary.py` | Converts coverage XML into package-level CI summary data. | Keep report-only policy separate from test execution. Validate missing/empty coverage inputs and keep package aggregation deterministic. |

## HTTP API and transport adapters

Routers should stay thin: validate request DTOs, obtain the request-bound runtime, call one application service, and map results/errors. A router is not a second composition root.

| Path | Current responsibility | Improvement / guard |
|---|---|---|
| `api/__init__.py` | API package marker. | No runtime behavior belongs here. |
| `api/errors.py` | Application exception to HTTP error contract and FastAPI error-handler registration. | Keep stable machine-readable error codes. Replace message-based classification only with explicit typed service errors; avoid leaking internal exception text. |
| `api/runtime_context.py` | ContextVar binding and `get_current_runtime()` access to the request-scoped campaign runtime. | Preserve token restoration on exceptions and nested bindings. Do not expose the ContextVar itself to routers. |
| `api/serializers.py` | Shared operation-result serialization. | Keep it transport-only and test public JSON shape before changing enum/status handling. |
| `api/routers/campaign.py` | Campaign create/update, session lifecycle, campaign-state and active-character endpoints. | Review campaign/session scoping and page contracts. Keep campaign state assembly in campaign services. |
| `api/routers/character.py` | Character creation/bootstrap, sheet, inventory and equipment endpoints. | Keep equipment/character projections in their owning services. Do not duplicate inventory ownership logic in HTTP handlers. |
| `api/routers/clock.py` | Campaign clock read/advance endpoints. | Keep fictional campaign time independent of server wall-clock time; validate advancement at the service boundary too. |
| `api/routers/combat.py` | Encounter lifecycle, attacks, death saves, movement, reactions and opportunity-attack endpoints. | Keep request schemas specific to combat. Avoid allowing route parameters to override persisted turn/position state; preserve expected-round/turn checks. |
| `api/routers/dice.py` | Standalone dice-tray endpoint, independent of turn resolution. | Keep this endpoint separate from authoritative mechanics adjudication and durable-turn state. |
| `api/routers/effects.py` | Persistent-effect query/create/status/remove endpoints. | Keep entity/campaign ownership checks in application services and repositories, not only in route validation. |
| `api/routers/integration.py` | SillyTavern context, external turn state, resolve/complete and clarification/manual-roll routes. | Keep the router thin; all state changes use the durable turn lifecycle. The narrative-first mutation route has been removed. |
| `api/routers/memory.py` | Memory search and context endpoints. | Ensure returned information follows player/GM visibility policy; do not let generic search bypass secret-event filtering. |
| `api/routers/system.py` | Root, liveness and readiness endpoints. | Keep liveness cheap; readiness should check only dependencies required to serve traffic and must not mutate state. |
| `api/routers/turns.py` | Native turn play, manual-roll/clarification continuation and transcript reads. | Keep durable-turn orchestration in `services/turns`; keep serialization helpers pure and test their public payloads. |
| `api/routers/world.py` | World overview, entity query/bootstrap and memory export. | Preserve campaign scoping, pagination and export visibility rules. |
| `api/routers/world_collections.py` | Paginated item, instance, resource, balance, relation and event endpoints. | Keep display-name joins in read services. Apply explicit secret-event/GM policy before any player-facing exposure. |

### API boundary review checklist

1. No router imports a concrete repository, provider or another router.
2. The selected campaign runtime comes only from `api.runtime_context`.
3. Input validation is strict at the transport edge, but business invariants are still enforced by services/domain types.
4. Error responses remain stable and do not serialize arbitrary exception messages.
5. Paginated collection endpoints validate limits/offsets and remain campaign-scoped.
6. Deprecation flags and structured warnings stay covered by tests.

## Models and shared contracts

The `models/` directory currently includes domain state, immutable read projections, mechanics results, durable turn records and Pydantic transport schemas. Avoid treating the folder name as proof that all these objects have the same architectural role.

| Path(s) | Current responsibility | Improvement / guard |
|---|---|---|
| `models/campaign_scope.py` | Immutable campaign identity/scope boundary. | Keep this small and dependency-free; require it at repository boundaries where it prevents accidental cross-campaign access. |
| `models/campaign_state.py`, `models/session_state.py` | Campaign/session state used to assemble turn context. | Keep persisted/canonical state distinct from derived context projections. |
| `models/campaign_clock.py` | Fictional campaign-time value object. | Preserve determinism and avoid implicit reads from system time. |
| `models/character_state.py` | Canonical mechanical state for player characters. | Keep HP and mechanical proficiency state canonical here; coordinate equipment-derived values through rules projections rather than duplicating them. |
| `models/character_sheet_read_models.py` | Typed character-sheet response projection. | Keep detached and player-safe; extend only when backing data and rules projections exist. |
| `models/combat_encounter_state.py` | Encounter state, status and turn/round progression. | Treat combatants as encounter snapshots; verify canonical HP and expected turn position before mutation. |
| `models/combatant_state.py` | Combatant snapshot with tactical position, action/reaction and death-save track. | Preserve invariants in `__post_init__`; keep this a value/state type rather than adding repository behavior. |
| `models/creature_state.py` | Canonical persisted mechanical state for NPC creatures. | Keep metadata validation close to a typed NPC profile; do not make untrusted metadata an implicit rules authority. |
| `models/entity.py`, `models/relation.py`, `models/event.py` | Core world entity, relation and event records. | Preserve IDs, campaign ownership and the distinction between secret/internal and player-visible records. |
| `models/item.py` | Item definitions and item-instance state. | Keep definition and physical instance separate; preserve owner/location and transfer invariants. |
| `models/resource.py` | Resource definitions and balance data. | Keep non-negative balance and atomic transfer invariants at mutation boundaries. |
| `models/persistent_effect.py` | Persistent effect lifecycle, source, duration and status. | Avoid duplicating the derived condition set; expiry and status transitions should have one authoritative owner. |
| `models/mechanics.py` | Typed mechanics decision and result contracts. | Keep model-proposed decisions separate from dice results and applied consequences. |
| `models/operation_result.py` | Typed status/result returned by operation application. | Keep it a result contract, not a second validation or authorization mechanism. |
| `models/turn_context.py` | Detached turn input: campaign, session, active character, world and related projections. | Avoid growing it into an unbounded service locator. Add new context fields only with explicit provenance and freshness. |
| `models/turn_record.py` | Persisted transcript/narrative turn record and version/status fields. | Keep transcript version separate from durable resolution state; preserve historical records during regeneration. |
| `models/turn_resolution_record.py` | Durable in-flight turn-resolution state, leases and transition metadata. | Preserve fencing, idempotency and legal state transitions; update codec/repository tests with any schema change. |
| `models/turn_resolution_result.py` | Typed resolution plan/result and public mapping data. | Keep internal proposals, committed operations and narration distinct. |
| `models/world_state.py` | In-memory aggregate of campaign world records. | Preserve a single canonical mutable state per runtime; read projections should be deep-copied/detached. |
| `models/world_context_projection.py` | Typed, detached and budget-diagnostic LLM context projection; shared token upper-bound helper. | Keep the dependency direction: context selects; LLM-world renders. Preserve mandatory facts and fail-closed budget behavior. |
| `models/world_operations_in.py` | Typed incoming world-operation request container. | Keep transport parsing separate from the canonical internal operation dataclasses. |
| `models/world_application_result.py` | Aggregate result of applying operations. | Keep deterministic ordering and failure details stable for service/API callers. |
| `models/world_read_models.py`, `models/world_collection_read_models.py` | Detached entity and collection query DTOs. | Keep pagination metadata stable and display names additive; enforce event visibility before player exposure. |
| `models/session_read_models.py` | Session list/detail read projection. | Avoid embedding internal session notes unless an explicit GM authorization contract exists. |
| `models/schemas.py` | Broad Pydantic request schemas for campaign, character, world, turn, integration and other API domains. | Main schema-navigation hotspot. Split by bounded context only with a stable import migration plan; avoid circular imports and preserve OpenAPI contracts. |
| `models/combat_api_schemas.py` | Combat-specific request schemas and strict tactical/attack validation. | Keep separate from general schemas; cross-check duplicated constraints between API schemas and service/domain boundaries. |
| `models/persistent_effect_api_schemas.py` | Persistent-effect API request contracts. | Keep transport validation distinct from effect domain lifecycle invariants. |
| `models/campaign_clock_api_schemas.py` | Campaign-clock request/response DTOs. | Keep fictional time fields explicit and validated. |
| `models/equipment_api_schemas.py` | Equipment endpoint input contracts. | Keep slot/ownership constraints aligned with equipment service behavior. |

### Model organization target

A future schema reorganization should distinguish at least:
- domain state/value objects (campaign, character, world, combat, turn);
- application projections/read DTOs;
- HTTP/Pydantic input and output contracts;
- LLM-only typed projections.

Do not move everything at once. Start with the most stable, cohesive API schema groups and preserve transport imports until all routers/tests are migrated. Do not add compatibility re-exports by default; document the chosen canonical import path and delete old paths after the consumer search.

## Typed operations

| Path | Current responsibility | Improvement / guard |
|---|---|---|
| `operations/world_operations.py` | Typed command dataclasses for entity, item/instance, resource, relation and event operations. | Keep this as the canonical operation vocabulary. Add new commands only with world applier, parser registry, semantic validation and persistence tests. |
| `operations/character_operations.py` | Typed character-state mutation commands. | Keep deterministic character mechanics outside model-proposable operations unless an explicit trusted application flow is defined. |
| `operations/operation_reference.py` | Typed reference to earlier operation output/IDs. | Preserve reference resolution order and reject unknown or mismatched reference types. |
| `operations/referenced_operation.py` | Couples a typed operation with its references. | Keep ID resolution deterministic and fail closed if a reference is absent or ambiguous. |
| `operations/turn_operations.py` | Shared type aliases for operations accepted in turn plans. | Keep aliases accurate when a new operation family is introduced. |

Operation metadata is centralized under `services/llm_world/operation_registry.py`; this catalogue is descriptive, not a second registry. The registry's model-proposable flag is a trust gate, not domain authorization. Existence, campaign scope, permission and mutation checks remain in the application/world boundary.

## Persistence repositories

Repositories own SQL and hydration. They must not call providers or orchestrate turns. Preserve campaign scope and allow caller-owned connections wherever workflows need atomic multi-repository updates.

| Path | Current responsibility | Improvement / guard |
|---|---|---|
| `repositories/campaign_repository.py` | Campaign/session persistence and campaign state access. | Review query scopes and connection passing; do not move runtime cache ownership here. |
| `repositories/campaign_clock_repository.py` | Campaign fictional-clock persistence. | Keep clock state campaign-scoped and deterministic. |
| `repositories/campaign_state_version_repository.py` | Reads the monotonic revision maintained by SQLite triggers. | Keep revision reads on the same transaction/connection when fencing a prepared turn. |
| `repositories/character_repository.py` | Character-state persistence and row hydration. | Preserve expected-HP compare-and-set updates and caller-provided connection behavior. |
| `repositories/entity_repository.py` | World entity persistence and retrieval. | Preserve campaign filtering and stable entity identity. |
| `repositories/creature_repository.py` | NPC creature mechanics persistence. | Treat metadata as untrusted persisted configuration; validate it before rule execution. |
| `repositories/combat_encounter_repository.py` | Campaign-scoped encounter and combatant snapshot persistence. | Preserve turn-position concurrency checks and transaction participation. |
| `repositories/weapon_equipment_repository.py` | Equipment projection backed by owned item instances. | Keep equipment derived from canonical inventory; do not introduce a second equipment data store. |
| `repositories/persistent_effect_repository.py` | Persistent effect rows, lifecycle status and expiry queries. | Keep effect ownership campaign-scoped; test simultaneous expiry/update operations and transaction rollback. |
| `repositories/turn_repository.py` | Transcript turns, versioning, external turn identity and status persistence. | Preserve idempotency, ordering, campaign isolation, supersession and external ID uniqueness. |
| `repositories/turn_resolution_repository.py` | Durable in-flight resolution, lease acquisition/fencing and transitions. | Critical consistency boundary. Never weaken compare-and-set state transitions or stale-worker fencing. |
| `repositories/world_repository.py` | Canonical world state load/save and collection persistence. | Critical transaction boundary. Preserve atomic multi-collection writes, connection ownership and campaign isolation. |
| `turn_snapshot_archive` (migration 029) | Inert archive of pre-retirement snapshot JSON. | Preserve historical payloads; do not introduce a runtime restore/read path. |

### Repository review checklist

- Every query that touches campaign-owned data includes a campaign scope/ID.
- Multi-repository use cases pass the same active SQLite connection through every participating repository.
- No repository starts an independent transaction when a caller owns one.
- Expected-state updates use guarded writes where concurrent requests can race.
- Row hydration validates/normalizes data at the persistence boundary.
- Rollback tests assert both database state and in-memory state remain consistent.

## Deterministic rules engine

The rules engine owns deterministic D&D 5e (2014) rules and data. Its modules should remain independent of models/repositories/services/API. A rules function should accept typed/primitive rule inputs and return deterministic values/results.

| Path | Current responsibility | Improvement / guard |
|---|---|---|
| `rules_engine/dnd5e_2014/core/abilities.py` | Ability identifiers and ability-score modifier. | Keep score ranges and rounding behavior explicit; no application state. |
| `rules_engine/dnd5e_2014/core/skills.py` | Skill identifiers and governing abilities. | Keep the ruleset mapping canonical and exhaustive. |
| `rules_engine/dnd5e_2014/core/proficiency.py` | Proficiency bonus progression/calculation. | Add level-boundary tests for every supported progression. |
| `rules_engine/dnd5e_2014/core/dice.py` | Dice roller, d20 result and manual/advantage roll primitives. | Keep randomness injectable and deterministic in tests; no hidden application retries. |
| `rules_engine/dnd5e_2014/character.py` | Protocol for character fields required by rules calculations. | Keep this as a narrow rules input protocol, not a dependency on CharacterState. |
| `rules_engine/dnd5e_2014/checks.py` | Generic ability-check and saving-throw resolution. | Keep deterministic modifier composition and d20 mode semantics independently tested. |
| `rules_engine/dnd5e_2014/character_checks.py` | Character-aware check modifiers, proficiency and saves. | Preserve separation between trusted character statistics and untrusted mechanics proposals. |
| `rules_engine/dnd5e_2014/armor/catalog.py` | Immutable armor/shield catalogue. | Keep SRD/rules data separate from owned inventory and persisted item instances. |
| `rules_engine/dnd5e_2014/armor/armor_class.py` | AC and armor-proficiency derivation. | Add explicit tests for stacking, shield, unarmored defense and proficiency penalties before extending rules. |
| `rules_engine/dnd5e_2014/weapons/catalog.py` | Immutable SRD weapon definitions and properties. | Keep catalog keys stable because item metadata may reference them; document unsupported special/loading/ammunition behaviors. |
| `rules_engine/dnd5e_2014/weapons/attack_profile.py` | Derives attack ability, proficiency, bonus and damage dice from trusted character/weapon inputs. | This is the rules-facing profile derivation. Application-side NPC metadata selection still needs extraction from CombatAttackService. |
| `rules_engine/dnd5e_2014/combat/attack.py` | Attack roll, natural 1/20, critical and damage-roll resolution. | Keep it pure and validate dice/manual-roll edge cases independently. |
| `rules_engine/dnd5e_2014/combat/conditions.py` | Condition set and attack advantage/disadvantage calculation. | Keep conditions typed; avoid applying persistent-effect lifecycle or repository concerns here. |
| `rules_engine/dnd5e_2014/combat/condition_effects.py` | Derived restrictions such as auto-failed saves and check disadvantages. | Ensure every condition with a mechanical impact is represented in tests; avoid duplicate mappings in services. |
| `rules_engine/dnd5e_2014/combat/damage.py` | Damage types, resistance/vulnerability and HP clamping. | Preserve immunity > cancellation > resistance/vulnerability ordering and rounding. |
| `rules_engine/dnd5e_2014/combat/hit_points.py` | HP/death-track transition after damage (added in PR #196). | Keep the transition pure; validate terminal-state invariants and critical/downed/massive-damage cases. |
| `rules_engine/dnd5e_2014/combat/death_saves.py` | Death-save roll and success/failure track. | Keep roll resolution separate from damage-caused failures; coordinate state invariants through shared tests. |
| `rules_engine/dnd5e_2014/combat/initiative.py` | Initiative rolls and deterministic tie grouping. | Keep tie ordering stable and specify which source controls equal initiative ordering. |
| `rules_engine/dnd5e_2014/combat/movement.py` | Grid distance, path movement, speed modifiers and opportunity triggers. | Add explicit rule citations/tests for diagonal movement, reach, voluntary movement, disengage and incapacitation. |

### Rules-engine boundary test

The existing architecture tests prevent inward dependencies on API/services/repositories. Extend this test only when an actual new rule module is added; do not whitelist service imports into the engine to avoid moving deterministic logic to the right layer.

## Tests and executable contracts

Tests are grouped by capability and boundary in `tests/`. Keep deterministic CI independent of Ollama and network services. The live provider suite remains separately marked `real_llm`.

| Test area | Contract to preserve | Navigation / next improvement |
|---|---|---|
| `tests/rules_engine/` | Ability/checks, armor, attack, conditions, damage, initiative, death saves and dice rules. | Keep each module narrowly aligned with one deterministic rule family; add `test_hit_points.py` for the new damage-state transition. |
| `tests/test_architecture_boundaries.py` | Core-layer and eight capability dependency prohibitions, plus integration adapter direction. | Update in the same PR as every approved cross-package dependency. |
| `tests/test_canonical_service_import_boundaries.py` | Retired flat service import paths remain absent. | Keep denylist explicit; never delete it merely because no legacy paths currently exist. |
| `tests/test_campaign_runtime.py`, `tests/test_app.py` | Runtime composition, middleware binding and app-level behavior. | Keep tests asserting runtime stays out of routers and is restored correctly after request failures. |
| `tests/test_*repository.py` | SQL hydration, campaign isolation, transaction ownership, atomic save/rollback and state concurrency. | Preserve same-connection and rollback coverage when repositories are reorganized. |
| `tests/test_migrations.py` | Historical schema/data upgrades and constraints. | Treat every supported historical migration as a compatibility contract; replay from old DB fixtures before changing migrations. |
| `tests/test_*world*` | World application, appliers, query projections, persistence and serializer behavior. | Split oversized test modules only along observable contracts; retain multi-collection rollback cases. |
| `tests/test_*combat*` | Encounter, attack, conditions, movement, opportunity attacks, equipment and HP projection synchronization. | Add failure-injection tests wherever an attack or encounter update spans canonical HP and encounter snapshots. |
| `tests/test_*turn*` | Turn resolution, durable commit, manual rolls, clarification, idempotency and recovery. | Preserve failure-path/restart/fencing assertions when extracting lifecycle collaborators. |
| `tests/test_context_*`, `tests/test_proposal_context_selector.py` | Retrieval, expansion, stable ranking, secret exclusion, mandatory facts and budget failures. | Add medium/large campaign fixtures and assert deterministic selection, not just token totals. |
| `tests/test_llm_world_proposals.py`, `tests/test_llm_world_proposal_prompt_builder.py`, `tests/test_llm_world_proposal_validator.py` | Single structured player-intent proposal, trust gate and bounded one-repair behavior. | Keep model output untrusted and domain validation independent. |
| `tests/test_llm_world_proposals.py`, `tests/test_llm_world_proposal_prompt_builder.py`, `tests/test_llm_world_proposal_validator.py` | Active structured intent proposal, trust gate and bounded one-repair behavior. | Keep model output untrusted and domain validation independent. |
| `tests/test_silly_tavern_api.py`, `tests/test_silly_tavern_schemas.py` | Active context, resolve/complete, external identity and durable challenge contracts. | Preserve client-visible payload/status semantics and ensure historical transcripts cannot bypass durable resolution. |
| `tests/test_real_llm.py` | Live Ollama/provider quality probes. | Run only as explicit opt-in/manual validation; never pretend deterministic CI covers it. |

Oversized tests are a navigation concern, not automatic evidence of bad architecture. The current test audit identifies the modules and contracts that should be split first; update that inventory after structural changes.

## Dependency and ownership cross-check

Use the existing [capability dependency matrix](package-dependency-matrix.md) as the authority. This catalogue must not silently grant new dependencies.

| Caller | Allowed direction | Forbidden shortcut |
|---|---|---|
| API router | request runtime -> application service -> typed result | Router directly opens repositories or providers. |
| Bootstrap | imports and composes all application packages | Capability package imports bootstrap. |
| Integration adapter | maps external contracts onto application services/models | Adapter imports FastAPI router or constructs runtime composition. |
| Turn orchestration | context selection + mechanics + LLM proposal + world application | LLM package imports context package or mutates world state. |
| LLM boundary | typed projection -> prompt -> provider -> untrusted typed proposal | Prompt allowlist treated as authorization or provider parses domain state. |
| World application | typed operations -> semantic validation -> transaction/repositories | Raw model JSON or parser bypasses domain checks. |
| Repository | scoped SQL using caller-owned connection when supplied | Repository begins unrelated transaction during a multi-aggregate use case. |
| Rules engine | typed inputs -> deterministic result | Rules engine imports models, database, repositories, services or API. |

## Known candidates for future PRs

Ordered by expected architectural value, not ease of implementation:

1. **Combat profile resolution:** extract NPC natural/melee profile parsing and player/equipment selection from `CombatAttackService` into a typed application collaborator. Preserve exact validation errors/contracts and add player/NPC profile tests. Do not move creature metadata or repositories into `rules_engine`.
2. **Durable turn lifecycle:** keep `DurableNativeTurnService` as public façade, extract clarification/manual-roll/external completion orchestration by durable state boundary. Every extraction must preserve idempotency, lease fencing and commit-before-narration.
3. **Combat transaction audit:** map every repository write during create/start/advance/death-save/move/reaction/attack and inject failures to verify encounter snapshots never diverge from canonical character/creature HP or persistent effects.
4. **World application audit:** map `WorldService` dispatch and connection ownership. Existing applier modules already define operation-family candidates; split coordination only after a transaction map exists.
5. **Schema bounded contexts:** split `models/schemas.py` by campaign, character, world, turn and integration DTOs. Keep combat/effects/clock schema modules separate and verify OpenAPI output.
6. **Provider contract coverage:** add a focused provider contract test matrix for success, timeout, unavailable Ollama, malformed JSON and normalized errors; retain fake provider parity.
7. **Campaign runtime lifecycle:** document/test invalidation and shutdown for the current process-local cache before adding any eviction policy.
8. **Migration navigation:** add an index mapping migration number to schema/data transition before changing the 2,298-line migration history.
9. **Visibility policy:** define an explicit GM/player permission model for secret events and hidden world state before expanding non-GM read surfaces.
10. **Structured proposal quality:** run representative large-campaign/live-Ollama probes for the active prompt without coupling deterministic CI to a live provider.
11. **Legacy retirement:** completed in PR #198; historical snapshot JSON is preserved in the inert archive created by migration 029.
