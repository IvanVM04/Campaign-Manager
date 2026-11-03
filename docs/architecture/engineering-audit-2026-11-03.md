# Architecture and engineering audit

**Date:** 2026-11-03  
**Repository:** `IvanVM04/Campaign-Manager`  
**Audited baseline:** `main`, commit `5fbcb86f357350de9b77f386344d7babf6f681c0` (PR #18)  
**Review type:** static source audit; not a runtime certification.

## 1. Executive conclusion

**Keep the modular monolith. Do not rewrite it. Do not introduce microservices.**

The project has a sound direction in several important areas: campaign isolation, typed operations, a separate deterministic rules package, explicit repositories, short write transactions for native turns, transactional turn reconciliation, and tests across most major subsystems.

The architecture is not yet solid enough to support unrestricted feature growth. The main weaknesses are:

1. the native and SillyTavern turn paths have different application semantics;
2. final narrative generation still precedes consequence extraction and commit;
3. API composition and routing are concentrated in `app.py`;
4. transaction ownership and persistence access are distributed across services;
5. domain boundaries are implicit in a layer-oriented package layout;
6. character, encounter, effects and equipment state require explicit ownership/synchronization rules;
7. runtime/provider lifecycle is designed for one local process, with some unbounded/in-memory state.

These are **incremental consolidation problems**, not evidence that the architecture must be replaced.

## 2. Findings

### A-01 — The turn pipeline is not yet consequence-first and commit-then-narrate

**Priority:** P1 — resolve before treating the AI DM workflow as authoritative.

**Evidence:** `TurnResolutionService.prepare_turn()` calls the mechanics adjudicator and deterministic check resolver where applicable, then `DMService.generate()`, then `LLMWorldExtractor.extract()`. The resulting world operations are applied later by `CampaignTurnService` inside a transaction.

The write transaction is correctly kept short, but the final narrative is still the source text from which world consequences are extracted. The application does not yet persist a structured consequence plan and then generate narration from the committed result.

**Risk:** retries can require another model call; narrative and committed facts are coupled; it is harder to independently recover narration after a persistence success; the model can narrate consequences that fail validation or commit.

**Direction:** introduce an explicit, validated consequence proposal as an application artifact. Validate authority and preconditions, resolve mechanics deterministically, commit state plus a durable turn/resolution record, then generate narration from the committed result. Store enough state to retry narration without reapplying consequences.

Do not attempt this as a broad rewrite in PR19. Design and implement it as a separately reviewed application-workflow change.

### A-02 — Native and Sillytavern turn paths have different authority contracts

**Priority:** P1 — resolve before claiming feature parity between clients.

**Evidence:** `POST /turn` uses `CampaignTurnService` and `TurnResolutionService`, including `MechanicsAdjudicator` and deterministic checks/saves. `POST /integration/turn` accepts an already-generated narrative and uses `SillyTavernIntegrationService` plus `LLMWorldExtractor` to persist world changes and reconcile external turn versions. The extractor explicitly rejects `CharacterOperation` values.

**Risk:** the same player action can have different guarantees depending on entry point. The SillyTavern path is a narrative/world-extraction adapter, not the same rules-adjudicating use case as the native path.

**Direction:** define one application-level turn/consequence contract and make both entry points explicit adapters. If SillyTavern intentionally remains externally narrated, require a structured, validated result payload or clearly label the weaker mode; it must not bypass mechanics/authority checks.

### A-03 — `app.py` combines transport, composition and compatibility code

**Priority:** P1 — consolidate before adding substantial new API surface.

**Evidence:** `app.py` contains FastAPI construction, CORS, campaign middleware, runtime binding, older service factory functions, compatibility proxies, route handlers, error conversion and response serialization. The file is approximately 1,325 lines at the audited baseline.

**Risk:** route changes are harder to isolate and test; transport details are coupled to service composition; legacy compatibility code obscures the active dependency graph.

**Direction:** extract routers by capability (campaign, characters, turns, memory/world, encounters, effects/clock, SillyTavern integration), keep a small application factory/composition root, and move request/response serialization to transport modules. Preserve the public paths and campaign middleware contract. Do not split services while moving routes.

### A-04 — Transaction boundaries are real but not represented as an application abstraction

**Priority:** P1/P2 — introduce selectively, not mechanically.

**Evidence:** `CampaignTurnService`, `SillyTavernIntegrationService`, `CombatAttackService`, `CombatEncounterService`, `PersistentEffectService` and `CampaignClockService` import `get_conn()` and open transactions themselves. Repositories often accept an optional caller-supplied `conn`, which is a useful foundation.

**Risk:** transaction policy is repeated across use cases; it is harder to test orchestration without a real SQLite connection; a service can accidentally compose operations outside a shared transaction.

**Direction:** introduce a narrow Unit of Work / transaction runner at the application-infrastructure boundary. Keep repository methods able to use a caller-owned connection. Do not hide transaction semantics behind a generic ORM or abstract every SQL statement.

### A-05 — Domain boundaries are obscured by layer-first package organization

**Priority:** P2 — gradual restructuring.

**Evidence:** domain-specific code is distributed across global `models/`, `services/`, `repositories/` and `operations/` packages. Rules are better isolated under `rules_engine/dnd5e_2014`, but campaign, character, combat, effects, clock and turn application logic do not have similarly explicit package boundaries.

**Risk:** dependencies between domains are governed by convention; ownership is difficult to understand; feature growth can produce cross-domain imports and accidental cycles.

**Direction:** first document boundaries and allowed dependencies. Then move one vertical slice at a time (for example `campaign`, `character`, `combat`, `effects`, `turns`) while preserving public service interfaces. Avoid a mass file move.

### A-06 — Runtime cache and locks support one process, not horizontal scaling

**Priority:** P2 — acceptable for current local MVP; lifecycle work needed.

**Evidence:** `CampaignRuntimeFactory` stores runtimes in an in-memory dictionary and has manual invalidation. Each runtime has a process-local `TurnExecutionLock`. Provider construction is hard-coded to `OllamaProvider()`. Manual pending rolls are held in a service dictionary with a 15-minute lifetime.

**Risk:** runtime count can grow with campaigns; restart loses pending manual rolls; multiple processes have separate world/runtime caches and locks; configuration cannot be varied cleanly by role/provider.

**Direction:** keep the single-process/single-worker restriction. Add explicit runtime lifecycle/invalidation and validated provider settings before supporting more complex deployment. Persist pending rolls only if restart recovery becomes a product requirement. Do not add distributed locks now.

### A-07 — Character and encounter mechanical state have a synchronization contract

**Priority:** P1 — enforce for every future mechanical mutation.

**Evidence:** `CharacterState.current_hp` is persisted separately from `CombatantState.current_hp` in encounter snapshots. `CombatAttackService` verifies they agree and updates the character and encounter within one transaction.

**Risk:** any future HP writer outside this path can desynchronize the active encounter. Adding conditions, temporary HP or death saves in both models independently would compound the problem.

**Direction:** designate character mechanics as canonical persistent state and encounter combatant state as a synchronized encounter projection for persisted player characters. Route every cross-write through one transaction-owning use case. Explicitly decide the ownership of NPC mechanics before persisting NPC state outside encounters.

### A-08 — Persistent effects and effective conditions must remain distinct

**Priority:** P2 — boundary guard.

**Evidence:** persistent effects are stored as campaign records; `EffectiveConditionService` projects them into condition state consumed by combat. Campaign clock advancement expires due campaign-time effects in the same transaction.

**Risk:** storing derived conditions independently could create stale or contradictory state, especially when round/turn durations are added.

**Direction:** keep persistent effect identity/lifecycle authoritative and effective conditions derived. Design a common duration/lifecycle model for campaign-time and round/turn effects before adding more duration types.

### A-09 — API error semantics are inconsistent

**Priority:** P2 — address during API extraction.

**Evidence:** route handlers map different service exceptions to HTTP 400, 409, 422, 404 or 500 in endpoint-specific ways; some broad exception paths return exception text while others use generic messages.

**Risk:** clients cannot rely on stable error contracts and internal details may leak.

**Direction:** define stable application error categories (invalid command, not found, conflict/stale state, provider unavailable, persistence failure, unexpected error) and centrally map them to HTTP responses. Keep diagnostic detail in server logs, not public response text.

### A-10 — Context budgeting is character-based, not model-token-based

**Priority:** P3 — improve when provider configuration is centralized.

**Evidence:** `ContextBuilder` uses `DEFAULT_MAX_CONTEXT_CHARS` and `DEFAULT_MAX_RECENT_TURNS_CHARS`.

**Risk:** character counts do not predict model token usage consistently across languages and structured content.

**Direction:** add a tokenizer/budget interface with a safe character fallback. This is not a blocker for the current local model workflow.

### A-11 — Documentation describes both target and legacy flows without a single current map

**Priority:** P2 — addressed by this PR's documentation set.

**Evidence:** README's product vision correctly distinguishes intended capabilities from current implementation, but its primary architecture/turn diagrams still describe an earlier narrative-extraction flow and do not show the native mechanics path, runtime factory or combat/effect/clock subsystems. The older functional audit contains historical findings that have since been corrected (for example the long-held native-turn connection) and should remain historical rather than be silently rewritten.

**Direction:** use the current architecture map, ownership map and this audit as the present snapshot. Update README diagrams in a later focused docs change if needed; preserve historical audit findings as history.

## 3. Positive foundations to preserve

- Modular monolith and local-first single-player scope.
- Explicit `CampaignScope` and campaign-scoped repositories.
- SQLite migrations and cross-campaign integrity safeguards.
- A typed operation model with parsing separated from application.
- `WorldService` working-copy application and rollback-oriented tests.
- Native turn planning outside the write transaction, followed by fresh-context validation and short `BEGIN IMMEDIATE` commit.
- SillyTavern external turn IDs, versioning, idempotency and snapshot reconciliation.
- A ruleset-specific deterministic package with tests independent from FastAPI/SQLite/LLM.
- Explicit encounter, persistent-effect and campaign-clock services.
- Python and JavaScript tests covering the main existing workflows.

## 4. Priority summary

| Priority | Findings | Meaning |
|---|---|---|
| P1 | A-01, A-02, A-03, A-07 | Must be resolved or explicitly bounded before treating the next major feature set as a cohesive playable AI-DM product. |
| P1/P2 | A-04 | Add a transaction abstraction where it reduces real risk; not a prerequisite for every feature. |
| P2 | A-05, A-06, A-08, A-09, A-11 | Consolidate progressively; some are acceptable constraints for the local MVP. |
| P3 | A-10 | Optimization, not a blocker. |

## 5. Verification and confidence

### Verified by source inspection

- Default branch commit and repository tree.
- CI job definitions and declared commands.
- Runtime factory, request middleware/proxies, turn services, integration service, combat/effect/clock services, repositories and representative models.
- Migration version constant (`CURRENT_VERSION = 20`).
- Presence of 75 Python test files and 2 JavaScript test files.

### Not verified dynamically

- No Python test suite was executed during this audit.
- No Ruff or JavaScript test command was executed.
- No live Ollama request was performed.
- No multi-process contention test was performed.
- No full migration replay against real user database copies was performed.
- Not every route, repository, migration, SQL trigger or test case was read line-by-line.

CI currently defines:
- `python -m pytest -m "not real_llm"` on Python 3.12;
- `ruff check .`;
- `npm run test:js` on Node 20.

A CI run must be inspected separately. The existence of these jobs is not evidence that they passed on this commit.
