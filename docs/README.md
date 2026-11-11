# Documentation hub

This is the starting point for maintainers and coding agents. Prefer current indexes over searching through dated audit history.

## Current engineering baseline

1. [Current architecture and modularity audit](architecture/architecture-audit-2026-11-11.md) — actual package ownership, active and legacy flows, prompt pipeline and ordered refactoring plan.
2. [Capability dependency matrix](architecture/package-dependency-matrix.md) — enforced cross-package boundaries and the process for adding dependencies.
3. [CI audit](quality/ci-audit-2026-11-11.md) — workflow inventory, observed check results, enforcement gap and quality-gate roadmap.
4. [Test-suite audit](quality/test-suite-audit-2026-11-11.md) — suite composition, large modules, protected contracts and reorganization plan.
5. [Architecture documentation index](architecture/README.md) — active design contracts and historical audit snapshots.
6. [Quality roadmap](quality/ci-quality-roadmap.md) — baseline and staged static-analysis policy.

## Active architectural contracts

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

The architecture index retains the 2026-11-03, 2026-11-05 and 2026-11-06 snapshots. They are useful for rationale and decisions, but their migration status is not current unless confirmed by the 2026-11-11 audit and source code.

## Rules for updating documentation

- Keep one current source of truth for present-day status.
- Mark completed work with its PR and merge date where useful.
- Keep pending items actionable and specific; remove completed items from pending checklists.
- Do not edit historical findings to describe later code as though it existed at the time.
- Link every new audit from this hub and the relevant index.
