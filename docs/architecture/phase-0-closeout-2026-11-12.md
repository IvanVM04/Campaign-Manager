# Phase 0 — architecture closeout and hand-off

**Scope:** local, single-player, single-process modular monolith.  
**Verified baseline:** `main` at `a14d1568ba852cd545caaf06e9efd48a4f925b03` (PR #205 merged, 2026-11-12).

## Decision

Phase 0 structural consolidation is closed for the current product scope. The
architecture is sufficiently modular to continue with gameplay. Do not start
another broad decomposition, microservices, distributed infrastructure,
multi-user authorization or standalone UI before gameplay demonstrates a
concrete need.

- PRs #198–#202 retired the parallel turn path, centralized player-safe
  visibility, extracted durable execution, hardened combat writes,
  coordinated world operations, split request schemas and indexed migrations.
- PR #203 added explicit runtime shutdown and invalidation behavior/tests and
  strengthened Ollama provider error/timeout handling.
- PR #204 completed the first cross-workflow audit of implemented character
  and combat state, fixed effect-aware movement/reactions and added Hit Dice
  plus short/long rests in migration 030.
- PR #205 split the durable-turn and context test suites by observable
  contract, preserving all 59 original test functions/assertions and changing
  no production behavior.

## Preserved compatibility/history

Do not delete `turn_snapshot_archive`, the `models.schemas` compatibility
facade, the legacy `npc_melee_attack` read fallback or historical migrations
merely as cleanup. They preserve data/import compatibility/history and are
not active parallel runtime paths.

## Remaining acceptance and quality work

### P1 — local end-to-end acceptance

Run the local Ollama + SillyTavern acceptance flow: campaign setup,
exploration, checks, clarification (including multiple rounds), manual and
automatic dice, combat where applicable, persistence, duplicate delivery,
regeneration, restart/recovery and provider outage/recovery. Record backend
revision, extension revision, model, settings and outcome in
[the smoke-test checklist](../sillytavern-smoke-test.md).

This has not been marked as passed. Deterministic CI does not establish real
model quality or the behavior of the local SillyTavern extension.

### P2 — remaining branch probes and live acceptance

- [x] Add deterministic medium/large campaign context and proposal fixtures
  covering stable ranking, mandatory character/location retention, dependency
  expansion, budget growth/exhaustion, projection non-mutation, secret-event
  exclusion and one compact repair (PR #207; see
  [probe documentation](../quality/context-scale-probes-2026-11-12.md)).
- Keep targeted branch coverage for stale revisions, partial-write rollback,
  lease fencing/recovery and effect expiry. Provider-level success, timeout,
  connection failure, HTTP errors, malformed JSON and no-hidden-transport-
  retry behavior already have deterministic tests; extend them only when a
  new uncovered contract is identified.
- Keep real Ollama quality probes opt-in and separate from deterministic CI.
  They do not replace the local Ollama + SillyTavern end-to-end acceptance.
- Do not introduce a global coverage threshold solely to raise a percentage.

Test-suite organization is complete in PR #205; deterministic context/proposal
scale probes are added in PR #207. Runtime shutdown/selective invalidation
tests and the Ollama adapter error contract are covered by PR #203.

## Deferred by product scope

No multiplayer, accounts, remote exposure, multiple workers, distributed
locks, automatic LRU/TTL cache eviction without measured need, standalone UI
or full D&D 5e implementation. Add rules in deterministic tested slices.

## Development hand-off

The next phase is gameplay-first: typed character creation and progression,
class/equipment/resource slices, a complete core combat/rest loop and one
complete first adventure. The suggested sequencing and indicative percentages
and hours are recorded in
[the engineering readiness and gameplay roadmap](engineering-readiness-and-gameplay-roadmap-2026-11-12.md).

Refactor further only when a real ownership, correctness, performance or
testability issue appears.
