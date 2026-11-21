# Repository guidance for coding agents

Read this file before making repository changes.

## Start here

1. Read [the documentation hub](docs/README.md).
2. Read the [current system state](docs/architecture/current-state-2026-11-18.md), [current architecture map](docs/architecture/architecture-map-2026-11-18.md), [current architecture audit](docs/architecture/architecture-audit-2026-11-18.md) and [current change-impact map](docs/architecture/change-impact-map-2026-11-18.md).
3. Read the [product requirements v0.2](docs/product/product-requirements-2026-11-18.md) and [current quality roadmap](docs/quality/quality-roadmap-2026-11-18.md).
4. Read the [shared-layer module catalogue](docs/architecture/module-catalog-2026-11-12.md), [capability dependency matrix](docs/architecture/package-dependency-matrix.md), relevant package `README.md` and active technical contract before changing a capability.
5. Read the [documentation freshness audit](docs/architecture/documentation-audit-2026-11-18.md) when editing documentation. Dated CI/test audits are historical; use the current quality roadmap and latest workflow evidence for present status.

Dated audits and PR implementation records are historical snapshots unless explicitly designated as current. Inspect source and current contracts before treating an old recommendation, count or status as pending.

## Working agreement

- Keep one active implementation branch and one open PR at a time.
- Start every PR from the latest integrated `main`.
- Keep each PR focused on one architectural or quality objective.
- Do not merge while any applicable CI check is failing, pending or cancelled.
- Fix failures on the same PR branch; do not create a follow-up PR to work around a known failure.
- Do not use auto-merge as a substitute for reviewing checks and the diff.
- Do not add gameplay features while the active objective is CI, architecture, legacy cleanup, prompt quality or test maintenance.
- Do not claim a live Ollama/SillyTavern smoke test passed unless it was actually run.

The default-branch ruleset `protc1` requires pull requests, review-thread resolution, `CI summary`, and both CodeQL language checks. `CI summary` aggregates Ruff, deterministic tests, scoped and repository-wide Pyright, and JavaScript tests. See the current CI audit.

## Mandatory player-understanding roadmap synchronization

The active highest-priority language-understanding program is governed by [the master roadmap](docs/architecture/player-understanding-roadmap-2026-11-21.md) and [its delivery workflow](docs/architecture/player-understanding-delivery-workflow-2026-11-21.md).

For every PR in that program:
- Update the matching master-roadmap row before requesting review and before merge.
- Record delivered and deferred scope, acceptance criteria, deterministic CI, Ollama evidence and SillyTavern status separately.
- Do not mark a row MERGED + VERIFIED until the PR is actually merged and required evidence exists.
- At the next program PR, reconcile all rows left as IMPLEMENTED — PR OPEN by recording the confirmed merge SHA/date.
- A code module that is not wired into the runtime must be described as isolated, not integrated.
- Any exception to the roadmap checklist must be explained in the PR body and reflected in the roadmap.

## Environment setup

Install runtime dependencies and the pinned development tools from the canonical PEP 735 dependency groups:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install --group test --group lint --group typing
```

The CI workflows install only the relevant group for each job. Update versions in `pyproject.toml`, not ad-hoc workflow commands.

## Required validation

For implementation and test changes, run the checks applicable to the changed scope:

```bash
ruff check .
python -m pytest -m "not real_llm" --cov --cov-report=term-missing --cov-report=xml
npm run test:js
pyright models rules_engine bootstrap operations
pyright
```

CodeQL analyzes Python and JavaScript/TypeScript on pull requests, pushes to `main` and its weekly schedule. Repository-wide Pyright is a blocking CI job and currently has a zero-diagnostic baseline. Live-provider tests are marked `real_llm` and are not part of deterministic CI.

A green CI run does not prove that a manual SillyTavern session or live LLM call works. Report those separately.

## Architecture constraints

- Preserve the modular-monolith design. Do not introduce microservices, a message bus, a vector database, distributed locks or generic infrastructure frameworks without a demonstrated requirement.
- Treat `bootstrap/campaign_runtime.py` as the composition root.
- API routers are transport adapters; do not make them compose runtimes or own domain workflows.
- Respect [the package dependency matrix](docs/architecture/package-dependency-matrix.md). Update the matrix and architecture tests in the same PR when a new service dependency is justified.
- Import from canonical capability packages. Do not restore flat compatibility shims or old exports.
- Keep deterministic rules/mechanics, semantic validation, persistence and LLM proposal generation as separate authorities.
- Preserve the single coherent, versioned player-intent response. Do not split related action/frame/relation fields across independent model calls.
- Keep intent normalization, discourse selection/surface extraction and canonical conversation-reference resolution as separate typed stages; read `docs/architecture/player-language-understanding-architecture-2026-11-19.md` before changing their contracts.
- Current player text is the only source for current-turn literal evidence. History and narration may help bounded reference resolution but must never be promoted into the current player's evidence.
- LLM output is untrusted input. It may propose operations but must never write directly to SQLite or bypass domain validation.
- Preserve turn idempotency, campaign revision checks, lease fencing, short atomic commit boundaries and narration recovery.
- The narrative-first `POST /integration/turn` route, `LegacySillyTavernTurnService`, `WorldSnapshotRepository`, `LLMWorldExtractor.extract()` and runtime `turns.snapshot` column are retired. Do not reintroduce them. Migration 029 preserves old non-null snapshot JSON in the inert `turn_snapshot_archive` table.

## LLM context and prompt constraints

- Keep static instructions separate from typed context data.
- The structured proposal prompt is the only world-consequence proposal path. Keep static instructions separate from typed context data; do not add a parallel narrative-first extraction pipeline.
- `TurnResolutionService` builds the active structured proposal projection through `ContextBuilder.build_proposal_context()` and passes the typed `models.world_context_projection.WorldContextProjection` to `services/llm_world`.
- Keep the dependency direction: `services/turns` may orchestrate `services.context`; `services/llm_world` must not import `services.context`.
- The current proposal-context implementation requires one trusted active-character focus and preserves current location, related records and dependency bundles. The product target additionally supports controlling several player characters and selecting further known entities; that broader policy is specified in product requirements v0.2 and must not be represented as already implemented.
- Never solve context overflow by truncating arbitrary campaign facts.
- The shared token-budget helper is a conservative one-UTF-8-byte-per-token upper bound, not a model-specific tokenizer. The complete prompt and compact one-repair request are independently bounded.
- Keep provider output size-limited, repair attempts limited to one, and model output strictly validated.

## Test-suite maintenance

- Tests document observable contracts. Never remove a test only because it is small, old, slow-looking or in a large file.
- Remove legacy tests in the same PR as the implementation they protect, after verifying all consumers.
- When splitting a test module, preserve fixtures, assertions, parameterization and failure-path coverage.
- Keep migration tests for supported historical schema upgrades.
- Keep deterministic CI independent of Ollama and external network services.
- Prefer tests at the narrowest useful boundary, retaining integration tests for cross-component guarantees.

## Documentation requirements

- Update the relevant package `README.md` when ownership, public exports or dependencies change.
- Update the current architecture audit and architecture map when a finding is fixed or a new one is confirmed.
- Keep historical audit documents dated and immutable; do not rewrite history to make it appear that a later fix was always present.
- Record module purpose, consumers, dependency rules, known risks and concrete follow-up work.
- Link new current documents from [the documentation hub](docs/README.md) and the relevant index.

## PR acceptance checklist

- [ ] One focused objective; no unrelated feature work.
- [ ] Based on current `main`.
- [ ] Consumers and compatibility impact checked.
- [ ] Contract tests added/updated without weakening existing assertions.
- [ ] Ruff passes.
- [ ] Deterministic Python suite passes.
- [ ] JavaScript suite passes.
- [ ] Required Pyright scope passes.
- [ ] CodeQL checks pass.
- [ ] Package and architecture docs are current.
- [ ] Applicable roadmap row is updated; acceptance evidence, deferred work and dependencies are recorded.
- [ ] Previously merged roadmap rows are reconciled with merge SHA/date.
- [ ] Manual/live checks are reported honestly.
