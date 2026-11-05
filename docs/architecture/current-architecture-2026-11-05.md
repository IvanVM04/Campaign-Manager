# Current architecture snapshot

**Date:** 2026-11-05  
**Repository:** `IvanVM04/Campaign-Manager`  
**Audited base:** `main` at `5c92be47a3fc71a0121e7449ed4f70dcf814141c`  
**Method:** static inspection of the tracked repository tree, key services, routers, tests and architecture docs. Not a runtime certification.

## 1. System shape

Campaign Manager is a **local-first, single-player, single-process modular monolith**. The architecture is layered and has some domain seams; package boundaries are not yet enforced consistently.

```text
Native client / SillyTavern extension
                |
                v
       FastAPI capability routers
                |
        X-Campaign-Id middleware
                |
      request-scoped CampaignRuntime
                |
        application services
       /        |          \
   turns     campaign/world  combat/effects/clock
       |        |          |
 LLM providers |     deterministic rules engine
       |        |     rules_engine/dnd5e_2014
       +--------+----------+
                |
        SQLite repositories
                |
       migrations + revisions
```

Keep this deployment shape. The current runtime cache, in-memory world and lock are process-local; running multiple workers is not supported.

## 2. Main packages

| Package | Current responsibility |
|---|---|
| `api/routers/` | HTTP transport adapters split by capability |
| `api/runtime_context.py` | Request-local runtime binding and compatibility proxies |
| `services/campaign_runtime.py` | Per-campaign composition root/cache |
| `services/` | Application orchestration and integrations; several classes are oversized |
| `models/` | State, schemas, operation results and lifecycle records |
| `operations/` | Typed world/character mutation commands |
| `repositories/` | Campaign-scoped SQLite persistence |
| `rules_engine/dnd5e_2014/` | Deterministic rules subset, isolated from HTTP/SQLite/LLM |
| `integrations/sillytavern/` | SillyTavern extension, state and tests |
| `migrations.py` | Ordered schema evolution (current migration 028) |
| `tests/` | Python service/API/rules/integration tests and JavaScript extension tests |

## 3. Request and runtime composition

`app.py` mounts capability routers and middleware. Every campaign-scoped request supplies `X-Campaign-Id`; middleware resolves a `CampaignRuntime` and binds it through a `ContextVar`. Campaign listing/creation and health/docs endpoints are exempt.

The runtime owns a campaign-scoped `WorldService`, repositories, context/memory services, turn services, combat/effect services, one `TurnExecutionLock` and an `OllamaProvider` created with defaults. `CampaignRuntimeFactory` caches runtimes in a process-local dictionary and offers manual invalidation, but no eviction policy.

`app.py` is now small relative to the original architecture: routers are extracted. It still retains legacy factory functions and imports compatibility names. `api/runtime_context.py` retains service proxies for older tests/callers.

## 4. Current turn lifecycle

### Native API

`POST /turn` delegates to `DurableNativeTurnService.play_turn()`. The service captures a consistent context/history and campaign revision, creates or retrieves an idempotent resolution, claims planning with a lease, and calls `TurnResolutionService.prepare_turn()` outside the write transaction. The plan contains structured operations and optional mechanics evidence. A short `BEGIN IMMEDIATE` transaction checks the captured revision/context, applies operations, records outcomes and resulting revision, and transitions to narration-pending. Native narration is then generated from the committed resolution and the transcript/completion transition is persisted.

Manual rolls and clarifications are stored in the durable resolution record and resumed against the original request identity. The older `CampaignTurnService` remains in the runtime graph and has a separate in-memory manual-roll path; it is not the route used by current `POST /turn`.

### SillyTavern

The current extension flow is:

1. `POST /integration/turn/resolve` with external turn identity and player input.
2. The same durable coordinator plans and commits consequences before prose generation.
3. The backend returns committed resolution evidence and context.
4. SillyTavern generates the narrative.
5. `POST /integration/turn/complete` stores the narrative version against the same external turn.
6. Swipe/regeneration changes narrative versions only; committed consequences are not replayed.
7. Clarification/manual-roll challenges resume the same durable resolution.

The old `POST /integration/turn` endpoint and `SillyTavernIntegrationService.process_turn()` remain for legacy clients. They use narrative extraction and snapshot reconciliation semantics. Do not describe them as equivalent to the active durable flow.

## 5. State ownership and persistence

- SQLite is the durable source of truth.
- Repositories generally carry explicit campaign scope and accept a caller-owned connection for atomic use cases.
- `campaign_state_versions` provides a monotonic campaign mutation revision via triggers. Prepared plans are rejected when the revision/context changes.
- `turn_resolutions` stores idempotency identity/fingerprint, lifecycle, proposal, adjudication/mechanics, operation evidence, lease metadata and context/result revisions.
- `turns` remains the historical narrative/transcript projection; it is not reused as the in-flight resolution record.
- Player-character mechanics are canonical in `CharacterState`; encounter values synchronized with them are projections and must be changed atomically.
- Persistent effects own identity/duration/lifecycle; effective conditions are derived.
- Item instance ownership remains canonical in `owner_id`; equipment is a projection.

The transaction helper makes ownership explicit in selected workflows. A universal Unit of Work is not present and should not be introduced mechanically.

## 6. Rules engine status

The `dnd5e_2014` package is deterministic and independent from FastAPI, SQLite and model providers. Implemented areas include dice/d20, ability checks, skill checks, saving throws, initiative, attack/damage primitives, conditions/exhaustion, selected weapons and encounter mechanics.

It remains a **partial** 2014 rules implementation. Character creation/progression, spellcasting, complete action economy, full movement/range/cover and many class/feature interactions are not complete. The adjudicator can propose whether a supported check is required and a DC; deterministic code resolves the accepted roll. Do not claim fully deterministic adjudication or complete D&D 5e support.

## 7. External and operational boundaries

- SillyTavern is the current player-facing interface; no standalone web UI exists.
- The app is single-player/local-first and defaults to loopback. `X-Campaign-Id` is a campaign selector, not authentication.
- One process/worker is the supported deployment. In-process locks and world caches are not distributed.
- Ollama providers are composed from validated startup settings. Narrative, extraction and mechanics roles may use separate models and timeouts; all default to the existing `gemma4:26b` / 120-second configuration. The per-campaign runtime cache remains process-local and has manual invalidation only.
- `/health` is liveness; `/ready` checks SQLite readiness.

## 8. Known architectural debt

See [audit and refactoring plan](audit-and-refactor-plan-2026-11-05.md). The highest-value issues are:
1. `DurableNativeTurnService` combines several lifecycle/adapter/challenge responsibilities.
2. Legacy and current SillyTavern turn paths coexist.
3. Domain ownership/dependency boundaries remain layer-first and convention-based.
4. Runtime/provider lifecycle and configuration are implicit.
5. API error mapping is centrally supported but still inconsistent at individual routes.
6. Several large modules concentrate unrelated policy and persistence behavior.

## 9. Verification limits

This snapshot is based on static inspection. It does not certify a local full-suite run, real Ollama generation, multi-process correctness, migration replay against user DB copies, or a live SillyTavern browser session. The manual checklist remains required before treating the campaign as playable end-to-end.
