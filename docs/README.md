# Documentation hub

This is the starting point for maintainers and coding agents. Prefer current
indexes over searching through dated audit history.

## Shared contracts

- [Models and shared contracts](../models/README.md) — canonical semantic and durable value contracts, trust rules and model-layer change guidance.

## Current engineering baseline

1. [Architecture map](architecture/architecture-map-2026-11-12.md) — global package map, main execution paths and module ownership.
2. [Shared-layer module catalogue](architecture/module-catalog-2026-11-12.md) — API, models, operations, repositories, rules engine, tests and shared entrypoints.
3. [Change-impact map](architecture/change-impact-map-2026-11-12.md) — contracts and tests to review for cross-layer changes.
4. [Current architecture and modularity audit](architecture/architecture-audit-2026-11-12.md) — verified findings and ordered refactoring plan.
5. [Phase 0 closeout](architecture/phase-0-closeout-2026-11-12.md) — integrated structural work, remaining acceptance gates and hand-off to gameplay.
6. [Engineering readiness and gameplay roadmap](architecture/engineering-readiness-and-gameplay-roadmap-2026-11-12.md) — post-#205 assessment, indicative module readiness and effort estimates.
7. [Migration catalogue](architecture/migration-catalog-2026-11-12.md) — ordered schema history, migration registry and rules for adding the next version.
8. [Legacy retirement record](architecture/legacy-retirement-2026-11-12.md) — retired paths, preserved snapshot history and migration 029.
9. [Capability dependency matrix](architecture/package-dependency-matrix.md) — enforced cross-package boundaries.
10. [CI audit](quality/ci-audit-2026-11-11.md) — workflow inventory, observed check results and quality-gate roadmap.
11. [Test-suite navigation](quality/test-suite-navigation-2026-11-12.md) — current contract-based test layout after PR #205.
12. [Observability and diagnostics](architecture/observability-and-diagnostics.md) — local structured logging, request correlation, error diagnostics and safe field policy.
13. [Prompt evaluation](quality/prompt-evaluation-2026-11-12.md) — deterministic proposal contracts, live Ollama probes and the SillyTavern acceptance boundary.
14. [AI world-understanding roadmap](quality/ai-world-understanding-roadmap-2026-11-12.md) — multi-PR strategy for world comprehension, retrieval, intent semantics, knowledge provenance and narrative continuity.
15. [P0 language-understanding implementation specification](quality/language-understanding-priority-2026-11-13.md) — current P0 priority register, shared intent contract and acceptance gates.
16. [Modular language-understanding pipeline](quality/modular-language-understanding-pipeline-2026-11-14.md) — approved Priority #1 architecture decision, stage boundaries, prompt budgets and acceptance criteria.
17. [PR #226 execution checkpoint](quality/pr-226-integrated-llm-pipeline-hardening.md) — current integrated pipeline hardening, deterministic CI, telemetry, compatibility boundary and exact live acceptance hand-off.
18. [Independent language-understanding audit](quality/language-understanding-audit-2026-11-14.md) — skeptical assessment of PRs #210–#223, remaining risks, prompt-budget failure and effort estimates.
19. [Entity reference resolution](quality/entity-reference-resolution-2026-11-12.md) — explicit aliases, deterministic matching rules, ambiguity abstention and known limitations.
20. [Semantic-understanding next-phase plan](quality/semantic-understanding-next-phase-2026-11-13.md) — typed action arguments, grounded relations, object identity, discourse and correction roadmap.
21. [Historical test-suite audit](quality/test-suite-audit-2026-11-11.md) — dated suite analysis and prior reorganization decisions.
22. [Architecture documentation index](architecture/README.md) — active design contracts and historical audit snapshots.
23. [Quality roadmap](quality/ci-quality-roadmap.md) — staged static-analysis policy.

## AI understanding and evaluation

- [AI world-understanding roadmap](quality/ai-world-understanding-roadmap-2026-11-12.md) — current priorities and semantic-quality acceptance boundary.
- [Semantic prompt evaluation](quality/prompt-evaluation-2026-11-12.md) — deterministic contracts, live Ollama protocol and metrics.
- [110-scenario evaluation corpus](quality/semantic-understanding-evaluation-corpus-2026-11-13.md) — development/held-out inventory and scoring policy.
- [PR #226 integrated pipeline audit](quality/pr-226-integrated-llm-pipeline-hardening.md) — modular role boundaries and hardening checkpoint.
- [PR #227 discourse/pipeline evaluation](quality/pr-227-held-out-discourse-pipeline-evaluation.md) — merged held-out fixture, evaluator and discourse regression checkpoint.
- [PR #228 Ollama thinking configuration](quality/pr-228-configurable-ollama-thinking.md) — per-role `think` control, live-model timeout investigation and reproducible A/B evaluation setup.
- [PR #229 Intent validation diagnostics](quality/pr-229-intent-validation-diagnostics.md) — safe validation-stage errors and single-scenario live evaluation for model debugging.
- [PR #230 Field-level Intent validation diagnostics](quality/pr-230-field-level-intent-validation-diagnostics.md) — safe semantic-field diagnostics and strict focused live evaluation.
- [PR #231 Intent category/active-step consistency](quality/pr-231-intent-category-active-step-consistency.md) — conservative provider-boundary normalization, regression coverage and Ollama performance investigation.
- [PR #232 Intent step position canonicalization](quality/pr-232-intent-step-position-canonicalization.md) — zero-based indexes derived from ordered step-array positions, safe normalization and 12B/26B latency comparison.
- [PR #233 Intent attribution evidence grounding](quality/pr-233-intent-attribution-current-evidence.md) — clears history-only step attributions without weakening strict domain validation or authorizing world changes.
- [PR #234 Discourse holdout fixture integrity](quality/pr-234-discourse-holdout-fixture-integrity.md) — supplies NPC speaker entities to the live prompt harness and validates literal expected mentions.

- [Predicate-understanding audit (2026-11-17)](quality/predicate-understanding-audit-2026-11-17.md) — action/relation predicate coverage, live metrics, measurement gaps and remaining effort.
- [PR #250 Predicate-specific evaluation and telemetry](quality/pr-250-predicate-evaluation-and-telemetry.md) — exact action/relation surface scoring, reproducible live JSON reports and privacy-safe usage telemetry.
- [Semantic-understanding hardening (2026-11-17)](quality/semantic-understanding-hardening-2026-11-17.md) — audit-led taxonomy, evidence-bound surface rules, optional-field sanitization and independent evaluation.
- [Discourse-understanding evaluation and actor hardening (2026-11-17)](quality/discourse-understanding-evaluation-2026-11-17.md) — primary fictional-actor gold, independent topic/callback/ellipsis controls and privacy-safe live Ollama reports.

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
