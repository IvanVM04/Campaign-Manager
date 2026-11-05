# Architecture audit and refactoring plan

**Date:** 2026-11-05  
**Repository:** `IvanVM04/Campaign-Manager`  
**Audited base:** `main` at `5c92be47a3fc71a0121e7449ed4f70dcf814141c`  
**PR under repair:** [#70](https://github.com/IvanVM04/Campaign-Manager/pull/70)  
**Method:** repository-tree, source, documentation, test-inventory and GitHub Actions inspection. This is a static audit; no local runtime, Ollama or live SillyTavern session was available.

## 1. Executive conclusion

**Keep the local-first modular monolith, SQLite and one-process deployment model. Do not rewrite the application or split it into microservices.**

The project has made substantial progress since the 2026-11-03 audit. The current tree already contains capability routers, a central API error handler, campaign-scoped state revisions, explicit transaction ownership in critical flows, a durable turn-resolution lifecycle, durable clarification/manual-roll continuation for the new flow, deterministic D&D rules modules, combat/effect/clock services, and a SillyTavern extension with readiness checks and JS tests.

Several earlier findings are therefore completed or superseded. The most important current issue is not missing infrastructure: it is that the application workflow and code organization have grown faster than the boundaries around them. The most valuable next work is controlled extraction of responsibilities from large orchestration services, removal of legacy duplicate paths, explicit runtime/provider lifecycle, and documentation that describes the actual current flow.

### What is already present — do not reimplement

| Capability | Current evidence | Audit status |
|---|---|---|
| FastAPI capability routers | `api/routers/*`; `app.py` mounts system, campaign, turns, integration, world, character, combat, effects, clock and memory | Implemented |
| Central API error contract | `api/errors.py` registers API, validation, HTTP and unexpected-error handlers | Implemented foundation; route-level consistency still needs work |
| Campaign isolation and state revisions | `CampaignScope`, campaign-scoped repositories, migrations 012–014 and 021 revision triggers | Implemented foundation |
| Short write transactions / stale-plan checks | `database.transaction`, campaign revision checks, critical services | Implemented in key paths; not a universal Unit of Work |
| Durable turn lifecycle | `turn_resolutions`, migration 022+, leases, idempotency/fingerprints, prepared/committed/narration-pending/completed states | Implemented foundation |
| Native and current SillyTavern resolution path | `DurableNativeTurnService` used by `POST /turn` and `/integration/turn/resolve` | Shared coordinator exists |
| Durable manual rolls and clarifications | Persisted in resolution lifecycle and exposed by integration endpoints | Implemented for durable path |
| Consequence-first / commit-before-narration | Structured proposal, atomic consequence commit, then native or external narration | Implemented for current durable path |
| SillyTavern readiness check | PR #68 checks campaign, active session, active character and context | Implemented |
| SillyTavern world continuity E2E regression | PR #67 tests durable event continuity after runtime reload | Implemented |
| Extension syntax fix | PR #69 fixes the import-list syntax issue | Merged |
| Deterministic D&D 5e 2014 subset | Checks, saves, dice, initiative, attack/damage, conditions, selected weapon/encounter flows | Partial rules coverage, not a complete rules engine |

The old `engineering-audit-2026-11-03.md`, `functional-audit-2026-11-03.md` and `roadmap-2026-11-03.md` are historical records. Their earlier snapshots and findings should not be silently rewritten; this document is the current audit addendum.

## 2. Current architecture

```text
SillyTavern extension / Native HTTP client
                  |
                  v
          FastAPI capability routers
                  |
          X-Campaign-Id middleware
                  |
        request-scoped CampaignRuntime
                  |
          application services
       /           |             \
  turn flow    campaign/world   combat/effects/clock
       |           |             |
  LLM ports    typed operations  rules_engine/dnd5e_2014
       |           |             |
       +-----------+-------------+
                   |
            SQLite repositories
                   |
        migrations + state revisions
```

### Current turn lifecycle

```text
Native POST /turn                 SillyTavern /turn/resolve
          \                              /
           \                            /
            -> DurableNativeTurnService
                    |
             consistent context + revision
                    |
          TurnResolutionService.prepare_turn
                    |
      adjudication -> deterministic supported checks
                    |
        structured consequence proposal
                    |
          validate + BEGIN IMMEDIATE
                    |
       state mutations + resolution record
           + resulting revision (atomic)
                    |
              narration_pending
                 /       \
       DMService         SillyTavern
       generate          generates prose
           \              /
            -> complete/persist narrative
                    |
                completed
```

The legacy `POST /integration/turn` and `SillyTavernIntegrationService.process_turn()` still exist for compatibility. They retain the older narrative-first extraction/snapshot reconciliation semantics and must not be mistaken for the active extension's durable flow.

## 3. Findings — current and evidence-based

### A-01 — Durable turn coordinator has too many responsibilities

**Priority:** P1  
**Evidence:** `services/durable_native_turn_service.py` is approximately 1,829 lines. One class owns request identity/fingerprints, context reads, planning leases, preparation, proposal serialization, mechanics serialization, commit transitions, manual-roll challenge handling, clarification challenge handling, SillyTavern adaptation, external narrative versioning/completion and native narration recovery.

**Risk:** changes to one lifecycle branch can regress another; method-level tests are large and highly coupled; invariants are hard to locate; the service is difficult to review.

**Direction:** preserve the existing public facade and persistence contract, but extract internal collaborators in small PRs:
1. `TurnResolutionCoordinator` / lifecycle application service: accept, claim, prepare, commit and recovery orchestration.
2. `TurnChallengeService`: clarification and manual-roll challenge state transitions/validation.
3. `ExternalNarrationService` or adapter: external transcript versioning/completion only.
4. `TurnResolutionCodec`: operation/mechanics serialization and reconstruction.

Do not extract all four in one PR. Begin with pure codecs or challenge handling; keep database transactions and lease fencing explicit. The facade should delegate without changing endpoint payloads or lifecycle semantics.

### A-02 — Legacy SillyTavern workflow duplicates turn authority

**Priority:** P1  
**Evidence:** `SillyTavernIntegrationService` is approximately 1,184 lines and still contains the old `process_turn` / `_process_turn_locked` flow, snapshot restoration, narrative extraction and legacy versioning, while the active extension uses `DurableNativeTurnService.prepare_external_turn()` and `complete_external_narration()`.

**Risk:** two turn-processing implementations coexist with different semantics. Future maintenance can accidentally fix or extend the obsolete path while the active path behaves differently. Legacy routes can remain a security/consistency bypass if treated as equivalent.

**Direction:** explicitly mark the old endpoint deprecated in API docs and README, add telemetry/logging for usage if feasible, document its weaker guarantees, and define a removal/migration policy. Do not remove it until extension compatibility requirements are confirmed. Keep snapshot code only for the legacy behavior that still needs it; do not duplicate that machinery in the durable path.

### A-03 — Layer-first package layout obscures domain ownership

**Priority:** P1/P2  
**Evidence:** domain code remains spread across global `models/`, `services/`, `repositories/` and `operations/` packages. The rules engine has a clearer ruleset boundary, but campaign, character, world, combat, effects, clock and turns do not have similarly enforced module boundaries.

**Risk:** cross-domain imports and circular dependencies can grow silently; ownership and transaction boundaries are convention-driven; new contributors must understand the entire layer graph.

**Direction:** first define allowed dependency direction and ownership in an import-boundary document. Then move one vertical slice at a time (start with the least coupled domain), using compatibility imports and unchanged public APIs. No mass file move and no generic framework.

### A-04 — Runtime cache/provider lifecycle is under-specified

**Priority:** P2  
**Evidence:** `CampaignRuntimeFactory` caches one runtime per campaign in an unbounded dict and exposes manual `invalidate()`. `_build_runtime` constructs one `OllamaProvider()` with implicit defaults and shares it across adjudication, extraction and narration. The app is explicitly single-process; the lock and in-memory world belong to that process.

**Risk:** long-lived installations with many campaigns can retain unused runtimes; provider URL/model/timeout cannot be validated or varied by role through a clear settings boundary; lifecycle shutdown and invalidation behavior are not explicit.

**Direction:** retain one process and one worker. Add typed settings for provider URL/model/timeouts and model-role assignment, explicit runtime invalidation on campaign deletion/config change, and cache observability/eviction only when safe. Add startup/shutdown hooks if providers/resources require them. Do not add distributed locks or multi-worker support now.

### A-05 — API error handling is centralized but endpoint semantics remain inconsistent

**Priority:** P2  
**Evidence:** `api/errors.py` provides stable error bodies and hides unexpected 500 details. However, several routers still catch broad exceptions and return endpoint-specific 400/409/500 details, while others use generic errors. Some domain errors are still mapped manually.

**Risk:** clients see different status/code semantics for equivalent failures; internal detail can leak through manually constructed HTTPExceptions; integration tests may validate incidental message text rather than stable codes.

**Direction:** use `APIError` (or a small typed hierarchy) at route boundaries, standardize status/code mappings, log unexpected exceptions once with traceback, and test the public contract. This is a consistency pass, not a second error framework.

### A-06 — Legacy and current turn pipelines coexist in the same service graph

**Priority:** P1/P2  
**Status:** compatibility boundaries documented and instrumented; legacy removal remains gated.  
**Evidence:** `POST /turn` and the active SillyTavern resolve/complete endpoints use `DurableNativeTurnService`. `POST /integration/turn` still invokes narrative-first `SillyTavernIntegrationService.process_turn()`; it is now marked deprecated in OpenAPI and logs campaign/external-turn usage. `CampaignTurnService` is not used by the native HTTP route, remains in the runtime graph for older in-process callers, and logs use of its public turn-execution methods.

**Risk:** the compatibility paths have different guarantees and may continue to be used by external clients or in-process consumers that are not visible in this repository.

**Direction:** use the [turn pipeline compatibility map](turn-pipeline-compatibility.md) as the route-to-use-case source of truth. Do not add gameplay behavior to compatibility paths. Do not remove the old endpoint, service, snapshot repository or compatibility proxy until downstream consumers are checked and structured usage is zero for an agreed migration window. Retire them in a separate reviewed PR; preserve existing campaign history.

### A-07 — Large modules concentrate domain policy and persistence logic

**Priority:** P2  
**Status:** `WorldApplier` operation families are delegated to cohesive collaborators; `ContextBuilder` now delegates candidate formatting, ranking selection, and budgeted rendering to `ContextRenderer`. Retrieval and graph expansion remain separate collaborators.  
**Evidence:** current file sizes include `LLMWorldExtractor` (~2,682 lines), `WorldApplier` (~1,352), `ContextBuilder` (~1,134), `CampaignTurnService` (~963), `SillyTavernIntegrationService` (~1,184), and `migrations.py` (~2,298). `WorldApplier` handles many unrelated operation families; `ContextBuilder` handles retrieval, ranking/budgeting and formatting.

**Risk:** unrelated edits conflict; tests need extensive fixtures; domain rules and presentation details are harder to isolate.

**Direction:** extract by cohesive behavior, not line count alone:
- split world operation handlers by entity/item/resource/relation/event while retaining one orchestrating applier and shared transaction contract;
- keep context retrieval (`MemorySearchService`), graph expansion (`ContextExpander`), ranking (`ContextRanker`), and textual candidate formatting/budgeting (`ContextRenderer`) behind separate boundaries; review candidate construction separately if it grows;
- split migrations into ordered modules only after protecting migration ordering and fresh/upgrade database tests;
- split extractor prompt construction, response parsing and operation policy.
A large file is a review signal, not proof that every class needs splitting.

### A-08 — Character and encounter state ownership must remain explicit as mechanics expand

**Priority:** P1 guardrail  
**Evidence:** player character mechanics are persisted in `CharacterState`; combat encounters hold combatant projections/snapshots; attack service synchronizes PC HP atomically. Persistent effects are authoritative and effective conditions are derived.

**Risk:** new writers for HP, conditions, temporary HP, death saves or resources could create divergent copies.

**Direction:** retain ADR-006/007. Before each new mechanic, define canonical owner, projection, mutation use case and transaction. Do not add a second persisted condition truth. NPC persistence ownership must be explicit before expanding it.

### A-09 — Ruleset completeness is a product risk, not a reason to rewrite architecture

**Priority:** P1 product scope  
**Evidence:** the deterministic rules engine supports a meaningful subset of D&D 5e 2014 (checks/saves, initiative, attack/damage/conditions and selected encounter/weapon behavior) but docs still state that character creation/progression, spellcasting, broad action economy and several combat features are incomplete.

**Risk:** the model may narrate unsupported mechanics as if they were authoritative; the user may overestimate what a convincing narrative means.

**Direction:** maintain a capability matrix by rules feature and test coverage. Implement only vertical slices with deterministic rules, canonical state ownership and API/integration tests. Do not treat the LLM as a substitute for missing rules.

### A-10 — README and architecture documents are out of sync with the implementation

**Priority:** P1 docs correctness  
**Evidence:** README still shows the older narrative-first SillyTavern flow and snapshot regeneration as the normal path; its API list omits resolve/complete/manual-roll/clarification endpoints. The 2026-11-03 architecture map describes the pre-router API and old native/SillyTavern flows; old functional audit includes findings corrected in later PRs.

**Direction:** README has been refreshed in this branch; preserve historical audits and add this dated current audit. Use the new current architecture snapshot as the canonical map.

## 4. Priority and proposed implementation sequence

| Order | Work | Priority | Estimate | Exit condition |
|---|---|---:|---:|---|
| 0 | Repair PR #70 logging change, add traceback regression test, get CI green | P0 | 0.5–1 day | Ruff + Python + JS pass; PR reviewed/merged |
| 1 | SillyTavern manual smoke test against demo campaign | P0 | 0.5–1 day | resolve/complete, clarification, roll, swipe, continuity checklist recorded |
| 2 | Turn lifecycle extraction: codecs/challenges first, keep facade | P1 | 2–4 days | same behavior and endpoint contract; failure-injection + regression suite |
| 3 | Deprecation boundary for legacy integration and old native path | P1 | 1–2 days | caller inventory, compatibility policy, tests and docs |
| 4 | Domain dependency/ownership map and import boundaries | P1/P2 | 1–2 days | module ownership matrix + enforceable import rules proposal |
| 5 | Provider settings + runtime lifecycle | P2 | 2–3 days | validated config, explicit cache invalidation, tests; still single worker |
| 6 | API error consistency pass | P2 | 1–2 days | stable status/code matrix and contract tests |
| 7 | Incremental extraction of world/context/extractor/migrations | P2 | 4–8 days | one module family per PR; no behavior changes |
| 8 | Ruleset capability matrix + next vertical slice design | P1 product | 2–3 days design; implementation estimated separately | supported/unsupported matrix with deterministic acceptance tests |

Estimates are engineering effort, not calendar guarantees. They assume one developer familiar with the repo, no new product scope, existing tests remain usable, and no unexpected migration/data compatibility issue. The estimates for steps 2–7 are not additive until the exact scope is agreed; parallelism and test findings can change them.

## 5. Progress and confidence

These percentages describe **audit coverage/confidence**, not project completion or a measured code-quality score.

| Area | Audit coverage | Confidence | Notes |
|---|---:|---:|---|
| Repository structure and architecture docs | 100% | High | Full tracked tree and current key docs inspected |
| PR #70 and CI failure | 100% | High | Diff, job outcomes and Ruff log inspected |
| Durable turn flow | 90% | High | Core lifecycle and key tests inspected; not every method exhaustively traced |
| SillyTavern adapter and compatibility path | 85% | Medium-high | Active endpoints and legacy service inspected; live client not run |
| Runtime/composition/provider | 90% | High | Runtime factory, middleware and composition inspected |
| Domain ownership/rules boundaries | 75% | Medium | ADRs, rule docs and key services inspected; not every rule or migration audited |
| Persistence/migrations | 60% | Medium | Migration inventory and key contracts inspected; not every SQL statement/data upgrade executed |
| API/error consistency | 65% | Medium | Central handler and key routers inspected; not every endpoint matrix-tested |
| Full dynamic verification | 20% | Low | CI result available for PR #70; no local full suite, real Ollama, or live SillyTavern test |

**Overall static architecture audit: approximately 80% coverage, medium-high confidence.** This is sufficient to prioritize refactoring without pretending that a static review certifies runtime correctness. A true 100% audit would require executing the full deterministic suite, migration replay against representative DB copies, real provider tests, and the manual SillyTavern checklist.

## 6. Verification still required

- Run the full CI workflow after the PR #70 update.
- Run the deterministic Python suite and Ruff locally or via CI.
- Run JS tests and a browser smoke test of the extension.
- Run the manual checklist in `docs/sillytavern-smoke-test.md` using a disposable campaign.
- Exercise process restart during pending clarification/manual roll and narration-pending states.
- Test migration replay from the previous schema version against a copy of a real database.
- Test multi-campaign isolation and stale-context behavior under concurrent requests.
- Verify provider failure logging and confirm no internal traceback is returned to HTTP clients.

## 7. Guardrails for all follow-up PRs

1. Inspect current implementation and callers before creating a finding or task.
2. Every finding must cite a current file, method, route, test or migration.
3. Mark work as **implemented**, **partially implemented**, **legacy-only**, **missing**, or **not verified**.
4. Never duplicate an existing capability under a new name without a concrete migration reason.
5. Preserve campaign isolation, idempotency keys, lease fencing, revision checks, atomic consequence commit and transcript version semantics.
6. One architectural concern per PR; add regression tests before extraction.
7. No microservices, distributed locks, ORM rewrite, database replacement or mass package move for the local MVP.
8. Update README/current architecture only when behavior actually changes; keep dated audit history intact.
