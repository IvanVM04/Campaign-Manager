# Architecture documentation index

Use the **current baseline** section for present-day design. The historical section records earlier audits and implementation stages without treating their pending items as live work.

## Current baseline — verified 2026-11-18

- [Current architecture map](architecture-map-2026-11-18.md) — current package ownership, pipelines, persistence, API and implementation gaps.
- [Current architecture audit](architecture-audit-2026-11-18.md) — source-verified assessment and ordered engineering risks.
- [Current change-impact map](change-impact-map-2026-11-18.md) — cross-package change and regression map.
- [Documentation freshness audit](../documentation-audit-2026-11-18.md) — repository-wide docs inventory, stale claims and source-of-truth hierarchy.
- [Capability dependency matrix](package-dependency-matrix.md) — enforceable dependencies and rules for adding a new edge.
- [Migration catalogue](migration-catalog-2026-11-12.md) — current schema version 34, migration registry and forward-only update rules.
- [SQLite transaction ownership](sqlite-transaction-ownership.md) — transaction and shared-connection rules.
- [Writer, lock and cache audit](writer-lock-cache-audit.md) — process-local lock and current route/writer inventory.
- [Observability and diagnostics](observability-and-diagnostics.md) — structured logs, redaction and request correlation.
- [World applier boundaries](world-applier-boundaries.md) — operation-family ownership and mutation invariants.
- [D&D 5e 2014 rules foundation](dnd5e-2014-rules-engine.md) — implemented subset, automatic/manual dice and limitations.

## Active contracts

- [Turn pipeline compatibility](turn-pipeline-compatibility.md) — single native and external durable resolution path; retired route guard.
- [Durable turn-resolution lifecycle](turn-resolution-lifecycle.md) — implemented lifecycle states, idempotency, challenge recovery, commit and narration.
- [Durable SillyTavern adapter](sillytavern-durable-turn-adapter.md) — adapter resolve/complete behavior and idempotency/version rules.
- [SillyTavern adapter boundary](sillytavern-adapter-boundary-2026-11-12.md) — adapter responsibilities and composition boundary (dated implementation record).
- [LLM proposal prompt boundary](llm-world-proposal-prompt-boundary.md) — structured proposal schema/trust contract.
- [LLM world-context rendering boundary](llm-world-context-rendering-boundaries.md) — detached projection and bounded prompt rendering.
- [Combat attack-profile boundary](combat-attack-profile-boundary.md) — source selection and deterministic profile derivation.
- [Combat/character-state audit](combat-character-state-audit-2026-11-12.md) — canonical HP, persistent effects and rest transaction contract.

## Current quality and product links

- [Product requirements v0.2](../product/product-requirements-2026-11-18.md) — target capabilities and explicit status.
- [Quality roadmap](../quality/quality-roadmap-2026-11-18.md) — current AI acceptance and implementation priorities.
- [Test-suite navigation](../quality/test-suite-navigation-2026-11-18.md) — current tests by contract.
- [Manual SillyTavern smoke test](../sillytavern-smoke-test.md) — client integration acceptance checklist.
- [Documentation hub](../README.md) — full current source-of-truth index.

## Historical snapshots

The following documents describe their named baseline only. Preserve them for rationale/evidence, but do not use their old PR priorities, migration status, routes or TODOs as current without source revalidation.

- [Architecture map — 2026-11-12](architecture-map-2026-11-12.md) — superseded by the 2026-11-18 map.
- [Architecture audit — 2026-11-12](architecture-audit-2026-11-12.md) — superseded by the 2026-11-18 audit.
- [Module catalogue — 2026-11-12](module-catalog-2026-11-12.md) — PR #205-era inventory; use current map and package guides.
- [Change-impact map — 2026-11-12](change-impact-map-2026-11-12.md) — superseded by the 2026-11-18 map.
- [Engineering readiness/gameplay roadmap — 2026-11-12](engineering-readiness-and-gameplay-roadmap-2026-11-12.md) and [Phase 0 closeout](phase-0-closeout-2026-11-12.md) — historical estimates/hand-off.
- [Legacy retirement record](legacy-retirement-2026-11-12.md) — records removed compatibility paths and snapshot archival.
- [Architecture audit — 2026-11-06](architecture-audit-2026-11-06.md), [current architecture — 2026-11-05](current-architecture-2026-11-05.md), [comprehensive architecture audit — 2026-11-05](comprehensive-architecture-audit-2026-11-05.md), [audit/refactor plan — 2026-11-05](audit-and-refactor-plan-2026-11-05.md), [engineering audit — 2026-11-03](engineering-audit-2026-11-03.md), [functional audit — 2026-11-03](functional-audit-2026-11-03.md), [architecture decisions — 2026-11-03](architecture-decisions-2026-11-03.md) and [roadmap — 2026-11-03](roadmap-2026-11-03.md).

## Maintenance rules

- A code change that alters ownership, route behavior, transactions, visibility, persistence, model contracts or dependencies updates the owning current contract and this index as needed.
- Do not rewrite historical findings as though later code existed at the original date.
- Do not leave a proposed lifecycle or retired implementation indexed as the current contract.
- Product requirements describe intended behavior; code and tests determine implementation status.
