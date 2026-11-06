# Architecture, maintainability and product-readiness audit

**Audit date:** 2026-11-06  
**Repository:** IvanVM04/Campaign-Manager  
**Audited baseline:** main at 4308e879615c68e78a05e21faa1f3694c4539daa  
**Method:** static inspection of the repository tree, source modules, API routers, migrations, package guides, tests and recent CI.  
**Scope limitation:** this is not a local runtime certification. No real Ollama generation, live SillyTavern browser session, migration replay against a user database or manual smoke checklist was run during this audit.

## 1. Executive assessment

Campaign Manager has a sound foundation for a **single-player, local-first modular monolith**. It already has several important pieces that should be preserved: campaign-scoped runtimes, explicit SQLite transaction ownership in critical flows, a durable turn-resolution lifecycle, idempotency and lease fencing, a separation between committed consequences and generated narration, deterministic dice primitives, and a broad automated test suite.

The project does **not** need a rewrite or a move to microservices. The next improvements should strengthen the existing seams and build missing product capabilities around them.

Current readiness:

| Area | Assessment |
|---|---|
| Backend foundation and persistence | Established; keep the modular-monolith and SQLite model for the current local product |
| Durable native/SillyTavern turn flow | Strongly structured and covered by automated tests; live end-to-end play still needs manual verification |
| Service package boundaries | Partially migrated; package modules exist, but compatibility imports are still used by production code |
| D&D 5e 2014 rules | Useful deterministic subset, not a complete character/rules implementation |
| Character sheet and progression | Minimal mechanical state; insufficient for a long-running campaign |
| Campaign memory at large scale | Deterministic in-memory retrieval and context ranking exist; large-campaign retrieval needs measurement and improvement |
| Standalone UI | Not started; the current player-facing UI is SillyTavern |
| Operations and deployment | Local, single-process/single-worker assumptions are explicit and should remain so until cache/lock coherence is redesigned |

The latest main CI run inspected for this baseline is workflow run 42127830370 (run 668). Its Python tests, Ruff lint and JavaScript tests all completed successfully. The real-LLM tests are excluded from the standard CI run, and CI success does not establish that a live campaign works end to end.

## 2. What is already working well

- The application has a clear composition point in bootstrap/campaign_runtime.py and creates a campaign-scoped service graph.
- database.transaction(mode) makes connection and transaction ownership explicit. Critical use cases pass the same connection to participating repositories rather than silently opening nested transactions.
- The durable turn path separates planning from a short write transaction. It checks the campaign revision and context before applying consequences, stores the result, and narrates only after commit.
- Turn-resolution state is persisted separately from transcript/narrative versions. Idempotency keys, request fingerprints, challenge persistence and lease tokens protect duplicate delivery and recovery.
- The SillyTavern extension uses the durable resolve/complete contract. The legacy narrative-first path is separately identified and deprecated.
- The rules engine has good examples of reusable deterministic primitives: RandomSource and DiceRoller support injected randomness and manual dice; attack, damage, conditions, initiative and movement are isolated from HTTP and SQLite.
- Context building is already decomposed into search, expansion, ranking and rendering collaborators.
- World operation application is split by entity, item, resource and relation families.
- Automated tests cover important failure paths, transaction rollback, campaign isolation, stale revisions and SillyTavern idempotency. The latest main CI run is green.

These are assets. Future work should preserve their contracts rather than replace them with generic frameworks.

## 3. Verified findings and recommended actions

### A-01 — Capability packages are only partially adopted

**Priority:** P1  
**Status:** migration in progress; not a correctness defect by itself.

Source modules have moved into five capability packages: services/context, services/llm_world, services/world, services/campaign and services/characters. However, the old flat services.* module paths remain as compatibility re-exports, and the composition root and several production services still import those old paths. For example, bootstrap/campaign_runtime.py still imports campaign, character, context, LLM-world and world services via flat paths; services/world/world_service.py still imports the character package through its compatibility modules.

The combat, providers and turns directories currently contain package guides, not migrated source modules. The current README statement that no source modules have moved is therefore stale, while describing all package boundaries as complete would also be inaccurate.

**Action:**
1. Treat the new package paths as canonical for new code.
2. Migrate production imports one capability at a time, beginning with the composition root and imports inside already-migrated packages.
3. Keep compatibility shims during migration; do not delete them in the same change that migrates imports.
4. Extend architecture tests to detect imports of old shims from production modules and to enforce capability-level boundaries.
5. Move combat, providers and turns only when their current dependencies and public contracts are mapped.

### A-02 — Rules engine and application character model depend on each other

**Priority:** P1  
**Status:** verified source-level coupling.

models/character_state.py imports ruleset-specific Ability and Skill types. In the other direction, rules_engine/dnd5e_2014/character_checks.py and rules_engine/dnd5e_2014/weapons/attack_profile.py import models.character_state.CharacterState. This makes the supposedly reusable rules package depend on an application model while the application model depends on the rules package.

The existing architecture test does not catch this: its rules_engine boundary forbids API, services and repositories, but permits imports from models.

**Action:** define a ruleset-facing character-statistics contract or immutable input object owned by the rules engine. Adapt the application CharacterState to it at the application boundary. As a second step, assess whether generic character state should store ruleset-neutral identifiers rather than importing one ruleset's enums. Do this incrementally with adapter tests; do not move all models in one refactor.

### A-03 — WorldService exposes its mutable in-memory aggregate

**Priority:** P1 for a future UI/API; P2 for the current single-process MVP  
**Status:** verified design choice with a growing boundary risk.

WorldService.get_world() returns the exact mutable WorldState instance held by the service. Tests explicitly assert object identity, and current readers operate directly on it. This is convenient inside the application, but it means any code holding the object can mutate dictionaries or records without passing through validated operations, revision tracking or persistence.

**Action:** preserve the mutable aggregate for internal application workflows, but do not expose it as the contract for new read APIs. Introduce immutable/read-only query DTOs and query services for world entities, items, instances, resources, relations, events and graph relationships. Keep all writes behind application use cases and typed operations. Consider making internal access more explicit once callers have migrated.

### A-04 — Current API is not yet a sufficient backend for the requested standalone UI

**Priority:** P1  
**Status:** product capability gap.

The existing API is optimized for the current integration and gameplay paths. GET /world returns the whole in-memory world without pagination or capability-specific filters. The character router supports creation, inventory and equipment operations but does not expose a full character-sheet read endpoint. There is no general sessions list/detail API, no dedicated conversation browser/read model, and no general dice-roll endpoint. The current manual-roll endpoints resolve pending authoritative challenges; they are not a general dice tray.

**Action:** before implementing a full UI, define versioned read models and API contracts for:
- campaign overview and sessions;
- character sheet, abilities, proficiencies, inventory, equipment, resources and effects;
- world database explorer, filters, search, entity details and relations;
- conversation/transcript history, turn resolution evidence and timeline;
- combat encounter state and turn order;
- dice rolls, with a clear distinction between a flavor roll and an authoritative rules check.

All list APIs need pagination/filtering and stable sorting. The UI must never query SQLite or mutate WorldState directly.

### A-05 — Current character state is not a complete D&D character

**Priority:** P1 for playable D&D campaigns  
**Status:** verified product gap.

CharacterState currently holds basic attributes, hit points, AC, level, class name and several proficiency sets. CharacterCreate is explicitly a minimal demonstration schema. The repository does not yet provide a complete builder, race/species and background selection, full class/subclass features, level-up choices, hit dice, spell lists/slots, prepared spells, concentration or the broader character progression model.

The existing combat and weapon modules do not close this gap.

**Action:** define a versioned character aggregate in vertical slices: creation and validation first; core identity/ability/proficiency next; equipment and derived statistics; class features and progression; spellcasting and resources. The character sheet should be a read model derived from canonical state, not a second mutable copy.

### A-06 — Runtime cache and synchronization are process-local

**Priority:** P2 for the documented local product; P1 before any multi-worker/remote deployment  
**Status:** known constraint, not a current defect under the supported deployment.

CampaignRuntimeFactory caches runtimes in an in-memory dictionary. Each runtime owns a mutable world cache and a campaign-local TurnExecutionLock. The lock and cache do not coordinate other processes. The runtime cache also has no eviction policy, and runtime construction is performed while holding a factory lock.

**Action:** keep the documented one-process/one-worker deployment. Add tests for runtime invalidation and lifecycle. Consider constructing runtimes outside the global lock with per-campaign coordination if contention is measurable. Do not add a distributed lock or cache infrastructure until multi-process deployment becomes a real requirement.

### A-07 — Retrieval needs a large-campaign strategy

**Priority:** P2  
**Status:** functional current baseline; scale and relevance not benchmarked.

MemorySearchService performs deterministic search over the in-memory WorldState. ContextExpander, ContextRanker and ContextRenderer then expand and rank candidates under character-count budgets. This is a useful deterministic baseline, but it does not yet provide an explicit retrieval strategy for long campaigns with many entities, facts, events, sessions and transcript entries. Context budgets are measured in characters, not model tokens.

**Action:** first add representative fixtures and retrieval-quality/latency/token-budget benchmarks. Then consider SQLite FTS5 lexical retrieval, relationship expansion and recency-aware ranking, with optional semantic/hybrid retrieval only if measured results justify it. Keep retrieval deterministic and inspectable; do not add a vector database pre-emptively.

### A-08 — Operation schema knowledge is duplicated across layers

**Priority:** P2  
**Status:** verified design coupling.

OperationParser owns a private _BUILDERS registry. LLMWorldProposalValidator introspects that private attribute to produce its repair allowlist, while prompt instructions independently describe which operations the model may propose. The LLM response parser also rejects character operations after parsing. These are defensible safety constraints, but schema knowledge is spread across multiple places.

LLMWorldProposalPromptBuilder also creates a proposal prompt by calling the legacy prompt builder and extracting text between marker strings, then replacing phrases. A wording change in the legacy prompt can silently break proposal construction.

**Action:** create one public operation metadata registry describing operation identifier, operation class, fields, description and whether the LLM may propose it. Keep internal-only operations explicitly excluded. Build both prompt allowlists and parser validation from that registry. Extract a typed world-context projection shared by prompt builders rather than parsing a rendered prompt with string markers.

### A-09 — API error handling is only partially centralized

**Priority:** P2  
**Status:** verified inconsistency.

api/errors.py contains a useful stable error mapping and unwraps provider/extraction failures. The durable turn routes use it, but other routers still translate exceptions independently. Some generic exception paths return HTTP 500 with str(exc), while the global Starlette HTTP exception handler returns exc.detail verbatim. This creates inconsistent error codes and a risk of exposing internal exception details.

**Action:** define application error categories/codes at service boundaries and map them consistently at the API boundary. Internal 5xx details should be logged with correlation IDs and returned as safe public messages. Preserve useful 4xx conflict/validation details.

### A-10 — Large modules need targeted separation, not line-count refactors

**Priority:** P2  
**Status:** improvement opportunity.

The durable turn coordinator is now around 754 lines and has already delegated challenge state, challenge submissions, prepared commit, narration and result mapping. It should not be treated as the old monolith described in the 2026-11-05 audit. Further extraction should be driven by a distinct policy boundary and preserve its facade/state machine.

Other modules remain large:
- services/campaign_turn_service.py: compatibility-only, roughly 983 lines;
- services/legacy_silly_tavern_turn_service.py: deprecated compatibility flow, roughly 801 lines;
- services/silly_tavern_integration_service.py: active context/state adapter plus legacy delegation, roughly 492 lines;
- services/world/world_service.py: roughly 662 lines;
- services/context/context_expander.py and context_renderer.py: roughly 786 and 884 lines;
- services/llm_world/llm_world_prompt_builder.py: roughly 2,193 lines, much of it prompt/context content;
- migrations.py: roughly 2,298 lines and 28 ordered migrations;
- integrations/sillytavern/index.js: roughly 1,940 lines.

**Action:** split only when responsibilities can be named and tested independently. Do not split the long prompt by line count alone; first separate shared data projection and version the prompt template. Consider splitting the SillyTavern extension into API transport, settings UI and turn lifecycle modules. Keep migrations chronological and immutable; a future migration package/registry may improve discoverability without changing migration order.

### A-11 — Test coverage is broad, but several test files are difficult to navigate

**Priority:** P2  
**Status:** maintainability opportunity.

Large integration files such as tests/test_silly_tavern_integration.py combine service, route, legacy, concurrency and end-to-end cases. tests/test_durable_native_turn_service.py also carries many lifecycle scenarios. This is valuable coverage, not evidence that tests are redundant.

**Action:** split tests by contract (durable lifecycle, adapter/API contract, legacy compatibility, context/retrieval and concurrency). Keep tests focused on externally observable behavior. Add architecture boundary tests and a few representative large-world performance fixtures.

### A-12 — Migration runner and developer tooling can be more discoverable

**Priority:** P2  
**Status:** low-risk maintainability work.

The migration runner has an explicit ordered chain through version 28. That is safe and understandable, but the migration functions and runner are spread through a single large file. pyproject.toml includes pytest and httpx2 in the dev group, while CI installs Ruff separately rather than declaring it alongside the other development tools.

**Action:** consider an ordered migration registry/package only when the next migration change justifies it, and prove fresh-database plus upgrade-from-previous-version behavior. Add Ruff to the declared development toolchain and make the documented/CI installation path consistent. Keep requirements.txt runtime-only if that is the intended split.

## 4. Legacy, compatibility and likely-unused code

These categories are deliberately separate. Compatibility code is still used and must not be deleted just because it is old.

| Code | Current status | Recommendation / deletion gate |
|---|---|---|
| POST /integration/turn | Deprecated HTTP compatibility route; still exposed and logs usage | Retire only after checking supported extension forks/clients and observing zero usage for an agreed migration window |
| LegacySillyTavernTurnService | Called by SillyTavernIntegrationService.process_turn() for that deprecated route | Remove together with the route, tests and snapshot dependency after compatibility sign-off |
| WorldSnapshotRepository and snapshot tables | Used by the legacy narrative-first reconciliation path and covered by tests | Candidate for removal only when the legacy route is retired; do not drop historic data as part of an unrelated refactor |
| CampaignTurnService | Explicitly compatibility-only; no longer used by the native HTTP route, but remains in the runtime graph, app factory and tests | Migrate any in-process callers, remove its runtime wiring and compatibility factory, then delete in a separate PR |
| RuntimeProxy and app.py legacy service exports | Used by older routers/tests and compatibility surfaces | Migrate routers to get_current_runtime or explicit request dependencies; then remove proxies/exports |
| Flat service re-export shims | Still imported by composition, internal services and tests | Not dead code yet. Remove only after repository-wide import search, CI and downstream compatibility checks show zero callers |
| services/identity_service.py | Functions such as normalize_text, tokenize, canonicalize_tokens and names_match have no source-code callers in the inspected repository; the only search result was its package guide | Strong future deletion candidate. Confirm no dynamic/external imports, then delete with focused tests or a documented decision to keep it as a utility package |
| data/database.py | Tracked zero-byte file; repository code search found no imports | Likely accidental artefact. Remove in a small cleanup PR after confirming no external tooling expects the path |

Other notes:
- services/campaign_runtime.py is a compatibility re-export still used by test setup; migrate that import before retiring it.
- services/combat, services/providers and services/turns currently provide target-boundary documentation only. Their source modules remain under services/.
- Do not delete tests merely because they exercise legacy code; the tests are the guardrail until the legacy surface is removed.

## 5. Documentation audit

### Current source of truth

Use this audit as the current architecture and roadmap baseline until a newer dated audit supersedes it. The architecture index in docs/architecture/README.md should distinguish current contracts from historical snapshots.

### Documents to retain as history

The 2026-11-03 and 2026-11-05 audit, roadmap and architecture snapshots are useful records of earlier decisions. Do not erase them. They must not be treated as current status without checking this audit because:
- the 2026-11-05 architecture snapshot says service modules are still flat, although five capability groups have since moved;
- the 2026-11-05 comprehensive audit reports the malformed-proposal retry and planning-lease release as unresolved, but the current code has a bounded one-repair validator and a regression test for lease release;
- the 2026-11-03 roadmap still refers to an old next-PR sequence.

The current tests include test_invalid_llm_proposal_releases_planning_lease_and_same_identity_retries. The earlier F-01/F-02 findings should therefore be marked as resolved in any future consolidated issue tracker, not copied forward as open defects.

### Corrections needed in existing documentation

- Root README: the package migration paragraph still says no source modules have moved. Update it to say five capability groups have moved and retain flat compatibility shims; combat/providers/turns remain pending.
- services/context/README.md: says llm_world_context_renderer.py is proposed for llm_world, but it already lives in services/llm_world/.
- services/campaign/README.md: says role-specific provider construction is pending; LLMSettings and the runtime already configure narrative, extraction and mechanics roles. Keep runtime cache lifecycle and import migration as pending.
- services/providers/README.md: role-specific models/timeouts and runtime provider construction already exist. Document that actual provider source modules remain flat and that the provider port is currently minimal.
- services/turns/README.md: helper collaborators have already been extracted from the durable coordinator. State that this is partial decomposition, not that the earlier full extraction remains pending.
- docs/mvp-quickstart.md: contains literal backslash-n text in the SillyTavern connection step and limitations list; replace those with real line breaks.
- Root README clone URL uses an owner spelling different from the actual repository URL; correct it to IvanVM04/Campaign-Manager.
- Root README should link the new current audit/index and label the dated 2026-11-05 documents as historical snapshots.
- The manual SillyTavern smoke checklist is useful and should remain separate from CI. Record its result only after actually running it.

## 6. Target structure and interface strategy

Keep the modular monolith and organize by capability. A possible incremental source layout is:

- services/campaign: campaign lifecycle, clock and session use cases;
- services/characters: character creation, progression, sheet projections and mutations;
- services/world: typed world application and world queries;
- services/combat: encounter orchestration, attack/equipment workflows;
- services/turns: durable lifecycle and narration coordination;
- services/context: retrieval, expansion, ranking and budgets;
- services/llm_world: prompts, structured proposal parsing and validation;
- services/providers: LLM port and concrete provider adapters;
- rules_engine/dnd5e_2014: deterministic rules only;
- api/routers and api/schemas: HTTP transport and request/response DTOs;
- repositories: SQLite implementations;
- bootstrap: composition and runtime lifecycle.

This is an evolutionary map, not a requirement to relocate every top-level folder.

### Where interfaces/Protocols are worth adding

Use Protocols at real substitution or infrastructure boundaries, not for every class:
1. LLM generation port: the current provider abstraction is a good start; define structured-output capabilities and error semantics only where needed.
2. Ruleset input contract: remove direct dependency on application CharacterState from rules_engine.
3. World/campaign query and persistence ports where application services need to be independent of SQLite or an in-memory cache.
4. Dice randomness: keep the existing RandomSource injection pattern.
5. Runtime/application dependencies: keep concrete wiring in the composition root and replace strict concrete-type checks only where they obstruct a genuine adapter or test double.

Do not introduce generic repository interfaces, a generic Unit of Work, a message bus, event sourcing or a plugin framework pre-emptively.

### Operation and prompt contract

Create one typed operation registry as the authority for operation names, schema metadata, validation and LLM allowlisting. Generate prompt examples/allowlists from it where possible. Share structured context data between prompt builders rather than extracting it from rendered prompt text.

### UI architecture

The standalone UI should be a separate TypeScript application consuming the FastAPI API; it should not own rules or campaign state. React + TypeScript + Vite is a reasonable default, but the backend contracts should remain framework-agnostic.

For customizability, start with a registry of built-in panels/widgets and a versioned layout configuration:
- campaign overview;
- world/database browser with filters and detail views;
- character sheet;
- conversation/transcript and campaign timeline;
- dice tray;
- combat/encounter panel;
- session and campaign controls.

Persist layout/theme preferences separately from canonical game state. Begin with built-in panels and user-configurable arrangement, visibility, size and theme; defer arbitrary third-party plugin execution.

## 7. Recommended development order

Do not finish the entire SillyTavern campaign roadmap before starting the custom UI. SillyTavern is a useful early integration harness, but a thin native UI should arrive as soon as the read API is stable.

1. **Stabilize current baseline.** Run the manual SillyTavern checklist; correct active documentation; add architecture boundary checks; migrate production imports from shims; normalize API errors; define explicit deprecation gates.
2. **Deliver a small playable vertical slice through SillyTavern.** Campaign/session/character setup, exploration/social checks, simple combat, equipment basics, durable state and restart recovery. Keep the rules scope intentionally small.
3. **Expand the character and rules model.** Proficiencies, class features, leveling, rests, equipment effects, spellcasting/concentration and the encounter action economy, each implemented as tested vertical slices.
4. **Improve long-campaign memory and campaign tools.** Session summaries, timeline, event/NPC history, retrieval benchmarks and query filters. Add FTS/hybrid retrieval only when the current approach is measured to be insufficient.
5. **Stabilize read APIs and start the native UI early.** Build the campaign overview, world browser, character-sheet view, conversation history and dice tray before all advanced rules are complete.
6. **Grow the customizable UI alongside game systems.** Add configurable panels, layout persistence, themes, combat view and richer campaign exploration. Keep SillyTavern supported as an adapter, not as an architectural dependency.

## 8. Delivery estimates

Estimates below assume one developer already familiar with this repository, an existing working development environment, no major product redesign, and the stated bounded rules scope. A developer-day means roughly 6–7 focused engineering hours. These are planning ranges, not guarantees, and include implementation, tests, integration and documentation.

| Milestone | Scope used for estimate | Additional effort | Approx. cumulative full-time calendar |
|---|---|---:|---:|
| Functional local application | Reliable startup, campaign/session/character bootstrap, database persistence, SillyTavern connection, one verified end-to-end turn and restart recovery | 5–10 days | 1–2 weeks |
| Basic D&D campaign via SillyTavern | A short 2–4 session adventure around levels 1–3; exploration/social checks, simple combat, a limited set of weapons/conditions/classes, usable character state and persisted campaign history | +20–35 days | 5–9 weeks total |
| Large campaign via SillyTavern | Around 10–20 sessions and progression through a bounded level range; broader character progression, spellcasting subset, rests/resources, recurring NPCs, campaign timeline/summaries and scalable retrieval | +45–75 days | 14–24 weeks total (about 3.5–6 months) |
| Large campaign with standalone customizable UI | Versioned read APIs, world/database browser, full sheet read model, conversations/timeline, dice tray, combat view, layout/theme persistence and UI/API tests | +40–70 days | 22–38 weeks total (about 5.5–9.5 months); some UI work can overlap the previous milestone |

The first usable native UI slice (campaign overview + world browser + character summary + conversation history + dice tray) should be delivered before the entire large-campaign feature set. It can start once the read API contracts have stabilized, while rules and retrieval work continue.

For a part-time schedule, convert effort using available focused hours rather than calendar optimism. At roughly 10 hours per week, the final cumulative range can extend to around 1.5–2 years. At 20 hours per week, it is roughly 9–12 months, depending on interruptions and testing.

These estimates do **not** mean complete implementation of every D&D 5e 2014 class, subclass, spell, feat, monster, magic item or edge-case rule. They describe a bounded, explicitly documented playable subset. A near-complete 5e ruleset is a substantially larger, separately scoped effort.

## 9. Acceptance gates

A milestone is complete only when:
- its user-visible workflow works against a fresh database and an upgraded database;
- tests cover normal, invalid, duplicate/retry and failure/rollback paths;
- API contracts and versioning are documented;
- no unsupported rule is silently invented by the LLM;
- a live integration path has been manually exercised where applicable;
- architecture boundaries and package ownership remain clear.
