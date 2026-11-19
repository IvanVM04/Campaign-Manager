# Change-impact map — 2026-11-18

**Baseline:** code `f4fb3914ebab4579118863796e6f6d4b7183d0cf` (PR #255); documentation main `4a3a2549bb0bb1bc38ec0e6f456ac6d5ccef24d1` (PR #257).  
**Purpose:** identify all boundaries and tests to inspect for cross-cutting changes. This is a review checklist, not an import/dependency map. The [package dependency matrix](package-dependency-matrix.md) remains authoritative for allowed imports.

## Review rule

Trace each behavior across inbound request/client, orchestration, trust boundary, canonical state, rules, persistence transaction, read projection and tests. Do not treat a product requirement as evidence that a corresponding domain/API capability exists.

## Current implemented paths

| Change area | Owning code/contracts | Required regression focus |
|---|---|---|
| Durable native turn | `api/routers/turns.py`, `DurableNativeTurnService`, `DurableTurnExecutionService`, challenge/commit/narration collaborators, turn models/repositories | Idempotency-key/fingerprint, state transitions, planning lease fencing, stale context, awaiting_input, prepared commit, retry and restart recovery. |
| SillyTavern turn | `api/routers/integration.py`, `integrations/adapters/silly_tavern`, integration schemas, durable turn services, extension | Stable external_turn_id, conversation_id, adapter scoping, duplicate delivery, clarification/manual roll resume, complete/version sequencing, swipe without mutation replay, chat switch/restart. |
| Intent interpretation | `IntentInterpreter`, `PlayerIntentAnalysis`, intent schemas, semantic frames, discourse evidence, prompt and live corpora | V1 compatibility; V2 step frames/relations; literal evidence; action actor; category/active-step consistency; polarity/modality; negative/hypothetical/question abstention; provider failures; compound per-step gold. |
| Conversation references | `ConversationReferenceResolver`, `DiscourseContextBuilder` facade, `services/discourse/{topic_history_selector,surface_mention_extractor,speaker_signal_extractor,renderer}`, `EntityReferenceResolver`, visibility policies | Current-turn versus history/narrator evidence, topic boundaries, callbacks, pronouns, dative recipients, NPC speaker signal, plural group safety, unique-target abstention and six/12-turn scope as implemented. |
| Pending corrections/clarifications | `PendingIntentCorrection`, clarification submission service, turn codec/repository, models 033/034 | Only literal latest-answer edits; unaffected fields preserved; pending/uncommitted guard; chat isolation; multi-round state; manual-roll/clarification continuation; no effects until valid commit. |
| Mechanics and dice | `MechanicsAdjudicator`, `rules_engine/dnd5e_2014`, durable manual-roll service, API schemas | Only actionable active step invokes adjudication; automatic server roll; manual d20 count/range; context revision; accepted result replay idempotency; conflicting result rejected; no LLM-supplied dice result. |
| World proposal/application | Operation registry/parser, `LLMWorldExtractor.propose()`, proposal validator, `WorldService`, appliers/repositories | Proposable/internal operation classification; schema alignment; semantic evidence; campaign/ownership/resource checks; caller-owned connection; atomic rollback; canonical IDs only from deterministic resolution. |
| Context retrieval and prompt | `MemorySearchService`, `ContextBuilder`, expander/ranker/selector, `WorldContextProjection`, renderers/providers | Mandatory active character/location; dependency bundles; secret/superseded event policy; stable ordering; complete prompt and repair budgets; detached projection; no `context -> llm_world` dependency. |
| World/collection APIs | World query/collection services, visibility policy, world read models, routers | Campaign scope, IDs/display names, pagination, query filters, secret filtering before search/count, detached projections, no unauthenticated GM bypass. |
| Character mechanics and rest | Character creation/state/sheet/rest services, CharacterState, repositories, clock/effect services | Canonical character HP/Hit Dice, equipment projections, expected clock version, active encounter guard, campaign clock/effect expiry, atomic transaction and rollback. |
| Combat | Combat encounter/attack services, attack profile resolver, pure rules engine, CharacterState/CreatureState, effects | Expected round/turn, canonical HP versus encounter snapshot, profile source, NPC metadata validation, damage/defenses/death saves, movement/reactions, same transaction. |
| Migrations | `migrations.py`, `MIGRATIONS`, migration catalog, migration tests | Forward-only ordering, 001–034 continuity, fresh install/upgrade/replay, foreign keys/indexes/triggers, preservation of legacy records. |
| Error/observability | `api/errors.py`, middleware/log allowlist, `observability` | Stable code/detail, request-ID correlation, no prompt/completion/player text/secrets/credentials in logs or error responses. |

## Product requirements not implemented yet — design impact for future PRs

These rows deliberately list future areas; they are **not descriptions of existing APIs**.

| Product capability | Design boundaries to define first | Minimum acceptance concerns |
|---|---|---|
| Multi-PJ control | Campaign/character authority model, control set versus active context character, turn actor selection, context/retrieval and mechanics hand-off, API read/write projections | Add/remove/switch control during play; one action attributed to the correct PJ; no unauthorized PJ operation; persisted across restart. |
| NPC delegation | NPC authority policy, requested/granted/rejected/revoked delegation record, grant scope/expiry, who can approve current owner, UI/API notifications | DM and player can request; only current authority approves; audit trail; revocation and restart; never grants knowledge/world authority by implication. |
| Configurable uncertainty | Calibrated model signals, evidence quality/validation feedback, campaign settings, durable per-turn checkpoint/slot dependencies | Low-confidence/ambiguous cases ask; clear cases proceed; resolved slots are not asked again; only dependent fields recompute; no premature world effects. |
| First-party UI | Client-facing stable API contracts, error/loading/pending-state models, safe read projections | Same domain authority as SillyTavern; accessible mouse/keyboard/touch; Simplified/Advanced are two views of same settings. |
| World compendium / inline links | Canonical entity reference in narration output, known-to-player/known-to-character projection, per-field visibility policy | Search/cards/panels/hover/focus/tap show only permitted data; manual context selection adds context but not new intent evidence. |
| NPC stat visibility | Per-campaign defaults plus per-NPC/per-field override and projection policy | HP/AC/conditions/resources can be visible/hidden/descriptive; underlying canonical mechanics remain unaffected. |
| Dice policy | Campaign/actor/check-category policy resolver and durable challenge schema | Manual versus backend automatic; correct actor attribution; deterministic tests; LLM cannot choose random values. |
| Custom rules modules | Versioned declarative manifest/schema, dependency/conflict resolution, campaign activation and deterministic engine boundary | Invalid/incompatible modules rejected; import rollback; no arbitrary code execution; tests per rule module. |
| Internationalization | Stable internal IDs, translation catalogs, UI/campaign/interaction language preferences | Spanish/English first; add another locale without data migration or semantic ID changes. |
| Full campaign import/export | Versioned portable archive, manifest, data graph, module dependencies and migration/validation strategy | Preflight validation, no partial import, round-trip integrity, secrets/GM data policy, conflict/duplicate strategy. |

## Relevant adjacent references

- [Current architecture map](architecture-map-2026-11-18.md)
- [Architecture audit](architecture-audit-2026-11-18.md)
- [Product requirements](../product/product-requirements-2026-11-18.md)
- [Quality roadmap](../quality/quality-roadmap-2026-11-18.md)
- [Package dependency matrix](package-dependency-matrix.md)
