# Architecture and documentation audit — 2026-11-18

**Repository:** `IvanVM04/Campaign-Manager`  
**Verified main:** `4a3a2549bb0bb1bc38ec0e6f456ac6d5ccef24d1` (PR #257 merged; documentation-only change).  
**Code baseline:** `f4fb3914ebab4579118863796e6f6d4b7183d0cf` (PR #255).  
**Schema:** 34.  
**Scope:** architecture, APIs, durable turn lifecycle, rules, context/visibility, package/service guides, tests/CI evidence and the documentation source-of-truth structure.

> This is the current source-verified assessment. Dated PR/audit reports remain historical snapshots. The [product requirements v0.2](../product/product-requirements-2026-11-18.md) describe approved product direction; they do not imply implementation.

## 1. Executive decision

The repository has a coherent **local, single-user, single-process modular monolith** with eight capability service packages, a central composition root, SQLite persistence and a single durable turn-resolution lifecycle. The code is sufficiently modular for the present scope. The main task is not another broad architectural rewrite: it is to preserve the current authority and recovery boundaries, establish live-model/integration evidence, and build product breadth in deliberate vertical slices.

The documentation audit found important active-page drift. Several current indexes still pointed to 12 November maps/audits, a proposed PR #28 lifecycle document was still indexed as the active contract, the 2014 rules page incorrectly said manual rolls were in-memory and lost on restart, and an LLM context page still described a retired legacy renderer. The live docs have been updated or superseded in this documentation pass. Old dated reports are retained with supersession notices rather than rewritten.

## 2. Verified repository baseline

| Area | Verified state |
|---|---|
| Main documentation head | `4a3a2549bb0bb1bc38ec0e6f456ac6d5ccef24d1`, PR #257 |
| Last code change in the reviewed baseline | PR #255, `f4fb3914ebab4579118863796e6f6d4b7183d0cf` |
| Database schema | `CURRENT_VERSION = 34`; registry contains migrations 001–034 |
| Service packages | campaign, characters, combat, context, llm_world, providers, turns, world |
| Composition | `bootstrap/campaign_runtime.py` |
| Persistence | SQLite, versioned forward-only migrations |
| Turn lifecycle | durable, shared native/SillyTavern application lifecycle |
| LLM provider | Ollama adapter plus deterministic fake provider |
| External client | SillyTavern adapter; no first-party UI exists |
| Process model | one Python process/one Uvicorn worker; campaign-local in-process locks |
| Rules | deterministic D&D 5e 2014 subset, not a complete rules engine |

### CI evidence boundary

The PR #255 quality record reports 2,042 deterministic tests passed, 22 opt-in real-LLM tests deselected, 85.14% combined coverage, Ruff, JavaScript tests, required and repository-wide Pyright, CI summary and both CodeQL analyses passing. That is the latest recorded source-code CI baseline in the current quality roadmap. PRs #256 and #257 changed documentation only.

This result does **not** certify current Ollama semantic quality, and does **not** mean the manual SillyTavern checklist has passed. Those are distinct acceptance gates.

## 3. Current architecture findings

### 3.1 Sound boundaries to preserve

- The application remains a modular monolith; capability packages have explicit ownership and the dependency matrix is enforced by architecture tests.
- API routers are transport adapters. Bootstrap owns runtime composition.
- LLM output is untrusted. It can return semantic analysis and typed proposals, but canonical IDs, visibility, permissions, mechanics and persistence are assigned/validated by deterministic application code.
- The production language pipeline separates intent interpretation, mechanics adjudication, consequence proposal, domain validation and narration.
- The structured proposal path receives one bounded, detached world projection. It must not query SQLite directly or import the context package.
- The durable turn coordinator persists request identity, conversation scope, intent evidence, challenge state, proposal/mechanics evidence and commit state.
- Campaign revision checks and planning leases fence stale workers. Provider calls and narration remain outside short write transactions.
- Consequences are committed before narration. Narrative retry/regeneration must not replay mechanics or world mutations.
- Player-facing visibility filters run before search/context and fail closed for GM-only/secret events.
- SQLite schema evolution is migration-owned; historical migration bodies remain in chronological order.

### 3.2 Current state and known limits

1. **Characters:** campaign state exposes one active-character pointer. Multiple character records may exist, but simultaneous control of a configurable group of PJ is not implemented.
2. **NPC authority:** DM controls non-delegated NPCs in the product model, but there is no typed, auditable approval/delegation model in the current domain/API.
3. **Clarification:** durable clarification and pending-intent correction flows exist. A configurable, calibrated uncertainty threshold and a general partial multi-step checkpoint that preserves arbitrary resolved steps/slots are not yet a product-level setting/contract.
4. **Dice:** automatic/manual mode exists at turn request level. Manual challenge state is durable; the backend validates entered d20 faces. Per-campaign/per-actor/per-check-type policy is not implemented.
5. **World view:** world entities, relations, events, items/resources and player-safe memory/read projections exist. A polished world compendium, inline linked entity popovers, user-pinned context bundles and per-field NPC statistic visibility are not implemented.
6. **Export:** `GET /export` returns a player-safe memory/world projection. It is not a complete importable campaign archive; no campaign import route/package format exists.
7. **Rules:** D&D 5e 2014 is the default implementation target. Custom rules-module import and a declarative plugin/module contract do not yet exist. D&D 2024 remains future/non-priority.
8. **Languages:** no first-party localization system separating UI, campaign narration and player interaction languages exists yet.
9. **UI:** SillyTavern is the available narrative client. No native UI with Simplified/Advanced modes, custom layouts or field-by-field help exists.
10. **Security:** local loopback deployment is intentional. `X-Campaign-Id` is a selector, not authentication. There is no authenticated GM read projection; never expose hidden data through an untrusted flag.
11. **Activity history:** technical logs exist, and world events are part of campaign state. A separate typed player-facing activity timeline is not present; do not conflate logs with durable activity data.

These gaps are not architectural defects by themselves. They are explicit product requirements that need dedicated designs and acceptance criteria before implementation.

## 4. Documentation findings and corrections

| File/document family | Finding | Disposition in this audit |
|---|---|---|
| `README.md` | Product scope, roadmap, UI and export language did not reflect v0.2 or distinguish future capabilities. | Updated as the concise project entrypoint; detailed requirements remain in product spec. |
| `AGENTS.md` | Start-here links pointed to the 12 Nov map/audit and old CI/test audits. | Updated to current docs and status rules. |
| `docs/README.md` | Current list mixed historical snapshots with active documents. | Reorganized into current sources, contracts and historical reports. |
| `docs/architecture/README.md` | 12 Nov audit/map were labelled current. | Repointed to 18 Nov current audit/map. |
| `turn-resolution-lifecycle.md` | Still said “proposed PR #28” and “manual input follow-up”, contradicting implementation. | Rewritten as the implemented current contract. |
| `dnd5e-2014-rules-engine.md` | Claimed manual rolls were in-memory/15-minute and lost on restart. | Corrected to durable challenge persistence; distinguished backend-generated automatic results from player-submitted manual faces. |
| `llm-world-context-rendering-boundaries.md` | Described a retired narrative-extraction renderer as an active legacy path. | Rewritten around the live bounded structured proposal flow. |
| `writer-lock-cache-audit.md` | Route matrix still described retired `POST /integration/turn` mutation behavior. | Corrected route row and added current retirement note. |
| `observability-and-diagnostics.md` | Called PR #209 “planned” as though it were an imminent activity timeline. | Clarified that no separate player activity timeline currently exists. |
| `migration-catalog-2026-11-12.md` | Version 34 was correct but the verification point was implicit. | Header now records the current verification baseline. |
| Service guides | Most current ownership notes remain useful; context guide's discourse summary stopped at PR #223. | Updated context/turn guides for PRs #246–#255 and explicit remaining quality work. |
| 12 Nov architecture/module/change-impact snapshots | Their 12 Nov baselines are historical, not live source indexes. | Kept as snapshots, added supersession notices and linked current replacements. |
| 11–14 Nov CI/test/AI roadmaps and PR audit reports | Point-in-time counts and priorities must not be read as current. | Kept their evidence and added current-document pointers. |
| `legacy-sillytavern-turn-boundary.md` | Contradicts current code by describing `process_turn()` as active. | Marked explicitly superseded; retained as historical explanation only. |

The repository tree contained **118 Markdown/text documentation files** at this baseline. This audit inventories the full tree, reviews the current source-of-truth and operational docs against code, and classifies dated PR/audit documents as point-in-time evidence. Historical snapshots are not individually re-certified as current behavior.

## 5. Source-of-truth hierarchy

Use these documents in this order:

1. [Product requirements v0.2](../product/product-requirements-2026-11-18.md) for intended product behavior and approved choices.
2. [Current architecture map](architecture-map-2026-11-18.md) for implemented package ownership and request paths.
3. This audit for current architecture findings, implementation gaps and risk.
4. [Current quality roadmap](../quality/quality-roadmap-2026-11-18.md) for test/LLM acceptance work and its order.
5. Active lifecycle/transaction/dependency contracts and the relevant package README.
6. Source code and tests, which win if a prose document disagrees.
7. Dated PR reports and historical audits for why/when decisions were made only.

## 6. Recommended work order

### P0 — evidence and reliable baseline
- Run the current semantic predicate, discourse, callback/topic-boundary and compound-intent holdouts on the configured Ollama model.
- Record model digest/settings, Ollama version, latency and allowlisted metrics.
- Run the manual SillyTavern smoke test and record backend/extension/model versions.
- Preserve no-false-critical-mutation, no-secret-leak, idempotency and restart-recovery gates.

### P1 — first playable vertical slice
- Close critical rule/character/combat correctness gaps in one short adventure flow.
- Keep D&D 2014 as the default ruleset and label unsupported mechanics.
- Add multi-PJ control and NPC delegation as backend/domain contracts before UI shortcuts.

### P1/P2 — prepare the first-party UI
Start UX discovery and interface design when API contracts and durable workflows are solid, not after every possible rule exists. Build the UI as a client of the existing API. Do not duplicate mechanics, permission enforcement or SQLite access in the client.

### P2 — product extensibility
- Design a declarative, versioned and validated custom-rules module format before import support.
- Design full campaign archive/import/export separately from the current player-safe `GET /export`.
- Add internationalization with distinct UI, campaign and interaction language settings.
- Design the world compendium and field-level NPC visibility as projections of explicit knowledge policy.

### Explicitly deferred
Remote access, multiplayer, D&D 2024, VTT/tactical maps, distributed infrastructure and arbitrary executable plugins remain outside current priority.

## 7. Evidence and linked contracts

- [Architecture map](architecture-map-2026-11-18.md)
- [Product requirements](../product/product-requirements-2026-11-18.md)
- [Quality roadmap](../quality/quality-roadmap-2026-11-18.md)
- [Turn lifecycle](turn-resolution-lifecycle.md)
- [Turn pipeline compatibility](turn-pipeline-compatibility.md)
- [SillyTavern durable adapter](sillytavern-durable-turn-adapter.md)
- [World visibility/read models](../../services/world/README.md)
- [Migration catalogue](migration-catalog-2026-11-12.md)
- [Manual SillyTavern smoke test](../sillytavern-smoke-test.md)


## 8. NLU structural findings confirmed on 2026-11-19

The implementation has a single coherent semantic contract and deterministic authority boundaries, but the orchestration and linguistic stages have accumulated distinct responsibilities in oversized modules. The key architectural risk is not a missing LLM call; it is the coupling between payload normalization, discourse cues, independent surface mention extraction, candidate scoring and evaluation.

PR #267 extracts normalization into a dedicated `IntentNormalizationPipeline` with a typed result and safe diagnostics. This preserves the existing order of normalization and strict `PlayerIntentAnalysis` decoding; it is not a semantic rewrite.

Follow-up findings:
- `DiscourseContextBuilder` currently combines topic selection, surface extraction, speech attribution hints and prompt rendering. Extract cohesive collaborators behind the facade.
- `ConversationReferenceResolver` already uses independent pronoun/dative-clitic extraction for a bounded subset. Expand this contract rather than inaccurately describing it as wholly model-dependent.
- The general language holdout evaluator does not consistently penalize extra steps or extra semantic claims; improve the scorer before using a full live run to guide tuning.
- Regex is acceptable for narrowly scoped literal cues with negative tests, but not as a replacement for general morphology, syntax or coreference.

The implementation order and acceptance rules are normative in [player-language-understanding-architecture-2026-11-19.md](player-language-understanding-architecture-2026-11-19.md). Do not run the next full live-model suite until the architecture and evaluator milestones are integrated. Continue to require deterministic CI and report any omitted live/manual checks explicitly.
