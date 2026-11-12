# Documentation hub

This is the starting point for maintainers and coding agents. Prefer current indexes over searching through dated audit history.

## Current engineering baseline

1. [Architecture map](architecture/architecture-map-2026-11-12.md) — global package map, main execution paths, module ownership, protected compatibility surfaces and module-level improvements.
2. [Shared-layer module catalogue](architecture/module-catalog-2026-11-12.md) — API, models, operations, repositories, rules engine, tests and shared entrypoints.
3. [Change-impact map](architecture/change-impact-map-2026-11-12.md) — which contracts and tests must be reviewed together for cross-layer changes.
4. [Current architecture and modularity audit](architecture/architecture-audit-2026-11-12.md) — verified findings, cleanup disposition and ordered refactoring plan.
5. [Capability dependency matrix](architecture/package-dependency-matrix.md) — enforced cross-package boundaries and the process for adding dependencies.
6. [CI audit](quality/ci-audit-2026-11-11.md) — workflow inventory, observed check results, enforcement gap and quality-gate roadmap.
7. [Test-suite audit](quality/test-suite-audit-2026-11-11.md) — suite composition, large modules, protected contracts and reorganization plan.
8. [Architecture documentation index](architecture/README.md) — active design contracts and historical audit snapshots.
9. [Quality roadmap](quality/ci-quality-roadmap.md) — baseline and staged static-analysis policy.

## Active architectural contracts

- [Shared-layer module catalogue — 2026-11-12](architecture/module-catalog-2026-11-12.md) — module-level navigation outside capability packages.
- [Change-impact map — 2026-11-12](architecture/change-impact-map-2026-11-12.md) — cross-layer change/test dependencies.
- [Architecture map — 2026-11-12](architecture/architecture-map-2026-11-12.md) — global entrypoint for coding agents and maintainers.
- [Current architecture audit — 2026-11-12](architecture/architecture-audit-2026-11-12.md) — supersedes earlier migration-status snapshots.

- [Legacy narrative prompt decomposition](architecture/legacy-prompt-decomposition-2026-11-12.md) — static instruction ownership and byte-for-byte compatibility baseline.
- [SillyTavern adapter boundary](architecture/sillytavern-adapter-boundary-2026-11-12.md) — read-only context adapter, injected legacy processor and bootstrap ownership.

- [Turn pipeline compatibility](architecture/turn-pipeline-compatibility.md) — active durable path vs deprecated narrative-first integration.
- [Durable SillyTavern adapter](architecture/sillytavern-durable-turn-adapter.md) — external turn identity, resolve/complete and retry semantics.
- [Turn resolution lifecycle](architecture/turn-resolution-lifecycle.md) — durable state transitions and commit boundaries.
- [SQLite transaction ownership](architecture/sqlite-transaction-ownership.md) — shared-connection and transaction contract.
- [Writer, lock and cache audit](architecture/writer-lock-cache-audit.md) — single-process synchronization assumptions.
- [LLM proposal prompt boundary](architecture/llm-world-proposal-prompt-boundary.md) — structured player-intent proposal path.
- [LLM context rendering boundary](architecture/llm-world-context-rendering-boundaries.md) — context projection ownership and rendering rules.
- [Manual SillyTavern smoke test](sillytavern-smoke-test.md) — live integration acceptance checklist.

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

## Historical audits

The architecture index retains the 2026-11-03, 2026-11-05 and 2026-11-06 snapshots. They are useful for rationale and decisions, but their migration status is not current unless confirmed by the 2026-11-12 audit, maps and source code.

## Rules for updating documentation

- Keep one current source of truth for present-day status.
- Mark completed work with its PR and merge date where useful.
- Keep pending items actionable and specific; remove completed items from pending checklists.
- Do not edit historical findings to describe later code as though it existed at the time.
- Link every new audit from this hub and the relevant index.
