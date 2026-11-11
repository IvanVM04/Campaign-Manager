# Repository guidance for coding agents

Read this file before making repository changes.

## Start here

1. Read [the documentation hub](docs/README.md).
2. Read [the current architecture audit](docs/architecture/architecture-audit-2026-11-11.md).
3. Read [the capability dependency matrix](docs/architecture/package-dependency-matrix.md).
4. Read the relevant package `README.md` before changing a capability.
5. Read [the CI audit](docs/quality/ci-audit-2026-11-11.md) and [test-suite audit](docs/quality/test-suite-audit-2026-11-11.md) before changing quality gates or tests.

Dated audits are historical snapshots. Use the newest current audit and inspect source before treating an old recommendation as pending.

## Working agreement

- Keep one active implementation branch and one open PR at a time.
- Start every PR from the latest integrated `main`.
- Keep each PR focused on one architectural or quality objective.
- Do not merge while any applicable CI check is failing, pending or cancelled.
- Fix failures on the same PR branch; do not create a follow-up PR to work around a known failure.
- Do not use auto-merge as a substitute for reviewing checks and the diff.
- Do not add gameplay features while the active objective is CI, architecture, legacy cleanup, prompt quality or test maintenance.
- Do not claim a live Ollama/SillyTavern smoke test passed unless it was actually run.

The repository ruleset currently requires pull requests and thread resolution, but its required-status-check list is empty. This is an administrative merge-protection gap, not a reason to relax the working agreement. See the CI audit.

## Required validation

For implementation and test changes, run the checks applicable to the changed scope:

```bash
ruff check .
python -m pytest -m "not real_llm" --cov --cov-report=term-missing --cov-report=xml
npm run test:js
pyright models rules_engine bootstrap operations
```

CodeQL analyzes Python and JavaScript/TypeScript on pull requests, pushes to `main` and its weekly schedule. The repository-wide Pyright report is informational while its baseline is reduced. Live-provider tests are marked `real_llm` and are not part of deterministic CI.

A green CI run does not prove that a manual SillyTavern session or live LLM call works. Report those separately.

## Architecture constraints

- Preserve the modular-monolith design. Do not introduce microservices, a message bus, a vector database, distributed locks or generic infrastructure frameworks without a demonstrated requirement.
- Treat `bootstrap/campaign_runtime.py` as the composition root.
- API routers are transport adapters; do not make them compose runtimes or own domain workflows.
- Respect [the package dependency matrix](docs/architecture/package-dependency-matrix.md). Update the matrix and architecture tests in the same PR when a new service dependency is justified.
- Import from canonical capability packages. Do not restore flat compatibility shims or old exports.
- Keep deterministic rules/mechanics, semantic validation, persistence and LLM proposal generation as separate authorities.
- LLM output is untrusted input. It may propose operations but must never write directly to SQLite or bypass domain validation.
- Preserve turn idempotency, campaign revision checks, lease fencing, short atomic commit boundaries and narration recovery.
- Do not remove `POST /integration/turn`, `LegacySillyTavernTurnService`, `WorldSnapshotRepository` or `turns.snapshot` until the external-client usage and data-retention gates are satisfied.

## LLM context and prompt constraints

- Keep static instructions separate from typed context data.
- The structured proposal prompt must not be built by parsing or editing the legacy narrative-extraction prompt. PR #161 completed this decoupling.
- The structured proposal context still needs relevance selection and a bounded model-token budget. Coordinate this at the turn/application boundary; `services/llm_world` must not import `services.context` directly.
- Preserve mandatory facts, permissions, current character/scene state and confirmed mechanics. Never solve prompt size by arbitrary string truncation.
- Keep repair attempts bounded and model output strictly validated.

## Test-suite maintenance

- Tests document observable contracts. Never remove a test only because it is small, old, slow-looking or in a large file.
- Remove legacy tests in the same PR as the implementation they protect, after verifying all consumers.
- When splitting a test module, preserve fixtures, assertions, parameterization and failure-path coverage.
- Keep migration tests for supported historical schema upgrades.
- Keep deterministic CI independent of Ollama and external network services.
- Prefer tests at the narrowest useful boundary, retaining integration tests for cross-component guarantees.

## Documentation requirements

- Update the relevant package `README.md` when ownership, public exports or dependencies change.
- Update current architecture/quality audits when a finding is fixed or a new one is confirmed.
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
- [ ] Manual/live checks are reported honestly.
