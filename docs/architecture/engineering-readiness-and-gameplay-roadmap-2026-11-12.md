# Engineering readiness and gameplay roadmap — 2026-11-12

**Repository:** IvanVM04/Campaign-Manager  
**Verified baseline:** `main` at `a14d1568ba852cd545caaf06e9efd48a4f925b03` (PR #205 merged).  
**Product scope:** local, single-player, single-process modular monolith.  
**Purpose:** record the post-#205 architecture assessment, remaining engineering validation, module expansion priorities and planning estimates.

## Executive decision

The architecture is sufficiently modular for the current product scope. Do not schedule another broad decomposition phase. Continue with focused maintenance only when a verified ownership, correctness, observability or testing problem appears.

The previous structural backlog is substantially closed:

- PRs #198–#202 retired the parallel legacy turn path, centralized player-safe visibility, extracted durable turn execution, hardened combat transactions, coordinated world operations, split bounded-context request schemas and indexed migrations.
- PR #203 added runtime shutdown and explicit invalidation behavior/tests, and strengthened the Ollama provider's timeout/HTTP error handling and no-hidden-transport-retry contract.
- PR #204 audited canonical character/combat state, fixed persisted-effect projection for movement/reactions and introduced Hit Dice plus short/long rests in migration 030.
- PR #205 reorganized the durable-turn and context test suites by observable contract without changing production code or removing their 59 test functions/assertions.

The project is ready to move from architecture-first work to a gameplay-first development phase, subject to local acceptance with Ollama and SillyTavern.

## Readiness estimates

These are engineering judgement estimates for the present local single-player scope. They are **not** test coverage, code metrics, completion percentages calculated from source, or a claim of D&D 5e rules completeness.

| Area | Estimated readiness | Assessment |
|---|---:|---|
| Modularity and responsibility boundaries | 96% | Eight capability packages, one composition root and enforceable dependency direction; no broad split currently justified. |
| Persistence and transaction safety | 93% | Durable turn commit/recovery and combat multi-write rollback are covered; extend tests when new state families arrive. |
| Package boundaries and architecture tests | 95% | Dependency matrix and architecture-boundary tests guard the intended direction. |
| CI, typing and static analysis | 95% | Deterministic Python/JS, Ruff, repository-wide Pyright and CodeQL checks are integrated. |
| Provider adapter contract | 90% | Deterministic Ollama/fake-provider behavior is covered; real local model quality and end-to-end behavior remain unverified. |
| Architecture documentation freshness | 80% on the pre-#206 base branch | Current indexes existed, but several still carried stale post-#203–#205 status; this PR synchronizes them. Reassess after merge. |
| Live Ollama + SillyTavern acceptance | Not yet recorded | Must be executed and recorded locally; deterministic CI cannot establish model quality or extension behavior. |

Do not average these figures into a product-completion score. Their purpose is to distinguish structural readiness from functional breadth and live acceptance.

## Remaining engineering and validation

| Priority | Work | Status | Estimate |
|---|---|---|---:|
| P1 | Synchronize architecture/module documentation and remove completed checkboxes | This documentation PR | 2–3 h |
| P1 | Run local Ollama + SillyTavern acceptance and record model/settings/results | Not yet recorded | 2–4 h |
| P2 | Add representative medium/large campaign context and proposal probes | Pending | 3–5 h |
| Contingent | Correct defects discovered during live acceptance/probes | Unknown until observed | 0–6 h initial allowance |

**Residual engineering estimate: 7–18 hours**, including documentation, acceptance and scale probes, plus an initial allowance for corrections. This is a planning range, not a commitment that defects will fit within six hours.

### Live acceptance gate

Use [the SillyTavern smoke-test checklist](../sillytavern-smoke-test.md). Cover campaign setup, exploration, checks, manual and automatic dice, clarification (including multiple rounds), combat where applicable, duplicate delivery/regeneration, persistence, restart/recovery and provider outage/recovery. Record the date, backend revision, extension revision, model and settings. Do not mark it passed based only on unit tests or CI.

### Scale and quality probes

Keep deterministic fixtures in CI for retrieval, ranking, dependency expansion, mandatory character/location retention, budget exhaustion and non-mutation. Real Ollama quality probes remain opt-in and must record model/settings and representative campaign size. Do not add a vector database or semantic retrieval layer until real campaign cases demonstrate that deterministic ranking is insufficient.

## Module expansion roadmap

The percentages below are approximate estimates of functional breadth, not source coverage. They describe the distance to the next useful gameplay milestone, not completion of the full D&D 5e 2014 ruleset.

| Package / capability | Estimated functional breadth | What exists | Main expansion |
|---|---:|---|---|
| Characters | 40–45% | Canonical character state, sheet projections, HP, proficiencies, Hit Dice and rests | Typed character builder, class/race/background, ability scores, level progression, multiclass and feature resources. |
| Combat | 45–55% | Encounters, initiative, attacks, movement, reactions, death saves, persistent effects and atomic HP projections | Action economy, class features, spells, resource consumption, ammunition and more deterministic rule families. |
| Equipment and resources | Foundation exists; mechanics integration incomplete | Items, instances, ownership/location, equipment slots, generic resource balances and derived attack/armor profiles | Typed weapon properties, consumables, charges, ammunition and class-resource ownership/recovery. |
| D&D 5e 2014 rules engine | Around 30% of the full rules breadth | Deterministic character checks and a first combat/mechanics slice | Add only the rules needed by selected classes and the first playable adventure; expose unsupported rules rather than improvising. |
| Campaign and world | Foundation advanced; game loop incomplete | Campaigns, sessions, fictional clock, entities, relations, events, items, resources and persistence | Adventure objectives, clues, NPC continuity, quest progression, rewards and inter-session consequences. |
| Context, turns and LLM | Around 85–90% of the current technical pipeline | Bounded structured proposal, ranked detached context, typed operation registry, durable commit/recovery and post-commit narration | Live model validation, representative scale probes and prompt-quality adjustments driven by observed failures. |

## First playable milestone — planning estimate

The next functional objective is one complete vertical slice: create a typed character, equip/use basic items, resolve checks and combat, rest, gain rewards and preserve campaign continuity across turns/sessions.

| Deliverable | Estimate |
|---|---:|
| Typed and persisted character builder foundation | 12–20 h |
| First-class progression and typed class resources | 10–18 h |
| Combat action/resource expansion for that slice | 12–20 h |
| One complete first adventure with continuity and rewards | 8–14 h |
| **Gameplay subtotal** | **42–72 h** |

Combined with the residual engineering estimate above, the planning range is **49–90 hours** to complete the next engineering-and-first-playable milestone. This excludes implementing all of D&D 5e, a standalone UI, multiplayer, accounts, remote hosting or any unexpectedly large defects.

## Recommended order

1. Complete and merge the documentation/readiness update.
2. Run the local Ollama + SillyTavern smoke test and record the outcome.
3. Add representative context/proposal scale probes and fix any demonstrated issue.
4. Build the typed character-creation vertical slice.
5. Add one class progression/resource slice that feeds both the sheet and deterministic rules.
6. Extend combat and equipment only for the mechanics required by that class/adventure.
7. Deliver the first complete adventure and verify persistence/continuity end to end.

## Architecture work explicitly deferred

Do not create work solely to reduce file size or reach a coverage percentage. Keep the current modular monolith and avoid:

- microservices, message bus, distributed locks/cache or multiple workers;
- multiplayer, accounts, remote exposure or an unauthenticated GM bypass;
- a standalone UI before the gameplay loop is stable;
- LRU/TTL runtime eviction without measured cache pressure and an in-flight request policy;
- a universal resource counter for class features/spell slots;
- a full 5e rules implementation before a selected playable slice requires it.

Reopen architecture only when a concrete defect or new product requirement creates a distinct ownership, transaction, authorization, persistence or testing boundary.

## Evidence and current references

- [Phase 0 closeout](phase-0-closeout-2026-11-12.md)
- [Current architecture audit](architecture-audit-2026-11-12.md)
- [Architecture map](architecture-map-2026-11-12.md)
- [Test-suite navigation](../quality/test-suite-navigation-2026-11-12.md)
- [Combat and character-state audit](combat-character-state-audit-2026-11-12.md)
- [Manual SillyTavern smoke test](../sillytavern-smoke-test.md)
- Integrated PRs: [#203](https://github.com/IvanVM04/Campaign-Manager/pull/203), [#204](https://github.com/IvanVM04/Campaign-Manager/pull/204), [#205](https://github.com/IvanVM04/Campaign-Manager/pull/205).
