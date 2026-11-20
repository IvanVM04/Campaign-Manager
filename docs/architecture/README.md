# Architecture documentation index

This index separates active technical contracts from dated architecture proposals and audits. For current product intent and status, start with [product requirements v0.2](../product/product-requirements-2026-11-18.md), [current system state](current-state-2026-11-18.md) and [documentation audit](documentation-audit-2026-11-18.md).

## Current architecture baseline

- [Current system state and architecture map — 2026-11-18](current-state-2026-11-18.md): current implementation shape, API/workflow, ownership, migration version, security, observed CI and unimplemented product requirements.
- [Project-wide audit — 2026-11-19](project-audit-2026-11-19.md): latest reconciled main SHA, integrated PRs #267–#269, CI metrics, product requirements progress, risks and next steps.
- [Current architecture map](architecture-map-2026-11-18.md): package ownership, pipelines, persistence, API surfaces and implementation gaps.
- [Current architecture audit](architecture-audit-2026-11-18.md): source-verified design, risks and ordered engineering priorities.
- [Current change-impact map](change-impact-map-2026-11-18.md): cross-package dependencies, affected contracts and regression-test surfaces.
- [Player intent and semantic understanding redesign audit — 2026-11-20](player-intent-semantic-redesign-audit-2026-11-20.md): current architecture direction after the PR #281 live evaluation; diagnosis, target semantic model, authority boundaries, v2-to-v3 migration and implementation PR sequence.
- [Player turn interpretation v3 contract — 2026-11-20](player-turn-interpretation-v3-contract-2026-11-20.md): phase-1 v3 DTOs, strict evidence/local-reference decoder, backend-only gameplay candidate and explicit no-production-wiring boundary delivered by PR #285.
- [Player turn interpretation v3 shadow prompt — 2026-11-20](player-turn-interpretation-v3-shadow-2026-11-20.md): PR #286 evaluation-only holistic prompt, paired v2/v3 runner, audit-derived holdout and content-free live report; production remains on v2.
- [Player action selection and partial checkpoint — 2026-11-20](player-action-selection-checkpoint-2026-11-20.md): PR #287 backend-only action graph, deterministic dependency gating, lease-fenced checkpoint persistence and selective clarification resume; the live turn route remains v2.
- [Player-language understanding architecture — 2026-11-19](player-language-understanding-architecture-2026-11-19.md): historical design baseline for the v2 pipeline and the PR #267–#272 structural work. The 2026-11-20 audit supersedes it as the recommended target design; the v2 code remains the current implementation until the proposed migration is delivered.
- [Documentation freshness audit — 2026-11-18](documentation-audit-2026-11-18.md): stale statements, current-vs-historical classification and synchronized index work.
- [Shared-layer module catalogue — PR #205 snapshot](module-catalog-2026-11-12.md): useful navigation inventory for shared layers, not a current source audit. Verify current paths against source and the 2026-11-18 map.
- [Change-impact map — 2026-11-12](change-impact-map-2026-11-12.md): cross-layer contracts, consumers and regression-test review.
- [Capability package dependency matrix](package-dependency-matrix.md): enforceable dependency direction and process for approving new edges.
- [Migration catalogue](migration-catalog-2026-11-12.md): active migration registry and schema version; the current application reports version 35.
- [Observability and diagnostics](observability-and-diagnostics.md): local structured logging, correlation IDs, safe fields and telemetry boundary.
- [Writer/lock/cache-coherence audit](writer-lock-cache-audit.md): current single-process synchronization assumptions and route-to-writer matrix. Historical PR #78 fixes are retained as provenance.

## Active application and lifecycle contracts

Prefer these contracts for current implementation work.

- [Turn pipeline compatibility](turn-pipeline-compatibility.md): the one supported native and external durable turn contract; the narrative-first endpoint is retired.
- [Durable turn execution boundary](durable-turn-execution-boundary.md): execution collaborator ownership, sequencing and typed failures.
- [Durable challenge state](durable-challenge-state-boundary.md): client-safe read projection of pending challenge state.
- [Durable clarification submission](durable-clarification-submission.md): clarification validation, continuation, idempotency and recovery.
- [Durable manual-roll submission](durable-manual-roll-submission.md): manual dice challenge submission and replay semantics.
- [Durable prepared-challenge commit](durable-prepared-challenge-commit.md): shared atomic commit boundary for native turns, clarification and manual rolls.
- [Durable narration lifecycle](durable-narration-lifecycle.md): native and external narration completion after consequence commit.
- [SillyTavern adapter boundary](sillytavern-adapter-boundary-2026-11-12.md): read-only context/transcript adaptation and composition-root ownership.
- [SillyTavern durable adapter](sillytavern-durable-turn-adapter.md): external turn identity, resolve/complete, retry, regeneration and chat isolation.
- [SQLite transaction ownership](sqlite-transaction-ownership.md): caller-owned transaction and repository connection rules.
- [SQLite maintenance and recovery](sqlite-maintenance-and-recovery.md): offline integrity checks, WAL-aware backups and guarded restoration.
- [Campaign state revisions](campaign-state-revisions.md): optimistic revision and mutation-trigger rules.
- [World applier boundaries](world-applier-boundaries.md): world-operation application ownership and mutation invariants.
- [API error contract](api-error-contract.md): stable transport error envelope and safe diagnostics.
- [LLM proposal prompt boundary](llm-world-proposal-prompt-boundary.md): active structured consequence proposal.
- [LLM world-context rendering boundary](llm-world-context-rendering-boundaries.md): active typed, detached, bounded projection and current context safety constraints.
- [Combat attack-profile boundary](combat-attack-profile-boundary.md): trusted player/NPC attack profile selection and deterministic rules derivation.
- [Combat/character-state audit](combat-character-state-audit-2026-11-12.md): canonical HP/effects/rest ownership for the implemented vertical slice.
- [D&D 5e 2014 rules-engine foundation](dnd5e-2014-rules-engine.md): actual implemented deterministic subset and rule-source boundaries.

**Historical lifecycle design:** [turn-resolution-lifecycle.md](turn-resolution-lifecycle.md) is the original PR #28 design proposal. It is intentionally retained, marked superseded and must not be used as the active contract.

## Historical architecture decisions and audits

The 2026-11-19 player-language understanding document is retained as the historical v2 architecture baseline. Its implementation notes remain useful, but its original roadmap/status predates PRs #272–#281 and its target design is superseded by the 2026-11-20 player-intent semantic redesign audit.

These documents are point-in-time reports. Their original conclusions, PR recommendations, counts and implementation status should be read against their recorded dates/baselines. The 2026-11-18 current-state map supersedes their general “current status”.

- [Architecture audit — 2026-11-12](architecture-audit-2026-11-12.md) and [architecture map — 2026-11-12](architecture-map-2026-11-12.md): snapshots around PRs #205–#218.
- [Phase 0 closeout — 2026-11-12](phase-0-closeout-2026-11-12.md) and [engineering readiness/gameplay roadmap — 2026-11-12](engineering-readiness-and-gameplay-roadmap-2026-11-12.md): prior structural closure and indicative planning estimates.
- [Architecture audit — 2026-11-11](architecture-audit-2026-11-11.md).
- [Architecture/maintainability audit — 2026-11-06](architecture-audit-2026-11-06.md).
- [Comprehensive architecture audit — 2026-11-05](comprehensive-architecture-audit-2026-11-05.md), [audit and refactor plan — 2026-11-05](audit-and-refactor-plan-2026-11-05.md), and [architecture snapshot — 2026-11-05](current-architecture-2026-11-05.md).
- [Engineering audit — 2026-11-03](engineering-audit-2026-11-03.md), [functional audit — 2026-11-03](functional-audit-2026-11-03.md), [domain boundaries — 2026-11-03](domain-boundaries-2026-11-03.md), [architecture decisions — 2026-11-03](architecture-decisions-2026-11-03.md), and [roadmap — 2026-11-03](roadmap-2026-11-03.md).

## Legacy retirement and historical migration records

- [Legacy retirement — 2026-11-12](legacy-retirement-2026-11-12.md) records removal of the parallel narrative-first mutation path and migration 029 snapshot archive.
- [Legacy cleanup inventory — 2026-11-06](legacy-cleanup-2026-11-06.md) records retired flat shims and preserved history.
- [Legacy extraction-boundary audit](legacy-extraction-boundary-audit-2026-11-12.md), [legacy prompt decomposition](legacy-prompt-decomposition-2026-11-12.md), [legacy SillyTavern retirement audit](legacy-sillytavern-retirement-audit-2026-11-11.md) and [legacy SillyTavern turn boundary](legacy-sillytavern-turn-boundary.md) are historical documents with explicit supersession notices.

## Older implementation boundaries

These focused documents explain individual fixes and contracts that remain relevant where linked by the current-state map or package guides:

- [Context rendering boundary](context-rendering-boundaries.md) — historical generic renderer snapshot, superseded by the active context package and proposal-context contracts.
- [Durable turn-resolution persistence](durable-turn-resolution-persistence.md) — migration 022 introduction and persistence rationale.
- [Durable challenge-state](durable-challenge-state-boundary.md), [clarification submission](durable-clarification-submission.md), [manual-roll submission](durable-manual-roll-submission.md), [prepared commit](durable-prepared-challenge-commit.md) and [narration lifecycle](durable-narration-lifecycle.md) — extracted collaborators of the implemented workflow.
- [Combat consistency audit](../combat-consistency-audit.md), [armor](../armor-rules.md), [weapon domain](../weapon-domain.md), [combat attack](../combat-attack.md), [movement](../combat-movement.md), [opportunity attacks](../combat-opportunity-attacks.md), [death saves](../death-saving-throws.md), [persistent effects](../persistent-effects.md) and [campaign clock](../campaign-clock.md).

## Index maintenance

- Keep the current-state map as the architecture-wide implementation snapshot. The player-language understanding design is an active capability contract; do not treat its target roadmap as code that already exists.
- Link new active technical contracts here and from the documentation hub; label v3 as a contract-only milestone until PR #286 and later gates are complete.
- Do not put dated PR implementation notes in the current baseline section.
- Preserve historical baselines; add a supersession notice rather than rewriting their original state.
- Product requirements define the target; implementation claims must be checked against code and current tests.
