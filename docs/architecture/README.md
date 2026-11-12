# Architecture documentation index

## Current baseline

- [Observability and diagnostics](observability-and-diagnostics.md): local logging configuration, correlation IDs, safe structured fields and the boundary with future player activity history.

- [Shared-layer module catalogue — 2026-11-12](module-catalog-2026-11-12.md): API, models, operations, persistence, rules engine, shared entrypoints and test navigation.
- [Phase 0 closeout — 2026-11-12](phase-0-closeout-2026-11-12.md): integrated structural changes, remaining acceptance gates and product hand-off.
- [Engineering readiness and gameplay roadmap — 2026-11-12](engineering-readiness-and-gameplay-roadmap-2026-11-12.md): post-#205 readiness assessment, module expansion priorities and indicative hour ranges.
- [Change-impact map — 2026-11-12](change-impact-map-2026-11-12.md): cross-layer consumer, transaction and regression-test review matrix.

- [Architecture map — 2026-11-12](architecture-map-2026-11-12.md): package/module ownership, execution paths, protected compatibility surfaces and improvement register.
- [Current architecture audit — 2026-11-12](architecture-audit-2026-11-12.md): latest source-verified architecture findings and refactoring priorities.
- [Combat attack-profile boundary](combat-attack-profile-boundary.md): player/NPC profile selection, rules derivation and atomic persistence contracts.
- [Combat and character-state audit — 2026-11-12](combat-character-state-audit-2026-11-12.md): canonical HP, persistent effects, movement/reaction projections, Hit Dice and rest transaction contracts.
- [Durable turn execution boundary](durable-turn-execution-boundary.md): request idempotency, planning leases, prepared commit hand-off and typed failures.

- [Entity reference resolution — 2026-11-12](../quality/entity-reference-resolution-2026-11-12.md): typed aliases, deterministic identity matching and ambiguity abstention.
- [Documentation hub](../README.md): current engineering, quality and package navigation for maintainers and coding agents.
- [CI and quality-gate audit — 2026-11-11](../quality/ci-audit-2026-11-11.md): actual workflow checks, required status checks and observed CI results.
- [Current test-suite navigation — 2026-11-12](../quality/test-suite-navigation-2026-11-12.md): durable native/SillyTavern, context, adapter and effects regression-test contracts.
- [Prompt evaluation — 2026-11-12](../quality/prompt-evaluation-2026-11-12.md): deterministic contracts, opt-in live Ollama probes and local acceptance boundaries.
- [Test-suite audit — 2026-11-11](../quality/test-suite-audit-2026-11-11.md): suite structure, protected contracts and reorganization plan.
- [LLM proposal prompt boundary](llm-world-proposal-prompt-boundary.md): active structured player-intent prompt.
- [LLM context rendering boundary](llm-world-context-rendering-boundaries.md): typed projection ownership and context-budget gap.
- [SillyTavern adapter boundary — 2026-11-12](sillytavern-adapter-boundary-2026-11-12.md): active read-only adapter and composition-root ownership.
- [Legacy retirement — 2026-11-12](legacy-retirement-2026-11-12.md): retired turn paths and snapshot data archive.

- [Capability-package dependency matrix](package-dependency-matrix.md): enforceable dependency direction for the eight service packages and the process for approving new cross-package edges.

- [Architecture and modularity audit — 2026-11-12](architecture-audit-2026-11-12.md): current package inventory, single turn pipeline, snapshot archival and ordered refactoring roadmap.
- [Architecture, maintainability and product-readiness audit — 2026-11-06](architecture-audit-2026-11-06.md): previous detailed audit. Retained as a dated snapshot; several migration-status statements were superseded by subsequent changes.
- [Turn pipeline contract](turn-pipeline-compatibility.md): the single supported durable native/SillyTavern flow.
- [Durable SillyTavern adapter contract](sillytavern-durable-turn-adapter.md): external turn identity, resolve/complete and retry semantics.
- [Writer, lock and cache audit](writer-lock-cache-audit.md): current single-process synchronization assumptions and mutation ownership.
- [SQLite transaction ownership](sqlite-transaction-ownership.md): transaction and shared-connection contract.
- [Migration catalogue](migration-catalog-2026-11-12.md): ordered schema history, explicit runner registry and upgrade checklist.
- [Turn-resolution lifecycle](turn-resolution-lifecycle.md): durable state transitions and commit boundaries.
- [MVP quickstart](../mvp-quickstart.md) and [manual SillyTavern smoke test](../sillytavern-smoke-test.md): operational setup and manual acceptance.

## Historical snapshots

The following documents are retained as decision and audit history. Their findings describe the repository at their recorded baseline and must not be treated as current without checking the 2026-11-12 architecture audit and legacy-retirement record.

- [Current architecture snapshot — 2026-11-05](current-architecture-2026-11-05.md)
- [Comprehensive architecture audit — 2026-11-05](comprehensive-architecture-audit-2026-11-05.md)
- [Audit and refactor plan — 2026-11-05](audit-and-refactor-plan-2026-11-05.md)
- [Engineering audit — 2026-11-03](engineering-audit-2026-11-03.md)
- [Functional audit — 2026-11-03](functional-audit-2026-11-03.md)
- [Architecture decisions — 2026-11-03](architecture-decisions-2026-11-03.md)
- [Roadmap — 2026-11-03](roadmap-2026-11-03.md)

Historical audit findings may have been fixed, superseded or invalidated by subsequent module moves. Preserve those files, but track current work in the latest audit and in focused implementation PRs.
