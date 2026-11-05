# Comprehensive architecture and reliability audit

**Date:** 2026-11-05  
**Repository:** `IvanVM04/Campaign-Manager`  
**Audited revision:** `main` at `675cad5236f6060dac9fba0068bf429377e91091`  
**Baseline documents:** [Current architecture snapshot](current-architecture-2026-11-05.md) · [Audit and refactoring plan](audit-and-refactor-plan-2026-11-05.md)  
**Method:** static inspection of the tracked repository tree, selected source files, routers, tests and architecture documents; inspection of PR #70 and its GitHub Actions checks. No local test command, live Ollama request, migration replay against a user database, or live SillyTavern browser session was run as part of this audit.

---

## 1. Executive summary

**Keep the local-first, single-process modular monolith. Do not rewrite it, split it into microservices, or replace SQLite.**

The project has sound architectural foundations: campaign-scoped runtimes, typed operations, a deterministic rules-engine boundary, durable turn-resolution records separate from transcript rows, idempotency/fingerprints, planning leases, revision checks, atomic consequence commits, and a SillyTavern adapter that commits consequences before prose generation.

The most important reliability gap is at the boundary between probabilistic LLM output and deterministic application contracts. The system asks the model to emit typed operations and correctly rejects unknown operation types. However, one invalid operation currently aborts planning for the entire turn. The error is then wrapped as a generic durable-turn failure, returned as HTTP 409, and the resolution remains in `planning` until its three-minute lease expires. The recent `start_interaction` failure is a concrete example of this chain.

This is not a reason to make the parser permissive. Unknown operations must not be silently accepted or discarded. The correct improvement is to make the contract machine-readable, validate and retry a bounded number of times, preserve precise failure categories, and explicitly release or transition failed planning claims.

### Highest-priority conclusions

1. **P0 — LLM proposal contract:** share one authoritative operation schema/registry across prompt construction, provider constrained output (where supported), parser and tests; add bounded correction/retry for invalid model output.
2. **P0 — Failed planning recovery:** an unexpected planning exception leaves a leased `planning` record in place for up to three minutes; persist a failure code and release/requeue or reject it deliberately.
3. **P1 — Error taxonomy:** do not map every `DurableNativeTurnError` to HTTP 409. Distinguish client/state conflicts, invalid model proposals, provider outages and internal defects.
4. **P1 — End-to-end response boundary:** consequence commit and context retrieval occur in the same endpoint request but are separate operations; make response/retry semantics explicit and tested.
5. **P1 — Regression coverage:** add the exact unsupported-operation scenario at extractor, durable-service and API levels, including recovery and no-world-mutation assertions.
6. **P2 — Simplify safely:** extract responsibilities from large services, retire legacy paths only after caller/compatibility proof, and make runtime/provider settings explicit.

---

## 2. Architecture as found

### 2.1 Deployment and composition

The application is a local-first, single-player, single-process FastAPI application. `app.py` mounts capability routers and binds a campaign runtime from `X-Campaign-Id` through middleware and a `ContextVar`. `CampaignRuntimeFactory` caches one runtime per campaign. Each runtime owns a loaded in-memory `WorldService`, repositories, services and a per-campaign `TurnExecutionLock`.

This deployment shape is appropriate for the current product. The in-memory world and lock are process-local, so multiple Uvicorn workers or backend processes are not a supported deployment configuration. Do not increase worker count without redesigning cache ownership, locking and world-state coherence.

### 2.2 Current durable turn path

Native and current SillyTavern requests share `DurableNativeTurnService`.

```text
Native POST /turn              SillyTavern POST /integration/turn/resolve
         \                                  /
          \                                /
                DurableNativeTurnService
                           |
               context + history + revision
                           |
                TurnResolutionService
                           |
             mechanics adjudication (if needed)
                           |
                 LLM structured proposal
                           |
                OperationParser / typed ops
                           |
             prepared resolution + planning lease
                           |
              short BEGIN IMMEDIATE transaction
                - revalidate revision/context
                - apply world/character operations
                - persist evidence and resulting revision
                           |
                    narration_pending
                      /          \
               native DM       Sillytavern
                      \          /
                  complete transcript
                           |
                       completed
```

The architecture intentionally separates:
- durable execution envelope (`turn_resolutions`);
- historical narrative/transcript projection (`turns`);
- typed operations from the LLM;
- deterministic mechanics from narration;
- operation application from SQLite repository access.

This is a good direction and should be preserved.

### 2.3 LLM responsibilities

The runtime constructs one `OllamaProvider` and shares it between `DMService`, `LLMWorldExtractor` and `MechanicsAdjudicator`. Provider defaults are local Ollama, model `gemma4:26b`, and a 120-second timeout. The inspected provider request sends model, prompt and `stream: false`; it does not send a constrained JSON schema.

`LLMWorldExtractor.propose()` builds a prompt from the existing world-context prompt and player intent. It tells the model to return JSON and use parser-supported operations. `OperationParser` is the strict structural authority; `WorldService` / `WorldApplier` own semantic validation and mutation.

### 2.4 Persistence and consistency

SQLite is the durable source of truth. The project has campaign-scoped repositories and `CampaignScope`, explicit transaction ownership in selected critical workflows, campaign state revisions, a durable resolution state machine, idempotency identity/fingerprints, planning leases, atomic consequence application and transcript versioning separate from consequence application.

This is a meaningful foundation. It is not a distributed transaction system and should not be described as exactly-once execution across arbitrary external systems. The current guarantee is narrower: durable idempotency and atomic local database consequence commits, with retryable narration.

---

## 3. Findings

Severity:
- **P0:** directly affects core turn reliability or can leave a user-visible turn stuck.
- **P1:** important correctness, diagnosability or maintainability risk.
- **P2:** structural debt or future operational risk.
- **Guardrail:** preserve an invariant as features expand.

### F-01 — LLM operation contract is not robust enough for probabilistic output

**Priority:** P0 · **Status:** confirmed design weakness; `start_interaction` is a concrete manifestation.

**Evidence**
- `services/llm_world_extractor.py`: `propose()`, `_parse_response()`, `_parse_operations()`.
- `services/operation_parser.py`: `OperationParser._BUILDERS` and `_parse_operation()`.
- `services/ollama_provider.py`: `OllamaProvider.generate()` and request payload.
- `tests/test_llm_world_extractor.py`: supported-operation prompt and parser-failure tests.

**What happens:** the prompt asks the model to use parser-supported operations, but the model can still emit an unknown type or malformed fields. The parser correctly rejects it. `_parse_operations()` wraps the parse exception as `LLMExtractionError("Failed to parse operations")`; `TurnResolutionService.prepare_turn()` wraps that as `TurnResolutionServiceError`. The whole turn fails before a plan can be committed.

The prompt documents supported operation names, but model compliance remains probabilistic. The provider request does not enforce a JSON schema, and there is no bounded correction loop around an invalid proposal.

**Risk**
- One invented operation can block an otherwise ordinary social/exploration turn.
- The failure is not distinguishable to the client from other durable-turn failures.
- The model may repeatedly produce the same invalid shape.
- Making the parser permissive would create a worse risk: silently accepting unsupported semantics or dropping operations could corrupt campaign state.

**Recommendation**
1. Define one machine-readable operation contract from the same registry used by `OperationParser`: operation names, required/optional fields, field types, enums and ID-reference syntax. Keep disabled operations (such as character HP changes from LLM extraction) out of the model-facing allowlist.
2. Generate prompt documentation and provider JSON schema from that registry; do not maintain separate handwritten lists.
3. Use Ollama constrained JSON/schema output when supported by the selected model. Keep local parser validation mandatory.
4. On structural/unknown-operation failure, perform at most one bounded repair attempt. Supply the validation error and original intent/context; request a corrected complete proposal. Do not ask the model to invent missing facts.
5. If the corrected proposal is still invalid, fail with a typed `InvalidLLMProposal` and durable failure code. Do not silently drop unknown operations or commit partial proposals.
6. For genuine no-op intents (talk, ask, negotiate, inspect without confirmed state change), require `{"operations":[]}`. Narration can still proceed from an unchanged committed resolution.

**Acceptance tests**
- Unknown `start_interaction` in first response, valid empty proposal on repair → turn continues and commits zero operations.
- Unknown operation on both attempts → controlled failure; no world mutation; lease released/requeued or resolution rejected.
- Invalid field, missing required field, invalid enum and malformed JSON follow the same bounded policy.
- Every parser-supported operation is represented in generated schema tests.
- Social negotiation without a confirmed exchange produces no resource mutation.

### F-02 — Unexpected planning failures leave a three-minute planning lease active

**Priority:** P0 · **Status:** confirmed from current code.

**Evidence**
- `services/durable_native_turn_service.py`: planning claim, three-minute lease and exception handling around `_play_turn_locked`.
- `repositories/turn_resolution_repository.py`: `claim_for_planning()` only reclaims a `planning` record when `lease_expires_at <= now`.
- `models/turn_resolution_record.py`: `planning` may transition to `accepted`, `awaiting_input`, `prepared` or `rejected`.

**What happens:** a resolution is claimed as `planning` with a lease expiring in three minutes. The catch block handles a small set of known rejection cases, but an unexpected extractor/provider/parser exception is logged and wrapped without transitioning the record or clearing its lease. The repository will not let another request reclaim the same record until expiry.

The observed failure logged `resolution_id=4` and `lifecycle_state=planning`, which matches this path.

**Risk:** an immediate retry with the same external identity can fail even though the previous attempt has ended; no useful `last_error_code` is recorded; recovery depends on lease expiry rather than an explicit failure policy.

**Recommendation**
- Define explicit retryable and terminal planning-failure policies.
- For a known failure before any state commit, transition `planning -> accepted` (or introduce a retryable state), clear `lease_token` / `lease_expires_at`, and record a stable `last_error_code`.
- For invalid proposals that should not be retried automatically, transition to `rejected` with a stable code and safe recovery path.
- Preserve lease fencing: only the current lease holder may release or transition a planning record.
- Never reset a record to accepted after consequence commit. Committed/narration-pending recovery must use the existing idempotent resume path.
- Test provider, JSON parsing, parser validation, process interruption and plan-preparation failures.

### F-03 — Durable-turn errors are over-mapped to HTTP 409

**Priority:** P1 · **Status:** confirmed.

**Evidence:** `api/routers/integration.py` maps every `DurableNativeTurnError` from `POST /integration/turn/resolve` to 409. `api/routers/turns.py` uses similar broad mapping for native turns, manual rolls and clarifications. Unexpected exceptions are wrapped as the generic `DurableNativeTurnError("native turn execution failed")`.

**Risk:** 409 conventionally means the request conflicts with current resource state. The same status is used for stale revisions, active leases, invalid model output, provider errors and potentially programming defects. Clients cannot choose sensible retry or correction behavior from the status alone. The central API error envelope exists, but manually raised `HTTPException` instances still produce generic status-derived codes.

**Recommendation**
- Introduce typed failures: invalid input, stale context/conflict, active lease/retry-later, invalid LLM proposal, provider unavailable/timeout, and unexpected internal failure.
- Map 4xx only to client/state conditions; use 503 for temporary provider/dependency outages where appropriate and 500 for unexpected defects.
- Preserve stable `code` values; keep stack traces and internal details server-side.
- Add API contract tests for each category.

### F-04 — Resolve can commit consequences before a later context-read failure

**Priority:** P1 · **Status:** confirmed sequence; recovery needs an explicit test.

**Evidence:** `api/routers/integration.py`, `resolve_silly_tavern_turn()`, calls `prepare_external_turn()` and then `get_context()`. The durable service commits consequences and moves to `narration_pending` before the endpoint obtains the generation context.

**Risk:** if the second call fails after commit, the HTTP request can fail even though consequences are already committed. Durable idempotency should make retry safe, but endpoint behavior is not atomic and needs explicit tests.

**Recommendation:** keep the durable commit authoritative; do not roll it back because a later context read failed. Distinguish “resolution committed, context unavailable” from “resolution not committed”. Test a forced context-read failure after commit, retry with the same external identity, and verify the proposal is not run again and consequences are applied once.

### F-05 — Provider configuration and model-role separation are implicit

**Priority:** P2 · **Status:** confirmed composition choice; not inherently incorrect for the MVP.

**Evidence:** `services/campaign_runtime.py` creates one `OllamaProvider()` shared by three model-facing services. `services/ollama_provider.py` defines model/base URL/timeout defaults (120 seconds); the inspected request payload has no schema-format option.

**Risk:** prose, structured extraction and mechanics adjudication have different reliability/latency/format requirements. Configuration is not represented by a validated application settings object. A slow model call happens while the per-campaign turn lock is held, serializing same-campaign requests. Provider errors flow into broad turn-level exception handling.

**Recommendation:** introduce typed provider URL/timeout/model-role settings while keeping one provider by default; add a structured-output capability to the provider interface; expose provider readiness separately from API/SQLite readiness; keep LLM calls outside SQLite write transactions. Measure latency before changing lock scope.

### F-06 — Extension abort behavior is safe but diagnostics are weak

**Priority:** P1 · **Status:** confirmed.

**Evidence:** `integrations/sillytavern/index.js` handles non-OK resolve responses, logs the error, clears extension context and aborts generation.

**Positive:** the extension fails closed when it cannot obtain authoritative resolution evidence. It does not silently generate prose without backend context.

**Risk:** the extension logs a generic console error and extracts `detail`; it does not use stable API `code` values to provide actionable recovery guidance. A player may not know whether to retry, wait for a lease, correct an action or inspect backend logs.

**Recommendation:** keep fail-closed behavior; surface a concise notification with stable error code and safe guidance; include external turn identity or a short correlation ID in diagnostics; distinguish “not committed” from “committed but context/narration needs retry”.

### F-07 — Legacy and current turn pipelines coexist

**Priority:** P1 · **Status:** previously identified; still present.

**Evidence:** `CampaignRuntimeFactory` constructs `CampaignTurnService`, `DurableNativeTurnService` and `SillyTavernIntegrationService`. `POST /integration/turn` and the old narrative-first `process_turn` remain for compatibility; the current extension uses `/integration/turn/resolve` and `/integration/turn/complete`.

**Risk:** the workflows have different guarantees. Future work can modify the wrong path or tests can exercise legacy behavior instead of the active contract.

**Recommendation:** maintain a route-to-use-case table; label compatibility endpoints in OpenAPI/README; add usage telemetry/deprecation policy where practical; do not add new gameplay behavior to the legacy pipeline. Remove it only after compatibility and caller checks.

### F-08 — Orchestration and domain modules are oversized

**Priority:** P1/P2 · **Status:** previously identified; still present.

**Evidence:** large modules include `durable_native_turn_service.py`, `llm_world_extractor.py`, `world_applier.py`, `context_builder.py`, `campaign_turn_service.py`, `sillytavern_integration_service.py` and `migrations.py`.

**Risk:** lifecycle policy, parsing, persistence and presentation logic are difficult to reason about together; small changes can affect unrelated flows.

**Recommendation:** extract cohesive collaborators incrementally, preserving facades and behavior: operation schema/registry and proposal validation; durable turn codecs; challenge handling; external narration adapter; world operation handlers by domain family; context retrieval/ranking/rendering; ordered migration modules after migration-order tests exist. Do not split files solely by line count.

### F-09 — Domain/package dependency boundaries are not enforced

**Priority:** P2 · **Status:** previously identified; still present.

**Evidence:** domain code remains distributed across layer-first `models/`, `services/`, `repositories/` and `operations/`. Rules-engine boundaries are clearer than campaign/world/combat boundaries.

**Risk:** cross-domain imports and circular dependencies can grow silently; ownership and transaction boundaries remain convention-driven.

**Recommendation:** write a dependency direction/ownership matrix; add lightweight import-boundary tests (for example, rules engine must not import API, SQLite or provider modules); move one vertical slice at a time only when justified.

### F-10 — Runtime cache and process lifecycle need explicit policy

**Priority:** P2 · **Status:** previously identified; still present.

**Evidence:** `CampaignRuntimeFactory` uses an unbounded per-campaign dictionary and manual `invalidate()`; runtime state and locks are process-local.

**Risk:** long-lived use with many campaigns can retain runtimes. Multiple processes would have divergent in-memory worlds and independent locks.

**Recommendation:** keep one worker for now and document it as a hard deployment constraint; invalidate runtime on campaign deletion/configuration changes; add cache diagnostics before eviction (eviction must not discard active work).

### F-11 — README retains a stale snapshot/regeneration description

**Priority:** P1 documentation correctness · **Status:** confirmed.

**Evidence:** README's durable-turn section correctly says swipes do not restore snapshots or replay consequences, but its later “World Snapshots” section still describes restoring the world before a turn and applying a regenerated version. The durable SillyTavern adapter contract says the current extension does not use that legacy behavior.

**Risk:** contributors can misunderstand the source of truth and reintroduce snapshot-based regeneration assumptions.

**Recommendation:** label snapshots as legacy compatibility behavior and state explicitly that the active durable flow versions narration only. Keep historical audit documents dated.

### F-12 — Rules-engine scope must remain explicit

**Priority:** P1 product guardrail · **Status:** partial ruleset, as documented.

**Evidence:** `rules_engine/dnd5e_2014/` covers deterministic d20 checks/saves, dice, initiative, attack/damage primitives, conditions and selected weapon/encounter flows. Character progression, spellcasting and broader action-economy/range/cover behavior remain incomplete.

**Risk:** an LLM can narrate unsupported mechanics as if they were rules-engine outcomes.

**Recommendation:** maintain a supported/partial/unsupported capability matrix. Every new mechanic needs deterministic rules, canonical state ownership, transaction behavior, API and regression tests. Persuasive narration is not proof that a rule was resolved.

### F-13 — Complete writer/lock/cache-coherence audit is still required

**Priority:** P1 guardrail · **Status:** not fully verified; not a confirmed bug.

**Evidence:** each `CampaignRuntime` owns a loaded in-memory `WorldService`; selected services use `TurnExecutionLock`; critical turn application uses explicit SQLite transactions and revision checks. This audit did not exhaustively trace every world/character/effect/combat route to prove that every mutation shares the same lock and in-memory coherence contract.

**Risk:** a mutation route that bypasses the campaign lock or updates SQLite without refreshing the runtime's in-memory world could produce stale context or lost updates.

**Recommendation:** build a route-to-writer matrix recording lock, transaction owner, canonical state, revision trigger and in-memory refresh/rollback behavior. Add multi-route tests that mutate through one endpoint and read through another, both in the same runtime and after runtime reload. Do not call this a confirmed defect until that verification exists.

---

## 4. What is already implemented — preserve it

Do not rebuild these capabilities under new names:

- Capability-oriented FastAPI routers and request-scoped campaign runtime selection.
- Campaign-scoped repositories and `CampaignScope`.
- Central API error envelope and unexpected-error logging.
- Explicit SQLite transaction helper and caller-owned connections in selected critical workflows.
- Campaign state revisions and stale-plan checks.
- Durable turn-resolution records distinct from transcript rows.
- Stable idempotency identity/fingerprints, planning leases and lifecycle transitions.
- Consequence commit before external SillyTavern narration.
- Current adapter narrative versioning/swipes without replaying consequences.
- Durable manual-roll and clarification challenges.
- Deterministic D&D rules modules with partial-scope documentation.
- SillyTavern readiness checks and JS tests.
- Tests for parser validation, operation references, resource operations, durable idempotency, narration retry, swipe behavior, world continuity and secret-event exclusion.

PR #70 is merged into `main` at the audited revision. Its GitHub Actions checks `lint`, `test-js` and `test` completed successfully. This confirms those jobs passed for that commit; it does not certify live Ollama generation or a manual browser smoke test.

---

## 5. Test and verification assessment

### Verified from repository/CI evidence

- The tracked tree contains broad Python unit/service/API/rules tests and JavaScript extension tests.
- Parser tests cover unknown/malformed operations and supported resource operations.
- Extractor tests verify supported-operation prompt documentation, parser-failure wrapping, intent-based proposal input and exclusion of secret world events.
- Durable-service tests cover commit-before-narration, idempotent retry, narration-failure recovery and swipe versioning without reapplying consequences.
- PR #70 CI checks passed: `lint`, `test-js`, `test`.

### Not verified by this audit

- Live generation using the configured Ollama model.
- The exact `start_interaction` failure and recovery against a local running database after any proposed fix (no code changes were made in this audit).
- Browser-level SillyTavern generation, extension prompt cleanup and swipe behavior.
- Full migration replay from older schema versions against a copy of a real campaign database.
- Cross-process behavior (not a supported deployment mode).
- Exhaustive lock/transaction ownership for every mutating API route.
- Long-running runtime cache behavior with many campaigns.

### Required regression suite before considering F-01/F-02 fixed

| Scenario | Expected result |
|---|---|
| Valid empty proposal | Narration proceeds; no world mutation |
| Valid supported proposal | Typed operation is applied once |
| Unknown operation once, repair succeeds | Corrected proposal is validated and processed |
| Unknown operation persists after repair | Controlled failure; no world mutation; lease released/rejected with stable code |
| Provider timeout before planning completes | Retryable failure; no stuck planning lease |
| Process interruption during planning | Expired lease can be reclaimed safely |
| Stale context after planning | Prepared plan rejected; no partial state commit |
| Failure after consequence commit, before narration | Same identity resumes narration; no re-planning or duplicate mutation |
| Context retrieval failure after commit | Retry returns committed resolution and context; consequences remain single-applied |
| Social request/negotiation without accepted transfer | No resource balance mutation |
| Confirmed resource transfer | Correct resource and owner balance change exactly once |

Run automated tests and the manual checklist in `docs/sillytavern-smoke-test.md` against a disposable campaign. Record backend revision, extension revision and outcome. Do not mark manual cases passed based only on unit tests.

---

## 6. Recommended implementation sequence

### Phase 0 — Make turn failures recoverable (P0)

1. Add typed error categories and stable error codes.
2. Fix planning-lease cleanup for all failures before commit.
3. Add the exact unknown-operation regression at extractor, durable-service and API layers.
4. Ensure the same external identity can recover immediately according to the explicit retry policy.
5. Keep the current strict parser; do not swallow unknown operations.

**Exit:** invalid model output cannot leave a live planning lease behind; failed proposals do not mutate the world; clients receive truthful status/code.

### Phase 1 — Harden the LLM contract (P0/P1)

1. Introduce a shared operation schema/registry.
2. Generate prompt operation descriptions and constrained-output schema from the registry.
3. Add one bounded correction attempt.
4. Add model contract tests for every allowed operation and prohibited operation.
5. Add telemetry for validation categories without logging full sensitive prompt/context.

**Exit:** model-facing operation types are generated from the parser contract; invalid output has deterministic, bounded handling.

### Phase 2 — Clarify endpoint and extension recovery (P1)

1. Test post-commit context-read failure and retry.
2. Surface stable error codes and safe recovery guidance in the extension.
3. Record a correlation identifier for backend logs and extension diagnostics.
4. Preserve fail-closed generation when authoritative context is unavailable.

**Exit:** the player can distinguish retryable, corrective and terminal failures without reading a Python traceback.

### Phase 3 — Reduce architectural ambiguity (P1)

1. Map every public turn route to its active use case.
2. Mark legacy routes and services explicitly.
3. Add deprecation/usage policy for `POST /integration/turn`.
4. Extract challenge handling and turn codecs behind the existing durable-service facade.

**Exit:** one clearly documented source of truth for new turn behavior; compatibility remains covered.

### Phase 4 — Enforce domain and persistence boundaries (P1/P2)

1. Complete the route-to-writer lock/transaction/revision matrix.
2. Add import-boundary tests.
3. Extract world applier handlers and context pipeline in separate PRs.
4. Split migrations only with ordered migration replay tests.
5. Add typed provider settings and explicit runtime invalidation.

**Exit:** mutation ownership and dependency directions are testable rather than merely documented.

### Phase 5 — Rules capability roadmap (P1 product)

Maintain a supported/partial/unsupported D&D 5e 2014 feature matrix and implement one vertical slice at a time. Every slice must include deterministic rules, canonical state owner, persistence transaction, API and integration tests.

---

## 7. Guardrails for future work

1. Do not introduce microservices, distributed locks, a database replacement or a rewrite for this local MVP.
2. Do not make the operation parser permissive to hide model errors.
3. Do not let the LLM directly mutate SQLite or authoritative character mechanics.
4. Do not hold SQLite write transactions across LLM calls, HTTP calls or user input.
5. Preserve campaign scope, idempotency fingerprints, lease fencing, revision checks and atomic consequence commit.
6. Never re-plan or reapply consequences for a committed external turn; resume narration instead.
7. Every new persistent mechanic must define canonical state ownership and projections.
8. Every finding must cite a current file/method/test and be marked confirmed, partial or not verified.
9. One concern per implementation PR; add regression tests before refactoring.
10. Update current architecture docs when behavior changes; keep historical audits dated.

---

## 8. Suggested next task

Start with a small reliability PR addressing **F-01 and F-02 at their shared boundary only**:
- typed proposal-validation failure;
- bounded schema-aware repair;
- explicit release/reject of the planning lease;
- regression tests for the observed `start_interaction` case;
- API status/code contract test.

Do not combine this with splitting `DurableNativeTurnService` or reorganizing packages. First make the current architecture fail safely and recoverably; then refactor it.
