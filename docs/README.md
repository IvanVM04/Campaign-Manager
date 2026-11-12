# Documentation hub

This is the starting point for maintainers and coding agents. Prefer current
indexes over searching through dated audit history.

## Current engineering baseline

1. [Architecture map](architecture/architecture-map-2026-11-12.md) — global package map, main execution paths and module ownership.
2. [Shared-layer module catalogue](architecture/module-catalog-2026-11-12.md) — API, models, operations, repositories, rules engine, tests and shared entrypoints.
3. [Change-impact map](architecture/change-impact-map-2026-11-12.md) — contracts and tests to review for cross-layer changes.
4. [Current architecture and modularity audit](architecture/architecture-audit-2026-11-12.md) — verified findings and ordered refactoring plan.
5. [Migration catalogue](architecture/migration-catalog-2026-11-12.md) — ordered schema history, migration registry and rules for adding the next version.
6. [Legacy retirement record](architecture/legacy-retirement-2026-11-12.md) — retired paths, preserved snapshot history and migration 029.
7. [Capability dependency matrix](architecture/package-dependency-matrix.md) — enforced cross-package boundaries.
8. [CI audit](quality/ci-audit-2026-11-11.md) — workflow inventory, observed check results and quality-gate roadmap.
9. [Test-suite audit](quality/test-suite-audit-2026-11-11.md) — suite composition, large modules and protected contracts.
10. [Architecture documentation index](architecture/README.md) — active design contracts and historical audit snapshots.
11. [Quality roadmap](quality/ci-quality-roadmap.md) — staged static-analysis policy.

## Active architectural contracts

- [Turn pipeline contract](architecture/turn-pipeline-compatibility.md) — the single supported durable turn lifecycle.
- [SillyTavern adapter boundary](architecture/sillytavern-adapter-boundary-2026-11-12.md) — read-only context/transcript adapter and bootstrap ownership.
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

The architecture index retains earlier dated audit snapshots. They explain
why decisions were made, but their migration/cleanup status is historical.
Use the current architecture audit, maps and source code for present behavior.

## Rules for updating documentation

- Keep one current source of truth for present-day status.
- Mark completed work with its PR and merge date where useful.
- Keep pending items actionable and specific; remove completed items from pending checklists.
- Do not edit historical findings to describe later code as though it existed at the time.
- Link every new audit from this hub and the relevant index.
