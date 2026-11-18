# Documentation hub

This is the starting point for maintainers, coding agents and product planning. Use the current source-of-truth documents below for present behavior. Older dated audits and PR reports are retained as historical evidence.

## Current product definition

- [Product requirements v0.2](product/product-requirements-2026-11-18.md) — approved product scope, functional/non-functional requirements, user-configurable control, NPC delegation, AI uncertainty/clarification, interface, world knowledge, rules modules, languages and import/export.
- [Quickstart for the current MVP](mvp-quickstart.md) — executable local setup through the current SillyTavern integration; explicitly lists what is not yet implemented.
- [Documentation freshness audit — 2026-11-18](documentation-audit-2026-11-18.md) — inventory, stale-document findings, current source hierarchy and historical classification.

## Current engineering source of truth

1. [Current architecture map — 2026-11-18](architecture/architecture-map-2026-11-18.md) — actual service ownership, pipelines, persistence, API and known implementation gaps.
2. [Current architecture audit — 2026-11-18](architecture/architecture-audit-2026-11-18.md) — source-verified design, technical risks and product/code gap assessment.
3. [Current change-impact map — 2026-11-18](architecture/change-impact-map-2026-11-18.md) — code ownership and required regression surfaces for cross-cutting changes.
4. [Capability dependency matrix](architecture/package-dependency-matrix.md) — enforceable dependency direction across the eight service packages.
5. [Shared-layer module catalogue — 2026-11-12](architecture/module-catalog-2026-11-12.md) — point-in-time catalogue; use current map/source to verify current files.
6. [Migration catalogue](architecture/migration-catalog-2026-11-12.md) — migration history, current schema version 34 and rules for adding the next migration.
7. [Observability and diagnostics](architecture/observability-and-diagnostics.md) — structured local logs, correlation IDs, redaction and separation from player activity data.
8. [SQLite transaction ownership](architecture/sqlite-transaction-ownership.md) — transaction and shared-connection contract.
9. [Writer, lock and cache audit](architecture/writer-lock-cache-audit.md) — single-process synchronization assumptions and current mutation-route status.
10. [World applier boundaries](architecture/world-applier-boundaries.md) — typed world mutation ownership and preserved invariants.
11. [D&D 5e 2014 rules foundation](architecture/dnd5e-2014-rules-engine.md) — currently implemented deterministic rules subset and dice boundary.

## Current durable turn and LLM contracts

- [Turn-resolution lifecycle](architecture/turn-resolution-lifecycle.md) — implemented states, idempotency, challenge recovery, atomic commit and post-commit narration.
- [Turn pipeline compatibility](architecture/turn-pipeline-compatibility.md) — one supported native/SillyTavern durable flow and retired-path guard.
- [SillyTavern adapter boundary](architecture/sillytavern-adapter-boundary-2026-11-12.md) — context/transcript adapter and composition boundary; dated implementation snapshot.
- [Durable SillyTavern adapter](architecture/sillytavern-durable-turn-adapter.md) — external turn identity, resolve/complete, retries and versioning.
- [LLM proposal prompt boundary](architecture/llm-world-proposal-prompt-boundary.md) — structured consequence-proposal trust and schema contract.
- [LLM world-context rendering boundary](architecture/llm-world-context-rendering-boundaries.md) — current detached projection, selector and proposal-renderer boundary.
- [Manual SillyTavern smoke test](sillytavern-smoke-test.md) — real-client acceptance checklist; must be run and recorded locally.

## Current quality and testing

- [Quality roadmap — 2026-11-18](quality/quality-roadmap-2026-11-18.md) — latest verified CI baseline, outstanding live-model and integration gates, prioritised implementation/acceptance phases.
- [Test-suite navigation — 2026-11-18](quality/test-suite-navigation-2026-11-18.md) — current test families, focused modules and standard/live/manual commands.
- [Predicate-understanding audit — 2026-11-17](quality/predicate-understanding-audit-2026-11-17.md) — historical live score/failure analysis; use current roadmap for pending order.
- [Semantic-understanding hardening — 2026-11-17](quality/semantic-understanding-hardening-2026-11-17.md) — PR-level implementation/evaluation snapshot.
- [Discourse-understanding evaluation — 2026-11-17](quality/discourse-understanding-evaluation-2026-11-17.md) — PR-level holdout/scorer snapshot.
- [Player-message comprehension phase — 2026-11-18](quality/player-message-comprehension-phase-2026-11-18.md) — PR #255 implementation record and held-out compound-intent contract.

The deterministic CI result does not certify live Ollama semantics or a real SillyTavern session. Consult the current quality roadmap rather than reusing historical metrics as current.

## Capability package guides

| Package | Guide |
|---|---|
| Campaign | [services/campaign](../services/campaign/README.md) |
| Characters | [services/characters](../services/characters/README.md) |
| Combat | [services/combat](../services/combat/README.md) |
| Context | [services/context](../services/context/README.md) |
| LLM world | [services/llm_world](../services/llm_world/README.md) |
| Providers | [services/providers](../services/providers/README.md) |
| Turns | [services/turns](../services/turns/README.md) |
| World | [services/world](../services/world/README.md) |
| Shared models/contracts | [models](../models/README.md) |

## Historical snapshots and PR records

These records explain decisions, baselines and results at their recorded dates. Their old status, count, priority or TODO language must not be treated as current without checking the current source-of-truth documents.

- [Architecture documentation index](architecture/README.md) — historical architecture snapshots and active contracts.
- [Architecture audit — 2026-11-12](architecture/architecture-audit-2026-11-12.md), [architecture map — 2026-11-12](architecture/architecture-map-2026-11-12.md), [change-impact map — 2026-11-12](architecture/change-impact-map-2026-11-12.md) — superseded source snapshots.
- [Engineering readiness and gameplay roadmap — 2026-11-12](architecture/engineering-readiness-and-gameplay-roadmap-2026-11-12.md) and [Phase 0 closeout](architecture/phase-0-closeout-2026-11-12.md) — historical structural hand-off.
- [CI audit — 2026-11-11](quality/ci-audit-2026-11-11.md), [CI quality roadmap](quality/ci-quality-roadmap.md), [test-suite audit — 2026-11-11](quality/test-suite-audit-2026-11-11.md), [test-suite navigation — 2026-11-12](quality/test-suite-navigation-2026-11-12.md) — dated CI/test snapshots.
- [AI world-understanding roadmap — 2026-11-12](quality/ai-world-understanding-roadmap-2026-11-12.md), [language-understanding priority — 2026-11-13](quality/language-understanding-priority-2026-11-13.md), [modular language-understanding pipeline — 2026-11-14](quality/modular-language-understanding-pipeline-2026-11-14.md), [semantic next-phase plan — 2026-11-13](quality/semantic-understanding-next-phase-2026-11-13.md) — historical development plans; the current quality roadmap supersedes their old “next PR” guidance.
- PR execution reports and held-out corpus definitions (#210–#255) remain useful for the exact change/test evidence at each revision. They are not a substitute for the current architecture/quality status.

## Rules for maintaining documentation

- Keep one current source of truth for product intent, architecture, quality priorities and test navigation.
- Update current docs in the same PR as code/API/schema/ownership changes.
- A product requirement is not marked implemented until source and tests demonstrate it.
- Keep historical PR/audit evidence dated. Add a clear supersession pointer when it can be mistaken for current; do not rewrite historical measurements or conclusions.
- Link each new current document here and from the relevant index.
