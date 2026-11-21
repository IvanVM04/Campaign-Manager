# Documentation hub

This is the navigation entry point for maintainers, coding agents and product work. The repository contains both current source-of-truth documents and dated implementation/audit snapshots. **A date-stamped PR record is not automatically current guidance.**

## Current source of truth — 2026-11-21

**Prioridad técnica máxima:** programa de comprensión semántica #292–#305.
- [Roadmap maestro de comprensión semántica — 2026-11-21](architecture/player-understanding-roadmap-2026-11-21.md) — fuente de verdad para PRs, dependencias, gates y estado de implementación.
- [Arquitectura objetivo de comprensión — 2026-11-21](architecture/player-understanding-target-architecture-2026-11-21.md) — modelo semántico v3, responsabilidades, autoridad, evidencia y migración v2→v3.
- [Roadmap de evaluación semántica — 2026-11-21](quality/semantic-understanding-evaluation-roadmap-2026-11-21.md) — corpus, gold, graph scorer, métricas y gates propuestos.
- [Scorer graph-aware y corpus v3 — 2026-11-21](quality/v3-graph-evaluation-and-corpus-2026-11-21.md) — evaluación por nodos y aristas, alineación sin IDs locales, diagnóstico por escenario y 20 nuevos casos held-out.
- [Prompt v3 y alineación de evidencias — 2026-11-21](quality/v3-prompt-recall-and-evidence-alignment-2026-11-21.md) — cobertura de cláusulas compuestas, pasada independiente de hechos y reparación conservadora de offsets literales en shadow.
- [Roadmap de prompts y runtime Ollama — 2026-11-21](quality/llm-runtime-reproducibility-and-prompt-roadmap-2026-11-21.md) — generation options, manifiesto reproducible, prompts, budgets y telemetría.
- [Proceso de entrega del programa NLU — 2026-11-21](architecture/player-understanding-delivery-workflow-2026-11-21.md) — obligación de sincronizar roadmap en cada PR antes de merge.

## Previous source-of-truth snapshots

Los documentos de los días 18–20 de noviembre siguen siendo registros históricos y de implementación. Sus baselines y hallazgos no se reescriben; para la secuencia NLU activa y el estado actual de las PR debe utilizarse el roadmap del 21 de noviembre.


Read these first. They describe the current product target, source-verified implementation state and active quality priorities.

- [Product requirements v0.2](product/product-requirements-2026-11-18.md) — product direction, confirmed design decisions, functional/non-functional requirements, desired UI, acceptance gates and proposed ideas clearly separated from approved requirements.
- [Current system state and architecture map](architecture/current-state-2026-11-18.md) — architecture snapshot dated 18 Nov with a 19 Nov reconciliation note.
- [Project-wide audit — 19 Nov](architecture/project-audit-2026-11-19.md) — latest source-verified baseline at `8276450`, PR #267–#269 delivery, CI metrics and updated roadmap.
- [Current architecture map](architecture/architecture-map-2026-11-18.md), [architecture audit](architecture/architecture-audit-2026-11-18.md) and [change-impact map](architecture/change-impact-map-2026-11-18.md) — complementary package/flow map, source-verified technical risks and regression surfaces.
- [Auditoría y rediseño de intención y semántica — 2026-11-20](architecture/player-intent-semantic-redesign-audit-2026-11-20.md) — dirección arquitectónica activa tras PR #281: actos comunicativos, eventos, enlaces discursivos, hechos y selección backend de acciones.
- [Player turn interpretation v3 contract — 2026-11-20](architecture/player-turn-interpretation-v3-contract-2026-11-20.md) — contrato de fase 1 entregado por PR #285; DTOs/decoder y criterios de aislamiento. No implica que v3 se use en producción.
- [Player turn interpretation v3 shadow prompt — 2026-11-20](architecture/player-turn-interpretation-v3-shadow-2026-11-20.md) — PR #286: prompt holístico y comparación en sombra v2/v3 con corpus held-out; harness de evaluación únicamente, producción permanece en v2.
- [Player action selection and partial checkpoint — 2026-11-20](architecture/player-action-selection-checkpoint-2026-11-20.md) — PR #287: selector backend determinista, dependencias `condition_on_success`, checkpoint durable por acción y reanudación parcial; sin activar todavía el pipeline v3 en los turnos reales.
- [World-fact eligibility and persistence policy — 2026-11-20](architecture/player-world-fact-policy-2026-11-20.md) — PR #288: política backend de hechos persistentes, resolución canónica visible, escritura append-only de atributos, relaciones dirigidas/idempotentes y recibos ligados al checkpoint; todavía no conectada al runtime v2.
- [Diseño de comprensión de lenguaje — 2026-11-19](architecture/player-language-understanding-architecture-2026-11-19.md) — snapshot histórico del pipeline v2 y del trabajo estructural #267–#272; no describe el diseño objetivo propuesto el 20 de noviembre.
- [Documentation freshness audit](architecture/documentation-audit-2026-11-18.md) — file-by-file classification, stale statements found, documents updated, historical material retained and remaining documentation gaps.
- [Current NLU roadmap](architecture/player-understanding-roadmap-2026-11-21.md) — maximum-priority, merge-tracked implementation sequence #292–#305. The 18 November quality roadmap is now a historical snapshot for its original broader quality scope.
- [Quickstart for the current MVP](mvp-quickstart.md) — executable local setup through the current SillyTavern integration; explicitly lists what is not yet implemented.
- [README](../README.md) — project overview, quick setup, route summary and top-level engineering navigation.
- [AGENTS.md](../AGENTS.md) — mandatory contributor/coding-agent instructions.

## Current architecture and package navigation

- [Architecture index](architecture/README.md) — active architecture contracts, package boundaries and historical snapshots.
- [Shared-layer module catalogue — dated PR #205 inventory](architecture/module-catalog-2026-11-12.md) — useful navigation aid for shared layers; individual paths/notes are not a fresh 2026-11-18 audit, so verify against source and the current-state map.
- [Change-impact map](architecture/change-impact-map-2026-11-12.md) — contracts and tests to review for cross-layer changes.
- [Capability dependency matrix](architecture/package-dependency-matrix.md) — dependency direction enforced by architecture tests.
- [Migration catalogue](architecture/migration-catalog-2026-11-12.md) — migration registry and schema version. The current code baseline has `CURRENT_VERSION = 35`.
- [Observability and diagnostics](architecture/observability-and-diagnostics.md) — structured local logs, correlation, safe telemetry and privacy boundaries.
- [Writer, lock and cache audit](architecture/writer-lock-cache-audit.md) — current single-process synchronization and route-to-writer responsibilities.

### Capability guides

Each package guide documents current code ownership and package-specific contracts.

| Package | Guide |
|---|---|
| Campaign | [services/campaign](../services/campaign/README.md) |
| Characters | [services/characters](../services/characters/README.md) |
| Combat | [services/combat](../services/combat/README.md) |
| Context and retrieval | [services/context](../services/context/README.md) |
| Structured world proposals | [services/llm_world](../services/llm_world/README.md) |
| LLM providers | [services/providers](../services/providers/README.md) |
| Durable turns | [services/turns](../services/turns/README.md) |
| Discourse understanding | [services/discourse](../services/discourse/README.md) |
| World application | [services/world](../services/world/README.md) |
| Shared models/contracts | [models](../models/README.md) |

## Active technical contracts

These documents describe current production boundaries. Prefer them over historical proposals where the two differ.

- [Turn pipeline contract](architecture/turn-pipeline-compatibility.md) — active native and external durable routes; retired narrative-first route.
- [Durable turn execution boundary](architecture/durable-turn-execution-boundary.md) — execution orchestration, commit and recovery ownership.
- [Durable challenge-state boundary](architecture/durable-challenge-state-boundary.md) — read projection for pending challenges.
- [Durable clarification submission](architecture/durable-clarification-submission.md) — validated clarification continuation and idempotency.
- [Durable manual-roll submission](architecture/durable-manual-roll-submission.md) — manual dice continuation and recovery.
- [Durable prepared-challenge commit](architecture/durable-prepared-challenge-commit.md) — shared atomic commit for prepared turns/challenges.
- [Durable narration lifecycle](architecture/durable-narration-lifecycle.md) — native and external narration after commit.
- [SillyTavern adapter boundary](architecture/sillytavern-adapter-boundary-2026-11-12.md) — context/history adapter and composition ownership.
- [Durable SillyTavern adapter](architecture/sillytavern-durable-turn-adapter.md) — external turn identity, resolve/complete, retries and chat isolation.
- [Structured world-proposal prompt boundary](architecture/llm-world-proposal-prompt-boundary.md) — single active consequence proposal contract.
- [LLM world-context boundary](architecture/llm-world-context-rendering-boundaries.md) — typed, detached, bounded proposal context.
- [SQLite transaction ownership](architecture/sqlite-transaction-ownership.md) — connection and transaction responsibilities.
- [SQLite maintenance and recovery](architecture/sqlite-maintenance-and-recovery.md) — offline integrity checks, consistent backups and guarded restoration.
- [Campaign state revisions](architecture/campaign-state-revisions.md) — revision/fencing semantics.
- [World applier boundaries](architecture/world-applier-boundaries.md) — validated domain application.
- [Package dependency matrix](architecture/package-dependency-matrix.md) — enforced architectural dependency rules.

**Note:** [turn-resolution-lifecycle.md](architecture/turn-resolution-lifecycle.md) is retained as the original PR #28 proposal. It is historical, not the active implementation contract.

## Current AI understanding and quality evidence

The latest project-wide baseline and reconciled milestone status are recorded in [the 2026-11-19 project audit](architecture/project-audit-2026-11-19.md). PR #269 is integrated; it is no longer in progress.

- [Historical quality roadmap](quality/quality-roadmap-2026-11-18.md) — original dated priority order after PR #266; use the 21 November NLU roadmap for the current semantic-understanding program.
- [Live Ollama evaluation — 2026-11-20](quality/live-ollama-evaluation-2026-11-20.md) — diagnostic run with Gemma 4 12B Q4_K_M after PRs #279/#280: 11/22 live tests passed, domain F1 85,24–98,67 %, compound-step modality 54,0 %, callback 3/12 and a report-commit provenance mismatch. The 93 % mean is not a global comprehension score, and the run is not a SillyTavern acceptance result.
- [Auditoría de rediseño semántico — 2026-11-20](architecture/player-intent-semantic-redesign-audit-2026-11-20.md) — diagnosis and target architecture based on that failure inventory; PR #285 implements its additive v3 DTO/decoder phase, while production remains on v2.
- [Player-language understanding architecture](architecture/player-language-understanding-architecture-2026-11-19.md) — the contract source for the NLU structural work.
- [Player-message comprehension phase — PR #255](quality/player-message-comprehension-phase-2026-11-18.md) — current delivery record: dative clitics, named-NPC speech signals, callback anchor scoping, negated step sequencing and 14 compound-intent holdout scenarios.
- [Predicate-understanding audit](quality/predicate-understanding-audit-2026-11-17.md) — dated audit which motivated predicate-specific scoring; its historical scores are not a current post-PR255 baseline.
- [Discourse-understanding evaluation](quality/discourse-understanding-evaluation-2026-11-17.md) — dated evaluation snapshot before PR #255.
- [Semantic-understanding hardening](quality/semantic-understanding-hardening-2026-11-17.md) — dated PR #253 semantic taxonomy/normalization record.
- [Prompt evaluation protocol](quality/prompt-evaluation-2026-11-12.md) — opt-in local Ollama evaluation protocol and safe reporting rules.
- [Test-suite navigation](quality/test-suite-navigation-2026-11-12.md) — suite grouping snapshot after PR #208; counts and baselines are historical.
- [CI audit](quality/ci-audit-2026-11-11.md) — workflow/ruleset investigation from 2026-11-11; use current workflow evidence linked from the current system-state map for latest results.

## Operational and rules references

- [MVP quickstart](mvp-quickstart.md) — current local setup and SillyTavern walkthrough. It describes the current working client, not the final UI plan.
- [SillyTavern smoke-test checklist](sillytavern-smoke-test.md) — manual integration acceptance; must be completed locally and never inferred from deterministic CI.
- [D&D 5e 2014 rules-engine foundation](architecture/dnd5e-2014-rules-engine.md) — implemented mechanics scope and deterministic rules-engine boundary.
- [Armor rules](armor-rules.md), [weapon domain](weapon-domain.md), [combat attacks](combat-attack.md), [combat movement](combat-movement.md), [opportunity attacks](combat-opportunity-attacks.md), [death saving throws](death-saving-throws.md), [persistent effects](persistent-effects.md), [campaign clock](campaign-clock.md), and [combat consistency audit](combat-consistency-audit.md).

## Historical snapshots and implementation records

These are intentionally retained because they explain why the architecture and semantics evolved. Their own dates/baselines remain valid historical facts; do not treat old TODOs, line counts, coverage numbers or “next PR” statements as present work without checking the current-state map and quality roadmap.

### Historical architecture and design snapshots

- [Architecture audit — 2026-11-12](architecture/architecture-audit-2026-11-12.md) — PR #205 baseline; superseded as current status.
- [Architecture map — 2026-11-12](architecture/architecture-map-2026-11-12.md) — PR #218-era map; superseded as current map.
- [Phase 0 closeout — 2026-11-12](architecture/phase-0-closeout-2026-11-12.md) — structural hand-off decision from that date.
- [Engineering readiness/gameplay roadmap — 2026-11-12](architecture/engineering-readiness-and-gameplay-roadmap-2026-11-12.md) — dated planning estimates, not current completion percentages.
- [Architecture audit — 2026-11-11](architecture/architecture-audit-2026-11-11.md), [2026-11-06](architecture/architecture-audit-2026-11-06.md), [2026-11-05](architecture/comprehensive-architecture-audit-2026-11-05.md), [2026-11-03](architecture/engineering-audit-2026-11-03.md), and [functional audit — 2026-11-03](architecture/functional-audit-2026-11-03.md).
- [Architecture decisions — 2026-11-03](architecture/architecture-decisions-2026-11-03.md) and [domain boundaries — 2026-11-03](architecture/domain-boundaries-2026-11-03.md).
- [Legacy retirement record](architecture/legacy-retirement-2026-11-12.md) and [legacy cleanup inventory](architecture/legacy-cleanup-2026-11-06.md) — historical record of retired code and preserved data.

### Historical AI/quality plans and PR delivery notes

The following are dated implementation/evaluation records, not independent active backlogs: [AI world-understanding roadmap](quality/ai-world-understanding-roadmap-2026-11-12.md), [language-understanding priority](quality/language-understanding-priority-2026-11-13.md), [modular language pipeline](quality/modular-language-understanding-pipeline-2026-11-14.md), [language architecture audit](quality/language-understanding-architecture-audit-2026-11-16.md), [language audit](quality/language-understanding-audit-2026-11-14.md), [advanced discourse](quality/advanced-discourse-understanding-2026-11-14.md), [semantic next phase](quality/semantic-understanding-next-phase-2026-11-13.md), [entity reference resolution](quality/entity-reference-resolution-2026-11-12.md), [typed world reference resolution](quality/typed-world-reference-resolution-2026-11-13.md), [context scale probes](quality/context-scale-probes-2026-11-12.md), and [110-scenario evaluation corpus](quality/semantic-understanding-evaluation-corpus-2026-11-13.md).

PR-specific records #226–#250 remain useful for provenance and design rationale. They are indexed here as [PR #226](quality/pr-226-integrated-llm-pipeline-hardening.md), [#227](quality/pr-227-held-out-discourse-pipeline-evaluation.md), [#228](quality/pr-228-configurable-ollama-thinking.md), [#229](quality/pr-229-intent-validation-diagnostics.md), [#230](quality/pr-230-field-level-intent-validation-diagnostics.md), [#231](quality/pr-231-intent-category-active-step-consistency.md), [#232](quality/pr-232-intent-step-position-canonicalization.md), [#233](quality/pr-233-intent-attribution-current-evidence.md), [#234](quality/pr-234-discourse-holdout-fixture-integrity.md), [#235](quality/pr-235-intent-surface-evidence-prompting.md), [#236](quality/pr-236-intent-speech-act-categories.md), [#237](quality/pr-237-reference-correction-evidence-reliability.md), [#238](quality/pr-238-read-only-negative-references-and-coverage-gate.md), [#240–#246](quality/pr-240-atomic-pending-correction-selectors.md), [#250](quality/pr-250-predicate-evaluation-and-telemetry.md), and [the consolidated PR #255 delivery record](quality/player-message-comprehension-phase-2026-11-18.md).

## Documentation maintenance rules

- Keep exactly one current product requirements baseline, one current system-state map and one current quality roadmap.
- Update their indexes whenever a new authoritative document is introduced.
- Preserve dated audit and PR records as immutable history; add a supersession banner instead of silently rewriting the facts of their baseline.
- A requirement is not an implementation claim. Product documents must distinguish implemented, partial, pending and out-of-scope work.
- Keep exact code/CI/live-test baselines and dates. Deterministic CI, live Ollama evaluation and manual SillyTavern acceptance are separate evidence classes.
