# Change-impact map — 2026-11-12

**Purpose:** show which files, contracts and tests must be reviewed together when changing a cross-cutting behavior. This is a review checklist, not a runtime dependency map. The [capability dependency matrix](package-dependency-matrix.md) remains authoritative for allowed imports.

## Rule: trace behavior in both directions

Before changing a workflow, trace:
1. the inbound caller (HTTP/native/external client);
2. orchestration and validation;
3. canonical state/model;
4. rules or LLM boundary, if applicable;
5. persistence and transaction owner;
6. outbound response/read projection;
7. unit, integration, migration and architecture tests;
8. package README and current architecture document.

A successful unit test for one collaborator does not prove an end-to-end contract survived.

## Change-impact register

| Change | Review together | Required regression focus |
|---|---|---|
| Character creation or activation | `api/routers/character.py`, `models/character_api_schemas.py` (compatibility export: `models.schemas`), `CharacterCreationService`, `CharacterRepository`, `EntityRepository`, campaign active-character state, character sheet/read model | Entity and CharacterState created together; campaign scoping; activation behavior; rollback after partial failure; no leaking metadata in sheet projection. |
| Character HP or other character mechanics | `CharacterService`, `CharacterApplier`, `CharacterRepository`, `WorldService`, `CombatAttackService`, `CombatEncounterService`, character/encounter snapshots | Canonical CharacterState remains authoritative; expected-current-HP guard; shared connection in an existing transaction; effects on downed/dead state; operation application cannot bypass validation. |
| NPC creature creation/profile metadata | creature/world creation operation, `CreatureState`, `CreatureRepository`, world applier, combat schemas, `CombatAttackService` profile selection | Required metadata shape; invalid natural/melee weapon config fails closed; campaign scope; attack profile has valid damage/reach/proficiency; no malformed metadata reaches rules engine. |
| Weapon catalog or attack calculation | `weapons/catalog.py`, `weapons/attack_profile.py`, `combat/attack.py`, `combat/damage.py`, `CombatAttackService`, `WeaponEquipmentService`, `models/combat_api_schemas.py` | Catalog keys remain stable; proficiency/finesse/ranged/versatile rules; critical and manual rolls; unsupported special/ammunition behavior is explicit; deterministic tests use injected dice. |
| Attack profile selection for player/NPC | `AttackProfileResolver`, `ResolvedCombatAttackProfile`, `CharacterRepository`, `CreatureRepository`, `WeaponEquipmentRepository`, `WeaponEquipmentService`, weapon/natural-attack schemas | Preserve player equipment selection, NPC melee/natural selection precedence and legacy single-profile read; malformed persisted data fails closed; weapon/natural numerical bonuses come from pure rules helpers; player-only finesse/versatile options cannot leak into natural attacks. |
| Damage, resistance or HP/death-track rule | `combat/damage.py`, `combat/hit_points.py`, `combat/death_saves.py`, `CombatAttackService`, `CombatEncounterService`, `CombatantState`, canonical character/creature repositories | Immunity/resistance/vulnerability order; HP floor; first drop to zero; massive damage; damage to downed/stable targets; critical failures; death and stable invariants; database snapshot remains in sync. |
| Encounter lifecycle or turn order | `CombatEncounterService`, `CombatEncounterRepository`, `CombatEncounterState`, `CombatantState`, `api/routers/combat.py`, combat schemas | Expected round/turn compare; initiative ties; active combatant changes; start/complete/restart; status transitions; all writes atomic. |
| Combat movement/reaction/opportunity | `combat/movement.py`, `combat/conditions.py`, `CombatEncounterService`, `CombatAttackService`, combat API schemas | Grid path/distance; reach; voluntary/disengage context; reaction availability; stale position; active mover restriction; no action/reaction consumed on failed validation. |
| Equipment/inventory change | `WeaponEquipmentService`, `WeaponEquipmentRepository`, `WorldService`, item/instance operations and appliers, `Item`/ `ItemInstance`, character and combat queries | Item ownership, equipment slot uniqueness, inventory transfer, derived AC/attack profile, campaign scope, and one canonical source of inventory truth. |
| Persistent effect or condition change | `PersistentEffectService`, `EffectiveConditionService`, effect model/repository/schemas, combat services and `ConditionSet` | Effect duration/expiry; active/removed status; condition projection; transaction synchronization with attack/encounter; no second persisted condition state. |
| World operation type added/changed | `operations/world_operations.py`, `operation_registry.py`, `operation_parser.py`, `llm_world_response_parser.py`, relevant `WorldApplier`, `WorldService`, repositories, read models and operation tests | Parser builder, schema/required fields, reference fields, registry trust classification, semantic checks, authorization, persistence, serialization, ID references and rollback. |
| Model-proposable operation or prompt contract | `operation_registry.py`, `llm_world_proposal_prompt_builder.py`, `llm_world_response_parser.py`, proposal validator, world semantic validation | Internal-only operations remain rejected before construction; schema and prompt contract agree; model allowlist is not authorization; one compact repair remains bounded. |
| World serialization or read API | `WorldSerializer`, world query/collection services, `models/world_*_read_models.py`, API routers and frontend consumers | Stable field names/types, pagination, detached copies, canonical IDs, nullable display names, and secret/GM visibility checks. |
| Context retrieval/ranking/expansion | `MemorySearchService`, `ContextExpander`, `ContextRanker`, `ContextBuilder`, selector, world visibility policies | Deterministic stable ordering; relationship and dependency bundles remain complete; no secret events; no hidden state leakage; source freshness and campaign revision assumptions. |
| Active structured player-intent prompt | `TurnResolutionService`, `ContextBuilder.build_proposal_context()`, `ProposalContextSelector`, `WorldContextProjection`, `LLMWorldContextRenderer`, `LLMWorldProposalPromptBuilder`, validator, provider settings | Mandatory active character/location; bounded projection and full prompt; complete facts not arbitrarily truncated; output and one repair independently bounded; no import from llm_world into context. |
| Provider or LLM settings | `LLMProvider`, `OllamaProvider`, `FakeLLMProvider`, `LLMSettings`, bootstrap role wiring, all three consumers (narrative/extraction/mechanics) | URL/model/timeout validation; normalized transport and malformed-response errors; fake parity; no hidden retry layering; network-free deterministic CI. |
| Native turn lifecycle | `DurableNativeTurnService` façade, `DurableTurnExecutionService`, typed durable-turn errors, challenge/commit/mapper/narration collaborators, `TurnResolutionService`, turn records/models, `TurnRepository`, `TurnResolutionRepository`, routers | Typed failure codes; idempotency; revision checks; lease fencing; same-resolution retry; no duplicate world operations; commit-before-narration; recovery after process restart and provider failure. |
| Clarification or manual dice continuation | Durable clarification/manual-roll collaborators, mechanics models, `TurnResolutionRepository`, `models/turn_api_schemas.py` and `models/integration_api_schemas.py` / routers, `DiceRoller` | Correct owning resolution; manual input bounds; state/lease transition; retry and replay behavior; deterministic dice result; exactly-once consequences. |
| Narrative/transcript regeneration | `DurableTurnNarrationService`, `TurnRepository`, external transcript-state adapter, version/read DTOs and API response mapping | Narrative regeneration does not reapply consequences; active/superseded transcript versions remain correct; previous external version checks; committed evidence used for narration. |
| SillyTavern external contract | `api/routers/integration.py`, integration façade/context adapter/errors, bootstrap wiring, native durable services, supported extension and smoke-test docs | URL/payload/status compatibility; required stable external ID on completion; resolve/complete idempotency; context/transcript-state reads; removed narrative-first route remains absent; live smoke test separate from CI. |
| Historical snapshot archive/migration | `migrations.py` `MIGRATIONS` registry, migration 029, `turn_snapshot_archive`, turn schema and migration replay tests | Archive all non-null historical JSON before dropping the runtime column; keep the archive inert; verify upgrade and fresh-database paths. |
| Session/transcript reads | `CampaignRepository`, `TurnRepository`, session/turn read models, campaign/turn routers, pagination response contracts | Campaign isolation; stable oldest-first ordering; status/version semantics; do not return GM-only session notes or internal resolution metadata. |
| Campaign clock | `CampaignClock`, clock schemas/router, `CampaignClockService`, `CampaignClockRepository`, effect expiry | Fictional time only; deterministic advance; expiry boundary and no dependence on server wall clock. |
| SQLite schema/data change | `migrations.py`, affected model, repository query/hydration, test fixtures and migration replay tests | Forward-only migration numbering; foreign keys; old data preservation; nullable/unique constraints; triggers/revision counters; rollback and fresh DB + upgrade paths. |
| API request/response contract | Bounded-context Pydantic schema module (`models/*_api_schemas.py`), compatibility facade (`models.schemas`), router, service, serializer/read model and API tests | OpenAPI diff; strict integer/boolean semantics; validation errors; stable status codes and field nullability; no business invariant only enforced by Pydantic. |
| Module/package relocation | Every source/test/script/docs import; package `__init__.py`; dependency matrix; architecture tests; package README | Consumer search before delete; canonical public import; no new compatibility shims unless explicitly justified; no stale documentation or test import paths. |
| CI/static-analysis workflow | `.github/workflows/tests.yml`, `.github/workflows/codeql.yml`, `pyproject.toml`, `requirements.txt`, ruleset checks | Aggregate job fails if any required component not green; pinned tool versions remain canonical; deterministic suite excludes real_llm; CodeQL Python and JS/TS remain required. |

## Cross-layer transaction ownership matrix

This table states the current intended owner; it is not permission to move transactions to another layer.

| Workflow | Transaction owner | Participants / invariant |
|---|---|---|
| Native durable commit | Turn/application commit collaborator with caller-provided SQLite connection | Turn-resolution state, campaign revision and world/character operations commit atomically; provider and narration remain outside. |
| Combat weapon attack | `CombatAttackService` opens one `IMMEDIATE` transaction | Encounter snapshot plus canonical target CharacterState/CreatureState HP are updated together; stale HP or stale turn position rejects the action. |
| Encounter create/start/advance/death-save/move/reaction | `CombatEncounterService` owns the existing service-level transaction per use case | Encounter and related creature/world/effect state must roll back together; map each path before changing repository APIs. |
| World operation application | World/application caller determines whether it owns the connection; `WorldService` passes the active connection to appliers/repositories | Multiple operation writes are one atomic unit; rollback must restore both persistent and in-memory state. |
| Persistent effect lifecycle | Effect service/repository transaction boundary | Campaign-scoped effect state and any derived condition projection must not diverge. |
| SillyTavern external narration completion | `DurableTurnNarrationService`, `TurnRepository`, external transcript adapter and completion schema | Persist narrative versions against the committed resolution; preserve external ID/version idempotency; never replay consequences. |
| Repository single-aggregate operation | Repository may use its own connection only where the public contract permits it | When a caller supplies `conn`, repository must use it and must not silently start another transaction. |

## When a refactor is not ready

Stop and design further if the PR:
- changes both ownership and external behavior without a compatibility test;
- adds a new cross-package dependency but leaves the dependency matrix/test unchanged;
- turns a data projection into a second canonical source of truth;
- mixes LLM provider calls with a SQLite write transaction;
- weakens idempotency, revision or lease checks;
- removes tests without retiring the behavior;
- changes migration history without replaying supported old database fixtures;
- treats a prompt instruction or model allowlist as permission to mutate;
- claims live Ollama or SillyTavern validation based only on deterministic CI.

## How to maintain this map

When a new capability or public workflow is added, update:
1. the capability package README;
2. the architecture map or shared-layer module catalogue;
3. this change-impact map when the workflow spans multiple layers;
4. the dependency matrix and boundary test if a new import edge is introduced;
5. tests and migration/read API contracts that protect observable behavior.

Keep this document concise enough to navigate: add paths and specific checks, not implementation walkthroughs or repeated source code.
