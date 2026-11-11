# Architecture and modularity audit — 2026-11-11

**Repository:** IvanVM04/Campaign-Manager  
**Audited baseline:** `main` at `248925293b46d37c97e29a32b8cd97f12443a676` (after merge of PR #155).  
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

The current `services/` tree still contains application-level services outside the eight packages, including:

- `DMService` now belongs to `services/turns`; it generates turn narration from injected context and provider collaborators and does not mutate world state.
- `mechanics_adjudicator.py` — now owned by `services/turns`; structured proposals are strictly validated before deterministic turn resolution.
- `memory_search_service.py` — now owned by `services/context`; deterministic retrieval/export over a supplied world snapshot.
- `PersistentEffectService` and `EffectiveConditionService` now belong to `services/campaign`; persistent effect lifecycle and derived D&D condition projection are kept together without duplicating state.
- `legacy_silly_tavern_turn_service.py` — compatibility implementation for the deprecated narrative-first route.
- `silly_tavern_integration_service.py` — still active for integration context and external transcript-state reads, and delegates the legacy route.

These are not automatically dead code. Each needs consumer mapping, ownership decision and focused tests before relocation or deletion. Avoid moving a file merely to make the root directory look smaller.

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

The deprecated `POST /integration/turn` route still requires the legacy service and snapshot reconciliation. Do not remove the route, service or historical snapshot tables until supported-client usage and migration gates are satisfied.

## 3. LLM prompt and operation-contract findings

### 3.1 Proposal prompt depends on the legacy prompt builder

The current `LLMWorldProposalPromptBuilder` is small (79 lines), but its context construction depends on the legacy `LLMWorldPromptBuilder` output and marker-based extraction/replacement. This couples the structured proposal path to the wording and layout of a legacy narrative-extraction prompt.

**Action:** extract a typed world-context projection and let each prompt builder render its own instructions from that projection. Do not parse one rendered prompt to construct another.

### 3.2 Context selection needs an explicit budget

`LLMWorldContextRenderer` currently projects broad world collections (entities, items, item instances, resources, relations and events). The structured proposal path needs a deliberate policy for relevance and size, rather than relying on the full world projection.

**Action:**
- identify the active character, scene/location, player intent and recent committed events;
- select directly relevant records and bounded relationship expansion;
- preserve mandatory facts and permissions;
- apply deterministic ranking and stable ordering;
- enforce a configurable model-token budget with a safety margin;
- expose diagnostics for included/excluded records and estimated/actual prompt size.

Do not silently truncate arbitrary strings or discard facts required for safety and rules resolution. Measure quality on representative small and large campaign fixtures.

### 3.3 Operation metadata is duplicated

Operation parsing, proposal validation/allowlisting and prompt descriptions have overlapping knowledge. The validator currently relies on parser internals for at least part of its allowlist.

**Action:** introduce one public, typed operation metadata registry only after mapping all operation types and their trust levels. It should distinguish:
- operations the model may propose;
- operations that are internal/application-only;
- schema/field validation;
- human-readable descriptions and prompt examples.

Parsing and validation remain deterministic. The registry must not turn model output into an authorized write.

## 4. Test-suite strategy

The suite is broad and protects important domain and durability invariants. Large test files are a navigation and maintenance problem, not proof of redundant coverage.

Priorities:
1. Produce a reproducible coverage baseline with `pytest-cov`, including branch coverage where practical.
2. Group tests by observable contract: domain/rules, repositories/transactions, durable lifecycle, HTTP/API, context retrieval, provider behavior and legacy compatibility.
3. Split oversized integration files without reducing assertions or weakening fixtures.
4. Retire tests for a legacy implementation only in the same change that removes that implementation and after consumer verification.
5. Add architecture tests for package dependency direction and prohibited compatibility imports.
6. Keep live-provider tests separately marked; deterministic CI must not require Ollama.

No tests are marked for deletion by this audit alone. A test is removable only when its behavior is obsolete or demonstrably duplicated and the surviving contract remains covered.

## 5. Documentation corrections identified

The 2026-11-06 audit and root README contain migration statements that no longer match the source tree. This PR corrects the most consequential ones:
- all eight service packages now contain source modules;
- the former flat compatibility modules for characters and LLM-world have been removed;
- the turns package owns the durable lifecycle collaborators and `DMService`; legacy turn services remain outside it;
- the proposal builder's dependency on the old prompt builder is still pending, not a completed extraction;
- the campaign package guide should not refer to an `identity_service.py` module that is absent from the current tree.

The dated 2026-11-03, 2026-11-05 and 2026-11-06 audits are retained as historical snapshots. Do not rewrite historical findings as if they had been true at the current baseline.

## 6. Ordered implementation roadmap

This is the agreed cleanup sequence. Keep one active implementation branch and one open PR at a time. Each PR must start from the latest integrated `main`, run the applicable checks, and be fixed in place until green.

| Order | Work package | Acceptance gate |
|---:|---|---|
| 0 | PR #147 runtime/router migration | Merged; follow-up main CI green |
| 1 | Refresh architecture inventory and package documentation | Current docs match source tree; no runtime behavior changed |
| 2 | Remove `RuntimeProxy` and old runtime exports | No production/test consumers; request-bound runtime tests pass |
| 3 | Define and enforce package dependency boundaries | Explicit allowlist plus negative import tests |
| 4 | Migrate/rehome remaining cross-cutting services | One responsibility per package; no circular dependencies; tests unchanged in behavior |
| 5 | Refactor LLM context/prompt and operation registry | No marker extraction from legacy prompt; bounded relevant context; proposal validation regressions pass |
| 6 | Audit and reorganize tests | Coverage baseline recorded; legacy tests removed only with their implementation |
| 7 | Add static quality tooling progressively | Pyright baseline, coverage reporting, CodeQL and optional SonarQube gates are documented and stable |

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
- pass Ruff, Python tests excluding `real_llm`, and JavaScript tests;
- include any newly applicable architecture/static checks;
- update package documentation when ownership or dependencies change;
- contain no unrelated formatting or feature changes.

Do not merge with failing checks. Fix failures on the same PR branch. The manual SillyTavern smoke test and live LLM checks must be reported separately; a green deterministic CI run does not certify live integration.
