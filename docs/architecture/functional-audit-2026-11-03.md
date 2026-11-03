# Functional audit — baseline

**Date:** 2026-11-03  
**Repository:** `IvanVM04/Campaign-Manager`  
**Audited baseline:** default branch `main`, source files inspected through GitHub.  
**Status:** first-pass static audit; no claim that the test suite has been executed.

## Executive summary

The repository is a useful persistent campaign-state backend with a narrative LLM path and a SillyTavern integration. It is not yet a complete D&D 5e game engine or a rules-adjudicating AI Dungeon Master.

The most important product-level gap is the current internal turn order:

```text
player input
  -> DMService generates narrative
  -> LLMWorldExtractor infers operations from that narrative
  -> WorldService applies operations
  -> persistence
```

There is no deterministic rules-resolution stage between the player's declared action and the narrative being treated as resolved. As a result, the LLM can narrate a hit, failed check, damage, spell effect or other outcome before any verified 2014 rules calculation has taken place. This path must not be treated as authoritative D&D adjudication.

## Functional inventory

| Area | Current evidence | Assessment |
|---|---|---|
| Campaigns and sessions | Campaign/session models, repositories, services and API endpoints | Implemented foundation |
| World entities and relationships | `WorldState`, typed operations, applier and repositories | Implemented foundation |
| Items and item instances | Typed operations, repositories and persistence | Implemented foundation; not a full equipment rules model |
| Resources | Generic resource balances and operations | Implemented generic system; not spell slots/class resources by rules |
| Player character record | `CharacterState` with level, class label, HP, AC, six abilities and proficiency bonus | Partial mechanical record, not a complete character sheet |
| Character creation | `CharacterCreate` and `CharacterCreationService` | Minimal/manual creation; no rules-driven builder |
| Character HP changes | `ChangeCharacterHpOperation`, parser, applier and service | Basic HP mutation only; no damage/healing rules, death saves, unconsciousness or conditions |
| Dice/checks/saving throws | No dedicated rules-resolution module found in the inspected architecture | Not implemented / needs full repository-wide confirmation |
| Attacks, initiative and combat | No dedicated encounter/combat domain found in the inspected architecture | Not implemented / needs full repository-wide confirmation |
| Spells and spell slots | Generic resources exist, but no verified spellcasting model was found in inspected files | Not implemented as a D&D rules subsystem |
| Narrative DM | `DMService` builds a prompt and calls an `LLMProvider` | Implemented narrative generation, not rules adjudication |
| Structured world extraction | `LLMWorldExtractor` plus `OperationParser` | Implemented probabilistic extraction with typed parsing and application validation |
| Context and memory | `MemorySearchService`, `ContextExpander`, `ContextRanker`, `ContextBuilder` | Implemented retrieval foundation; current budget is characters, not model tokens |
| SillyTavern | Context and turn endpoints, external turn IDs, versioning and snapshots | Substantial integration foundation |
| Standalone web application | FastAPI API exists; no standalone player-facing web client established by this audit | API exists; product UI remains to be built |
| VTT | No tactical map/token subsystem found in inspected architecture | Out of current scope |

## Findings

### F-01 — Narrative is currently generated before mechanical resolution

**Severity:** Critical product correctness gap  
**Evidence:** `services/turn_resolution_service.py` calls `DMService.generate()`, then passes the generated narrative to `LLMWorldExtractor.extract()`, then applies the extracted operations through `WorldService`.

This means the narrative is currently upstream of state extraction and there is no rules engine to verify mechanical outcomes. The extractor may translate generated prose into HP/world mutations, but that is not equivalent to resolving an action under D&D rules.

**Required direction:** introduce a staged turn pipeline: interpret declared intent; adjudicate circumstances; request deterministic rules resolution where required; validate proposed world consequences; persist; then narrate the committed result. Do not let a narrative extraction step stand in for a rules engine.

### F-02 — The default DM prompt imposes a tone that can conflict with campaign configuration

**Severity:** Medium  
**Evidence:** `services/dm_service.py` hard-codes a serious/dark/epic tone while `CampaignCreate` and `CampaignState` support a campaign-specific `tone`.

**Change in this branch:** remove the fixed style and instruct the narrator to respect the campaign's configured tone. Add a regression test.

### F-03 — The current character model is a minimal stat container, not a D&D character sheet

**Severity:** High for the intended product  
**Evidence:** `models/character_state.py` stores level, a free-text class name, HP, AC, six ability scores and proficiency bonus. `models/schemas.py::CharacterCreate` accepts most mechanical values directly from the caller.

Missing as explicit typed concepts include at least ability/skill/save proficiencies, hit dice, speed, size, race/species, background, class features, equipment/load, attacks, spellcasting, conditions, death saves and level-up choices. This list is a product-domain gap, not a claim that every item is required in the first playable slice.

The schema permits a caller to provide level and proficiency bonus independently. This can create an internally inconsistent D&D character. Do not add a derived-value rule until the exact 2014 source and intended multiclass/character-level semantics are documented and tested.

**Required direction:** replace ad-hoc growth of this dataclass with a versioned character domain model and rules-derived values, introduced incrementally with verified references.

### F-04 — HP mutation is deliberately much narrower than combat resolution

**Severity:** High for combat readiness  
**Evidence:** `services/character_service.py::change_hp` adds a signed amount and clamps the result between zero and max HP. The operation does not encode the cause or distinguish attack damage, falling damage, healing, temporary HP, massive damage, unconsciousness, death saves or conditions.

This is acceptable as a primitive state mutation in the current backend, but it must not be described as a combat engine.

### F-05 — Internal turn execution holds a database connection while LLM work runs

**Severity:** High operational risk; concurrency behaviour needs a targeted test  
**Evidence:** `services/campaign_turn_service.py::_play_turn_locked` enters `get_conn()`, loads campaign/turn context and invokes `TurnResolutionService.resolve_turn()` before leaving the connection context. The resolver calls the DM provider and extractor provider.

This keeps a SQLite connection and the read transaction/snapshot alive during potentially slow model inference. Depending on concurrent writes and SQLite journal mode, this can increase WAL retention and make transaction-upgrade contention more likely.

**Required direction:** separate the expensive LLM planning phase from the short authoritative persistence transaction. Re-read/validate the expected campaign version inside the write transaction before applying the plan. Add concurrent multi-campaign and failure-injection tests before changing transaction boundaries.

### F-06 — Runtime cache is process-local and has no eviction policy

**Severity:** Medium; partly documented limitation  
**Evidence:** `services/campaign_runtime.py::CampaignRuntimeFactory` stores runtimes in `self._runtimes` keyed by campaign ID and exposes manual `invalidate()`, but no eviction/close policy is visible. The README already documents the single-process/single-worker constraint.

**Required direction:** retain the single-process constraint for now; later add explicit lifecycle handling and cache invalidation on campaign deletion/configuration changes before considering multiple workers.

### F-07 — Context budget is character-based

**Severity:** Medium  
**Evidence:** `services/context_builder.py` names its limits `DEFAULT_MAX_CONTEXT_CHARS` and `DEFAULT_MAX_RECENT_TURNS_CHARS`, and validates character counts.

Character counts are not a reliable token budget across languages, structured data and different model tokenizers.

**Required direction:** introduce a token-budget abstraction behind a provider/model-aware tokenizer interface. Keep the current character limit as a documented fallback until token counting is available.

### F-08 — Provider configuration is embedded in the runtime factory/provider defaults

**Severity:** Medium  
**Evidence:** `services/campaign_runtime.py` constructs `OllamaProvider()` directly. `services/ollama_provider.py` has defaults for URL, model and timeout.

The provider abstraction is a good seam, but configuration is not yet visibly centralized in application settings.

**Required direction:** move provider URL/model/timeout and model-role selection to validated settings; avoid making rules correctness depend on a specific model.

### F-09 — Persistence and domain boundaries are a useful base but not yet ports-and-adapters

**Severity:** Medium architectural debt  
**Evidence:** repositories exist, but services import concrete repository/service classes and `database.py` exposes connection helpers. Runtime composition is centralized in `CampaignRuntimeFactory`.

**Required direction:** incrementally introduce application ports/Protocols and a Unit of Work. Do not rewrite the repository or split it into microservices.

## Confirmed positive foundations

- Typed dataclass operations are parsed separately from semantic application.
- `OperationParser` explicitly distinguishes structural parsing from semantic validation.
- `WorldApplier` / `WorldService` provide a validation/application boundary.
- Character/world operations are separated.
- Turn records, external turn IDs, versioning and snapshots provide a foundation for retries and SillyTavern regeneration.
- Tests exist for character creation, operation parsing/application, turn processing and integration behaviour.
- The runtime factory composes a per-campaign service graph and the README documents the current single-process constraint.

## Changes made in this audit branch

1. The default DM prompt no longer forces a dark/epic tone over campaign settings.
2. The default DM prompt now explicitly defers dice/check/attack/damage/spell/condition outcomes until a rules engine confirms them. This is a guardrail, not a substitute for deterministic enforcement.
3. A regression test was added for the prompt contract.

## Verification limits

- This is a static source audit of the files listed above, not a complete dynamic audit.
- The test suite has **not** been executed in this environment. The new regression test is added but remains unverified by execution.
- No D&D rule has been implemented or certified by this document.
- The absence of a module in the inspected paths is recorded as “not found / needs full repository-wide confirmation” rather than proof that no related code exists anywhere.

## Recommended next audit slice

1. Inspect all schemas, migrations and repositories for character/world invariants and campaign scoping.
2. Trace the complete SillyTavern regeneration transaction, including failure after snapshot restore and commit failure.
3. Inspect API error mapping, authentication/authorization and runtime lifecycle.
4. Inventory all tests and CI commands; execute the deterministic suite in a local checkout.
5. Produce the target domain map for a minimal playable D&D 5e 2014 slice before implementing any rules.


### F-10 — SillyTavern rollback restored a reference, not the shared in-memory state

**Severity:** High — corrected in the audit branch, regression test added

**Evidence:** `SillyTavernIntegrationService.process_turn()` originally saved `previous_world = self.world_service.get_world()`. `WorldService.apply_turn_operations()` works on a deep-copied working state, but after successful application it publishes the new collections onto the original `WorldState` instance to preserve shared object identity. If saving the `TurnRecord` or the enclosing SQLite commit then failed, assigning `self.world_service.world = previous_world` restored the same already-mutated object, not its previous contents.

**Change in this branch:** take a deep snapshot of the in-memory world before applying the turn and restore all world collections in-place on transaction failure. The helper preserves the original `WorldState` identity so existing `TurnContext` references remain valid. A regression test forces `TurnRepository.save_turn()` to fail after world application and checks that the shared world is restored.

**Verification status:** source change and test are committed to the audit branch. The test has not been executed here, so runtime verification remains pending.

### Additional transaction and concurrency observations

- The SillyTavern integration deliberately completes LLM extraction before opening its authoritative `BEGIN IMMEDIATE` write transaction. This avoids holding SQLite's write lock during model inference.
- It then rechecks the external turn version inside the write transaction, restores the previous snapshot for regeneration, applies operations, and saves the turn. This is a sound foundation for idempotent retries.
- The per-campaign `TurnExecutionLock` is a process-local `threading.RLock`. It serializes calls sharing that lock instance in one Python process; it does not coordinate multiple worker processes or separate application instances. The documented single-process deployment restriction is therefore important.
- `CampaignTurnService` currently differs from the SillyTavern path: it opens `get_conn()` before calling `TurnResolutionService.resolve_turn()`, which includes LLM generation and extraction. This keeps a SQLite connection/transaction open during inference. It should be redesigned separately using a plan-then-validate-and-commit workflow, with campaign version checks to reject stale plans.
- Existing integration tests already cover successful regeneration, extraction against the pre-regeneration snapshot, failed regeneration rollback, operation failure rollback, idempotent retries and turn version sequencing. This is stronger coverage than a first-pass inventory alone suggested; future work should extend it with commit-failure and cross-process contention tests rather than duplicate existing tests.


### F-11 — Campaign-scoped endpoints have no user authentication (intentional for local single-player)

**Severity:** Not a defect for the current product scope; becomes high priority only if remote access is introduced.

**Evidence:** `app.py::bind_campaign_runtime` accepts `X-Campaign-Id` and resolves a runtime. It does not authenticate a principal or check campaign membership/ownership. Campaign listing and creation are explicitly exempt from campaign selection and likewise have no user identity. Repository scoping by `campaign_id` is a valuable data-isolation layer, but it is not authorization.

**Decision:** the product is single-player and local-first. There is one local user, not a roster of accounts or campaign members. The documented server commands bind to loopback (`127.0.0.1`), so a user/account system is unnecessary for the MVP. Keep the loopback bind. If remote access is later requested, add authentication before changing the bind address or exposing the API through a tunnel/reverse proxy. Do not implement multi-user ownership/roles unless the product scope changes.

### F-12 — Campaign update schema accepted blank required values

**Severity:** Low/medium data quality issue; corrected in the audit branch.

**Evidence:** `CampaignCreate` trims and rejects blank `name` and `system`, but `CampaignUpdate` previously allowed empty or whitespace-only values and passed them to the repository.

**Change in this branch:** `CampaignUpdate` now applies the same nonblank/trim validation to optional `name` and `system`, and normalizes optional `tone` and `summary`. Regression tests cover blank values and whitespace normalization.

**Verification status:** code and tests committed; execution is pending.

### F-13 — Campaign isolation has meaningful database safeguards

**Severity:** Positive finding / retain these safeguards.

**Evidence:** `CampaignScope` rejects invalid IDs; repositories generally include `campaign_id` in lookups and mutations; migration 012 adds campaign ownership and cross-campaign reference constraints; foreign keys are enabled for connections; tests cover runtime isolation and snapshot isolation.

This does not replace API authorization, but it is a solid data-layer boundary. Continue adding tests for every new repository method to ensure campaign scope cannot be omitted.

### F-14 — API validation and error mapping are inconsistent

**Severity:** Medium.

**Evidence:** several routes convert broad exceptions into HTTP 400 or return raw exception text, while other routes correctly distinguish validation (422), conflict (409) and internal errors (500). This can leak implementation details and mislead API clients.

**Required direction:** define application exceptions (not found, conflict, invalid command, provider unavailable, persistence failure), map them centrally to stable API error responses, and log diagnostic details server-side. Avoid returning raw internal exception messages to clients.

### F-15 — Health endpoint is liveness-only

**Severity:** Low for local mode; operational gap for hosted mode.

**Evidence:** `/health` returns `{"ok": true}` without checking database readiness. This is adequate as a process liveness probe but should not be used as a readiness signal.

**Required direction:** retain liveness and add a separate readiness endpoint that verifies required local dependencies such as SQLite. Do not require Ollama to be available for the API to serve campaign reads or health checks.

### F-16 — Development tooling is split between project metadata and CI

**Severity:** Low.

**Evidence:** `pyproject.toml` declares the development test dependencies (`pytest`, `httpx2>=2.5`); `requirements.txt` intentionally contains runtime dependencies only; `.github/workflows/tests.yml` installs Ruff separately for its lint job and runs JavaScript tests with `npm run test:js`. The README's development-tools bullet incorrectly says `httpx` although the install command and CI use `httpx2`.

**Change in this branch:** corrected the README label to `httpx2`. There is no evidence that the runtime requirements file should include test/lint tools. A lockfile may improve reproducibility later, but it is not a blocker for the local single-player MVP.


### Product-scope clarification — single-player, local-first

The intended application is single-player: one person manages and plays their own campaigns. Multiple campaigns in one local installation remain supported and must stay isolated, but multiplayer accounts, campaign membership and role-based access are not MVP requirements.

The documented launch commands bind Uvicorn to `127.0.0.1`. Therefore lack of user authentication is not classified as a current product defect. Keep the loopback bind and treat remote exposure as a separate future security project. The campaign ID remains a selector and must never be mistaken for authentication if that deployment boundary changes.

### CI inventory

The repository's `.github/workflows/tests.yml` defines three jobs:
- Python tests on Python 3.12, installing `requirements.txt` plus `pytest` and `httpx2>=2.5`, then running `python -m pytest -m "not real_llm"`.
- Ruff linting via `ruff check .`.
- JavaScript tests via `npm run test:js` on Node 20.

The README's CI description should mention all three jobs, not only pytest and Ruff. The workflow file was inspected, but no run for the current audit branch was available through the inspected GitHub Actions interface; the suite is not claimed as executed.
