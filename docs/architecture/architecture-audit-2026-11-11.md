# Architecture and modularity audit — 2026-11-11

**Repository:** IvanVM04/Campaign-Manager  
**Initial audit baseline:** `main` at `bbcb7a0fda401c4d82d6ecff5119d6a0ec5eaec4` (after PR #169).  
**Latest revalidated baseline:** `main` at `a0e2c70bedd8f3e45f40d4c4f39d4fee13f8d4eb` (PR #189; 2026-11-11 21:26 UTC).  
**Method:** static inspection of the repository tree, current package guides, application composition, runtime context, turn services, prompt builders, CI workflow and prior audits.  
**Limitations:** no local test suite, live Ollama request, SillyTavern session, database migration replay or manual gameplay smoke test was executed as part of this documentation update. CI status is read from GitHub Actions, not reproduced locally.

## 1. Executive assessment

Campaign Manager should remain a **single-player, local-first modular monolith**. The current repository has a meaningful capability-package structure and a durable turn workflow. It does not need a rewrite, microservices, a message bus, a vector database or generic infrastructure abstractions.

The next phase should focus on making the existing module boundaries authoritative, retiring compatibility surfaces only after consumer verification, and removing duplicated contracts from the LLM proposal pipeline.

This audit supersedes the migration-status statements in the 2026-11-06 audit where current source has moved since that baseline. The 2026-11-06 audit remains useful history for its broader product/API assessment and delivery estimates.

## 2. Verified current baseline

### 2.1 Capability packages

All eight service capability packages contain implementation modules in the current tree:

| Package | Current responsibility |
|---|---|
| `services/campaign` | Campaign/session state and campaign clock |
| `services/characters` | Character creation, character use cases, sheet projection and typed character application |
| `services/combat` | Encounter, attack and weapon/equipment workflows; deterministic mechanics remain in rules_engine |
| `services/context` | Context retrieval, orchestration, expansion, ranking and rendering |
| `services/llm_world` | Prompt construction, world-context projection, extraction, response parsing and proposal validation |
| `services/providers` | LLM provider port, Ollama adapter, settings and fake provider |
| `services/turns` | Durable turn lifecycle, planning, challenge continuation, commit and narration |
| `services/world` | Validated world-operation application, query projections and serialization |

This is materially more advanced than the 2026-11-06 audit's package inventory, which described combat, providers and turns as documentation-only target packages. Their source modules now exist inside those packages.

The package structure is not the same as complete architectural isolation. A number of cross-package dependencies and root-level application services remain to be reviewed. Compatibility modules should be removed only after exact import and external-consumer checks.

### 2.2 Remaining service modules outside capability packages

The current `services/` root has one application adapter outside the eight capability packages:

- `silly_tavern_integration_service.py` — active external-integration adapter for context and external transcript-state reads. It also delegates the deprecated narrative-first endpoint to the quarantined turn collaborator.

The former root-level `DMService`, mechanics adjudicator, memory search, effect services, parser and compatibility shims now have canonical package owners. `LegacySillyTavernTurnService` lives in `services/turns`; its legacy status does not make it a dead module while the deprecated route remains supported.

The integration adapter is a candidate for a dedicated integration-owned package, but relocation should follow a consumer/dependency audit. Do not move it merely to make the `services/` root look smaller. Preserve its active context/transcript methods independently of the deprecated mutation route.

### 2.3 Runtime compatibility

The request-scoped runtime is now exposed only through `get_current_runtime()`. The HTTP middleware binds it with `bind_current_runtime()`, a context manager that restores the previous ContextVar token even when request handling raises. This keeps the ContextVar private to `api/runtime_context.py` and makes the binding lifecycle explicit.

PR #149 removes the `RuntimeProxy` class, all module-level service proxies, and their re-exports from `app.py`. The routers already use request-bound runtime access; repository code search found no remaining direct consumers of the proxy names. Tests now cover unbound access, nested bindings and restoration after exceptions. Runtime composition remains in `bootstrap/campaign_runtime.py` and `app.py`; routers must not construct runtimes.

`CampaignTurnService` and its dedicated tests have now been removed. Repository-wide source search found no production consumers; the active native workflow remains `DurableNativeTurnService`.

### 2.4 Turn lifecycle

The canonical `services/turns` package contains the durable coordinator and extracted collaborators for planning, challenge state/submission, prepared commit, mapping, narration and locking. `DMService` is now part of this package and owns narrative generation.

Preserve these invariants during future refactors:
- campaign revision/context checks occur before applying proposed consequences;
- the write transaction is short and atomic;
- provider calls and narration do not run inside the write transaction;
- durable resolution and transcript/narrative versions remain separate;
- retries and regeneration never reapply already committed consequences;
- idempotency, lease fencing and recovery semantics remain covered.

The deprecated `POST /integration/turn` route still requires `services/turns/LegacySillyTavernTurnService` and snapshot reconciliation. The collaborator has been moved into the turn package but remains quarantined from the active durable workflow. Its snapshot payload is JSON stored in the nullable `turns.snapshot` column; there are no dedicated snapshot tables. Do not remove the route, collaborator or snapshot data until supported-client usage and migration gates are satisfied.

## 3. LLM prompt and operation-contract findings

### 3.1 Proposal prompt decoupling

PR #161 completed the separation that was still pending in the previous audit. `LLMWorldProposalPromptBuilder` now obtains prompt sections directly from `LLMWorldContextRenderer`; it no longer parses the rendered legacy prompt or depends on marker-based extraction/replacement.

The active durable turn path passes `proposal_from_intent=True` from `DurableNativeTurnService` into `TurnResolutionService`, which calls `LLMWorldExtractor.propose()`. The 2,193-line legacy `LLMWorldPromptBuilder` remains behind the narrative-extraction `extract()` path and must be retained while verified legacy callers still depend on it.

**Status:** prompt-builder decoupling is complete. The outstanding problem is not the old marker coupling; it is the size and relevance of the world projection used by the structured proposal path.

### 3.2 Context selection and prompt-size budget

The active structured proposal path calls `LLMWorldContextRenderer.build_context(context)` directly. That renderer projects all known entities, items, item instances, resources, relations and non-secret events. It does not apply query relevance ranking or a size budget.

This differs from the narrative and mechanics paths:
- `DMService` uses `ContextBuilder` for its world context and recent history.
- `MechanicsAdjudicator` also uses `ContextBuilder` for relevant world context.
- `ContextBuilder` currently defaults to 6,000 characters for structured world context and 2,000 characters for recent turns. These are character budgets, not model-token budgets.

**Action:**
- have turn orchestration construct a typed, read-only context projection for the player intent;
- identify the active character, current scene/location, intent, confirmed mechanics and relevant recent events;
- select directly related records and bounded relationship expansion;
- preserve mandatory facts, permissions and authoritative state;
- apply deterministic ranking and stable ordering;
- enforce a configurable estimated-token budget with a model/provider safety margin;
- expose prompt diagnostics: selected/excluded record counts, rendered characters, estimated tokens and budget usage;
- bound repair context and invalid model output so a failed proposal cannot expand the follow-up prompt without limit.

Keep the dependency matrix intact: `services/llm_world` must not import `services.context` directly. Put projection orchestration at the turn/application boundary and pass a typed contract into the prompt builder. Do not silently truncate arbitrary strings or discard facts required for rules resolution. Measure behavior on representative small, medium and large campaign fixtures.

### 3.3 Operation metadata is duplicated

Operation parsing, proposal validation/allowlisting and prompt descriptions have overlapping knowledge. The validator currently relies on parser internals for at least part of its allowlist.

**Action:** introduce one public, typed operation metadata registry only after mapping all operation types and their trust levels. It should distinguish:
- operations the model may propose;
- operations that are internal/application-only;
- schema/field validation;
- human-readable descriptions and prompt examples.

Parsing and validation remain deterministic. The registry must not turn model output into an authorized write.

## 4. Test-suite strategy

The latest verified deterministic CI run collected 1,302 Python cases: 1,295 passed and 7 live-LLM cases were deselected. The branch-enabled coverage report showed 83% overall coverage. The repository contains a broad suite of focused test modules plus several oversized integration modules.

Largest navigation hotspots include:
- `test_silly_tavern_lifecycle.py`: 2,441 lines / 16 tests after the initial split in PR #186; versioned lifecycle, snapshot compatibility, retries, rollback and persistence remain mixed.
- `test_world_repository.py`: 1,817 lines / 24 tests; persistence, transaction and snapshot invariants.
- `test_turn_repository.py`: 1,420 lines / 38 tests; persistence, campaign isolation, connection ownership and validation.
- `test_turn_resolution_service.py`: 1,388 lines / 34 tests; legacy narrative-first and structured proposal planning contracts.
- `test_durable_native_turn_service.py`: 1,226 lines / 24 tests; durable commit, retries, narration, manual rolls and recovery.
- `test_context_builder.py`: 1,181 lines / 47 tests; relevance, expansion and character-budget behavior.
- `test_llm_world_extractor.py`: 1,152 lines / 35 tests; legacy extraction, structured proposals, parsing and repair.

**Disposition:** no test is approved for deletion by this audit. Tiny tests often protect narrow migration, serialization or public-contract invariants and should not be removed just because they contain one assertion. In particular, `test_architecture_boundaries.py` and `test_canonical_service_import_boundaries.py` protect different constraints and are not duplicates.

**Reorganization priorities:**
1. Split the SillyTavern integration tests by HTTP contract, durable lifecycle, adapter/context behavior and deprecated compatibility, preserving every assertion.
2. Separate legacy narrative extraction tests from player-intent proposal tests.
3. Split context tests by retrieval/expansion, ranking/budget and rendering/history where that improves navigation.
4. Keep migration tests tied to schema/data guarantees; do not delete historical migration coverage.
5. Keep `test_real_llm.py` as a separately marked suite; deterministic CI must remain independent of Ollama.
6. Revisit `test_turn_resolution_service_compatibility.py`: its single test checks canonical package exports, not a retired compatibility shim. Move/rename the assertion into the package-contract group rather than deleting it.

See [the test-suite audit](../quality/test-suite-audit-2026-11-11.md) for the full inventory and proposed sequence.

## 5. Documentation corrections identified

The 2026-11-06 audit and several package guides contain migration statements superseded by PRs #149–#169. The current documentation must reflect that:
- all eight capability packages contain implementation modules;
- the runtime proxy and old flat service shims have been removed;
- package dependency boundaries are enforced by architecture tests;
- the former `CampaignTurnService` has been removed;
- the legacy SillyTavern turn collaborator is inside `services/turns`, while the integration adapter remains active outside the capability packages;
- PR #161 completed proposal-prompt decoupling; relevance selection and a budget for structured proposals remain pending;
- coverage, repository-wide Pyright, CodeQL and Dependabot are active; the default-branch ruleset now requires aggregate CI and both CodeQL language checks.

Historical 2026-11-03, 2026-11-05 and 2026-11-06 documents remain immutable snapshots. Current status belongs in this audit, the CI/test audits and package READMEs.

## 6. Ordered implementation roadmap

Keep one active implementation branch and one open PR at a time. Each PR starts from the latest integrated `main`, remains open until every applicable check is green, and is corrected on that same branch.

| Order | Work package | Acceptance gate |
|---:|---|---|
| 0 | Maintain required CI and CodeQL checks | Active ruleset `protc1` requires `CI summary`, `Analyze (python)` and `Analyze (javascript-typescript)`; the CI summary aggregates deterministic tests, Ruff, Pyright and JavaScript. |
| 1 | Bound the active structured proposal context | Typed relevance-ranked projection, deterministic ordering, mandatory-fact preservation, estimated-token budget, provider safety margin and large-campaign regression tests. |
| 2 | Bound proposal repair and expose diagnostics | Validate/cap model output and repair input; do not resend an unbounded invalid response; report selection, rendered size, estimated tokens and budget usage. |
| 3 | Centralize operation metadata | Public typed metadata for model-allowed versus internal-only operations, schemas and prompt descriptions; preserve fail-closed validation. |
| 4 | Finish test navigation improvements | PR #186 completed the first SillyTavern test split; further split the remaining 2,441-line lifecycle module and other large modules without reducing assertions. |
| 5 | Integration adapter ownership | Decide whether `SillyTavernIntegrationService` needs a dedicated integration-owned package; preserve active context/transcript reads. |
| 6 | Retire legacy SillyTavern mutation path only when safe | Agreed zero-usage observation window, supported-client sign-off, consumer search and explicit `turns.snapshot` retention/migration decision. |
The CI findings and current check inventory are tracked in [the CI audit](../quality/ci-audit-2026-11-11.md).

### Non-goals for this phase

- No new gameplay features.
- No rewrite or microservice split.
- No premature vector database, event bus, distributed cache or generic repository framework.
- No deletion of legacy HTTP integration or snapshot data without a consumer/usage deprecation gate.
- No broad test deletion to improve test count.

## 7. Pull-request acceptance policy

Every implementation PR must:
- have one narrow architectural objective;
- be based on the latest `main`;
- include or update tests for the changed contract;
- pass Ruff, Python tests excluding `real_llm`, JavaScript tests, the clean Pyright scope and CodeQL analysis;
- include any newly applicable architecture/static checks;
- update package documentation when ownership or dependencies change;
- contain no unrelated formatting or feature changes.

Do not merge with failing checks. Fix failures on the same PR branch. The manual SillyTavern smoke test and live LLM checks must be reported separately; a green deterministic CI run does not certify live integration.


## 8. Revalidation against `main` after PR #189

This section supersedes any status or priority above that depended on the PR #169 baseline. The original findings remain useful as history, but the following is the verified repository state at `a0e2c70`.

### 8.1 Package and legacy surface

- All eight capability packages contain implementation code: `campaign`, `characters`, `combat`, `context`, `llm_world`, `providers`, `turns` and `world`.
- The only module directly under `services/` is `silly_tavern_integration_service.py`. Former flat service shims, runtime proxies and flat combat/provider paths are not outstanding cleanup tasks.
- `SillyTavernIntegrationService` remains active for context and external transcript-state reads. The deprecated `POST /integration/turn` route and its snapshot-backed collaborator remain compatibility behavior; do not delete them based only on age or naming.
- PRs #186, #187 and #189 have reorganized integration tests, extracted prepared-commit tests, and added durable retry/idempotency/restart coverage. Do not recreate these tasks.

### 8.2 Current prompt pipeline — highest architectural priority

There are two different prompt-size problems and they must not be conflated:

1. The active durable-turn path calls `LLMWorldExtractor.propose()` and `LLMWorldProposalPromptBuilder`. PR #161 removed the dependency on the legacy narrative-extraction prompt, but the proposal builder still asks `LLMWorldContextRenderer` to render every supported world entity, item, item instance, resource, relation and non-secret event. It applies no intent-based relevance filter and has no prompt/token budget.
2. The legacy `LLMWorldPromptBuilder` is a 2,193-line / 46,851-character module used by the narrative-first `extract()` path. It is a real maintainability hotspot, but it is not the builder used by the active structured proposal path. Its remaining use is tied to compatibility behavior, so splitting or retiring it must not be confused with fixing the active proposal context.

`ContextBuilder` already has deterministic search, relation expansion, ranking and character-based rendering limits (6,000 characters for world context and 2,000 for recent turns by default). Those limits are not token budgets and are not currently applied to structured proposals. The dependency matrix permits `services/turns` to orchestrate `services/context`, while `services/llm_world` must remain independent of it. The preferred boundary is a typed, read-only projection produced/orchestrated at the turn/application boundary and passed to the proposal prompt builder.

A second unbounded-growth point exists in `LLMWorldProposalValidator.parse_with_repair()`: its single repair prompt repeats the complete original prompt, validation error and complete invalid provider response. The retry count is bounded, but the repair input size is not. Validate/cap provider-response size and set a separate repair budget; do not solve this by arbitrary truncation of mandatory world facts.

The validator also reads the parser's private `OperationParser._BUILDERS` mapping to derive allowed operation types. Alongside repeated operation-field metadata in the parser, this is a candidate for a public typed operation metadata contract, but it is secondary to context selection and repair bounds.

### 8.3 Current test navigation state

The former 4,000-line `test_silly_tavern_integration.py` was split by PR #186 into API, lifecycle, service, schema and regeneration-failure modules plus shared support. The remaining `tests/test_silly_tavern_lifecycle.py` is 2,441 lines / 16 tests and is now the next integration-test navigation hotspot. PR #187 and #189 added focused fencing, recovery and idempotency assertions; preserve them.

See `docs/quality/test-suite-audit-2026-11-11.md` for the updated large-module inventory and split order.

### 8.4 Current validation and merge protection

At the revalidated commit, Tests run #43103128009 and CodeQL run #43103128059 both completed successfully. The deterministic suite collected 1,313 items, passed 1,306 and deselected 7 `real_llm` tests. Coverage reported 85.8% line and 72.6% branch coverage. Repository-wide Pyright reported zero diagnostics.

The active default-branch ruleset `protc1` requires `CI summary`, `Analyze (python)` and `Analyze (javascript-typescript)`. `CI summary` fails if a constituent deterministic test, Ruff, required scoped Pyright, repository-wide Pyright or JavaScript job does not succeed. Continue to inspect complete PR statuses; do not merge while a required check is failing, pending, cancelled or skipped.
