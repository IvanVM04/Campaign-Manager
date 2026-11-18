# Campaign Manager — current architecture map

**Verified:** 2026-11-18  
**Repository:** `IvanVM04/Campaign-Manager`  
**Documentation baseline:** `main` at `4a3a2549bb0bb1bc38ec0e6f456ac6d5ccef24d1` (PR #257, documentation only).  
**Code baseline:** `f4fb3914ebab4579118863796e6f6d4b7183d0cf` (PR #255).  
**Database schema:** version 34 (`CURRENT_VERSION = 34`).  
**Purpose:** current source-linked navigation for maintainers. Product requirements describe the target; this map describes the code that exists at the verified code baseline.

> Read [product requirements](../product/product-requirements-2026-11-18.md) for approved product direction and [the quality roadmap](../quality/quality-roadmap-2026-11-18.md) for ordered validation work. The new UI, multi-character control, NPC delegation, custom rules imports, configurable confidence threshold and full campaign import/export are requirements, not current implementation claims.

## 1. System shape

Campaign Manager is a **local-first, single-user, single-process modular monolith**. One person can maintain multiple campaigns. The current runtime has one active player character per campaign context; support for simultaneously controlling several player characters is a product requirement for future work, not a capability to infer from the single active-character pointer.

- FastAPI exposes HTTP transport contracts under `api/routers/`.
- `bootstrap/campaign_runtime.py` composes one campaign runtime per selected campaign.
- SQLite is the persistent store; the migration registry currently ends at version 34.
- Campaign-owned in-memory `WorldState` is used by domain workflows and guarded by a campaign-local `TurnExecutionLock`.
- Ollama is the production LLM adapter; fake providers keep deterministic tests independent of network/model availability.
- SillyTavern is an external client adapter. There is no first-party web UI yet.
- Deployment remains one process/one Uvicorn worker bound to loopback by the documented startup path.

Do not introduce multiple workers, distributed locks, microservices, a vector database or remote exposure without a separately evidenced product and security decision.

## 2. Authority boundaries

| Concern | Authoritative owner | Boundary |
|---|---|---|
| Player intention | Player input, interpreted into `PlayerIntentAnalysis` | LLM interpretation is evidence, not a canonical entity ID or permission. |
| Entity identity and visibility | Deterministic application/context resolvers and visibility policy | Ambiguous or hidden references abstain; prompt text cannot grant access. |
| Mechanics | `rules_engine/dnd5e_2014` and validated mechanics decision flow | LLM may recommend a check/DC within current contract; deterministic code rolls and calculates. |
| Consequence planning | LLM structured proposal | Untrusted typed proposal only; parser/schema allowlists are not authorization. |
| Authorization and mutation | Domain/application services and world appliers | Validate existence, campaign scope, ownership, permission, resources and revision before mutation. |
| Persistence | Repositories through caller-owned transactions | The LLM never writes SQLite. |
| Narration | Native `DMService` or SillyTavern generation after commit | Narration is a projection of committed evidence; regeneration cannot replay consequences. |

No typed NPC delegation/permission contract exists yet. The product requirement for player/DM NPC-control requests must be implemented as a backend/domain contract before UI controls are added.

## 3. Capability packages

The application service layer has eight capability packages:

| Package | Current ownership |
|---|---|
| `services/campaign` | Campaign/session state, fictional clock, persistent effects, effective condition projection. |
| `services/characters` | Character creation/state, character sheet query and rest use cases. The current creation path is not a complete 5e character builder. |
| `services/combat` | Encounter, attack, equipment and combat workflow orchestration; deterministic mechanics remain in rules_engine. |
| `services/context` | Search, expansion, ranking, proposal-context selection, entity and conversation reference resolution. |
| `services/llm_world` | Structured world-consequence proposal prompts, parsing, operation registry and proposal validation. |
| `services/providers` | LLM provider port, Ollama adapter, role settings and fake provider. |
| `services/turns` | Intent interpretation, mechanics adjudication, durable turn coordination, challenges, commit, recovery and narration. |
| `services/world` | Validated world-operation application, world state publication, query/read models and player visibility policy. |

Composition remains centralized in `bootstrap/campaign_runtime.py`. API routers are transport adapters; they must not become composition roots or own domain transactions.

## 4. Current turn pipelines

### Native API

```text
POST /turn
  -> DurableNativeTurnService
      -> durable request claim / idempotency / lease
      -> consistent campaign context + revision + same-conversation history
      -> IntentInterpreter -> validated PlayerIntentAnalysis
      -> deterministic canonical reference resolution
      -> MechanicsAdjudicator (only for actionable, non-clarification intent)
      -> deterministic 2014 mechanics and dice resolution
      -> bounded structured world proposal
      -> semantic/domain validation
      -> short atomic prepared commit
  -> DMService narration from committed evidence
  -> durable completed result
```

Native continuation routes are `POST /turn/roll` and `POST /turn/clarification`. The durable resolution record stores intent/evidence and challenge state; retries and challenge submissions do not start a new player action.

### SillyTavern

```text
POST /integration/turn/resolve
  -> durable resolution + consequence commit or awaiting_input
  -> safe campaign/session/character/context projection
SillyTavern generates narrative from returned committed evidence
POST /integration/turn/complete
  -> persist narrative version only
```

The extension carries a stable external turn identity and `conversation_id`. Clarification and manual-roll submissions are linked to the original action. `GET /integration/turn/{external_turn_id}` and the challenge-state routes support recovery after extension/browser restart. Swipes create transcript/narrative versions against the same committed resolution; they do not rerun mechanics or world operations. The narrative-first `POST /integration/turn` route is retired.

### Durable lifecycle states

`accepted → planning → awaiting_input | prepared → committed → narration_pending → completed`; invalid or unauthorized work may become `rejected`. Provider work stays outside write transactions. Campaign revision and lease fencing protect the prepared commit. See [the current turn lifecycle contract](turn-resolution-lifecycle.md).

## 5. Shared language-understanding pipeline

The production path uses distinct responsibilities:

1. `IntentInterpreter` produces one coherent `PlayerIntentAnalysis` v2 from literal player evidence and bounded same-chat history.
2. Model schema and literal evidence are validated; deterministic resolvers attach canonical IDs only when a visible, active, sufficiently unique entity matches.
3. `MechanicsAdjudicator` receives only the validated actionable active step and compact mechanical context; it returns a structured decision, not a dice result.
4. The rules engine/application resolves supported mechanics deterministically.
5. `LLMWorldExtractor.propose()` receives the same validated analysis, trusted references, bounded detached projection and confirmed mechanics; it does not reinterpret the raw utterance.
6. World/domain validation decides which operations are accepted.

The semantic interpretation is not a collection of independent per-slot LLM calls. Action frames, directed relation claims, modality, polarity, attribution and discourse signals form one semantic unit. Deterministic normalizers are conservative and should not improve recall by creating speculative entity identity or persistent facts.

## 6. Context, knowledge and visibility

- `ContextBuilder` and `ProposalContextSelector` perform deterministic retrieval, expansion, ranking and dependency-aware selection.
- The selected `WorldContextProjection` is detached from mutable runtime world state and bounded separately from the complete rendered prompt.
- The active character and current location are mandatory context.
- Event visibility/epistemic policy is enforced before player-facing search and context selection; secret/GM-only events are excluded.
- Entity descriptions, arbitrary free-text notes and every NPC fact do not yet have a complete per-assertion knowledge/provenance model.
- There is no authenticated GM read API. Never add a query/header bypass for hidden data.
- Current read surfaces include `GET /world`, paginated `GET /world/entities`, world collection routes, memory search/context and `GET /export`. The export endpoint is a player-safe memory/world projection, **not** a full portable campaign backup/import format.

The planned world compendium, inline entity previews, explicit player-selected context entities and per-NPC/per-field visibility settings belong to product v0.2 and are not yet implemented.

## 7. Rules and dice

The included engine targets D&D 5e 2014/SRD 5.1 and implements a deterministic subset: d20 rolls, ability/skill checks, saving throws, advantage/disadvantage, proficiency, selected weapon/natural attacks, damage/HP/death-track mechanics, conditions, selected movement/reactions and rests/effects. It is not a complete 5e rules engine, full character builder, spellcasting system or all-class progression system.

Current turn APIs support `dice_mode=automatic|manual`. Automatic rolls are generated by the backend. Manual d20 results are persisted against durable turn challenges and validated on submission. Fine-grained campaign/actor/check-type roll policies and importable custom rules modules are future product requirements. D&D 2024 remains a separate, non-priority future ruleset.

## 8. Persistence and API boundaries

- `migrations.py` defines ordered migrations 001–034 and `CURRENT_VERSION = 34`.
- Migrations are forward-only; update the registry and migration tests together.
- API campaign selection uses `X-Campaign-Id`; it is not authentication.
- Campaign-scoped calls require explicit campaign selection; no default-campaign fallback.
- The API defaults to loopback and the runtime assumes one process/worker.
- `/export` is not campaign import/export. Full portable packages are a future capability.
- API errors use the stable `code` / `detail` response contract with `X-Request-ID`.

## 9. Quality and acceptance boundary

At the PR #255 code baseline, the documented deterministic CI result is 2,042 passed, 22 deselected (opt-in real-LLM), 85.14% combined coverage, with Ruff, JavaScript, required-scope and repository-wide Pyright, CI summary and CodeQL passing. These checks do not prove live model quality or a real SillyTavern session.

The current next gates are:
- Re-run semantic predicate, discourse/callback/topic-boundary and 14-case compound-intent live holdouts on the current configured Ollama model.
- Record reproducible model digest/settings/latency and privacy-safe metrics.
- Perform the manual SillyTavern checklist; do not infer it from unit tests or Ollama-only probes.
- Continue the first playable vertical slice only after the quality baseline and critical recovery/visibility risks are understood.

## 10. Current product gaps (not implemented claims)

The product requirements v0.2 includes future requirements for multi-PJ simultaneous control, approved NPC delegation, configurable uncertainty thresholds with resumable partial-turn checkpoints, Simplified/Advanced UI modes, contextual field help, a first-party UI, world compendium and entity links, explicit entity inclusion in turn context, configurable NPC-stat visibility, fine-grained dice policy, custom rules modules, multi-language UI/campaign settings, and full campaign import/export. Treat these as requirements for design and implementation planning, not existing capabilities.

## References

- [Product requirements](../product/product-requirements-2026-11-18.md)
- [Current quality roadmap](../quality/quality-roadmap-2026-11-18.md)
- [Current architecture audit](architecture-audit-2026-11-18.md)
- [Change-impact map](change-impact-map-2026-11-18.md)
- [Migration catalogue](migration-catalog-2026-11-12.md)
- [Turn pipeline contract](turn-pipeline-compatibility.md)
- [Durable SillyTavern adapter](sillytavern-durable-turn-adapter.md)
- [Manual SillyTavern smoke test](../sillytavern-smoke-test.md)
