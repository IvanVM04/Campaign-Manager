# CI quality roadmap

## Workflow checks vs merge enforcement

The active default-branch ruleset requires `CI summary`, `Analyze (python)` and `Analyze (javascript-typescript)`. The aggregate CI summary includes deterministic Python tests, Ruff, repository-wide Pyright and JavaScript tests; CodeQL language analyses are independently required. This supersedes the earlier empty-ruleset finding in older audit snapshots. See [the CI audit](ci-audit-2026-11-11.md).

The following checks are expected to pass on every implementation pull request and should be configured as required status checks:

- Ruff lint.
- Python tests, excluding the real_llm marker (live Ollama dependency).
- JavaScript integration tests.
- Pyright for the clean `models`, `rules_engine`, `bootstrap` and `operations` scopes.

A green deterministic pipeline does not replace the manual SillyTavern smoke test or live-provider validation.

## Coverage baseline

The Python test job collects line and branch coverage and publishes coverage.xml as a short-lived workflow artifact.

The 85% combined line/branch gate is now blocking and has passed in CI. The latest main artifact (2026-11-12, commit `96b0232`) measured 86.8% line coverage, 73.6% branch coverage and 83.4% combined line/branch coverage. PR #209's successful deterministic run (commit `f06d764`, run `43283240982`) reports 89.3% line coverage, 76.3% branch coverage and 85.98% combined coverage, with 1,539 tests passed and 4 opt-in real-LLM tests deselected.

- The 85% combined line/branch target is now enforced by `[tool.coverage.report].fail_under = 85`.
- Branch coverage remains enabled; the combined figure is the same line-plus-branch metric reported by coverage.py.
- Do not exclude production modules, lower assertions or remove tests to improve the percentage.
- Use package and file-level reports to prioritize risk: remaining candidates include API integration edge cases, durable manual-roll recovery branches and rules-engine condition restrictions.

## Pyright baseline and progressive enforcement

Pyright runs in two scopes:

- **Required:** `pyright models rules_engine bootstrap operations`. These scopes currently have no baseline diagnostics and are checked together as the first blocking type-checking boundary.
- **Informational:** repository-wide first-party application scope (API, bootstrap, models, operations, repositories, rules engine and services). Diagnostics are collected as JSON and published as a short-lived workflow artifact.

Pyright 1.1.414 is pinned in the development dependency group. Do not suppress diagnostics globally or change runtime behavior merely to make reports smaller. Expand the required scope package by package only after fixing its existing diagnostics and validating the same command in CI.

The original repository-wide report is classified in [pyright-baseline-2026-11-11.md](pyright-baseline-2026-11-11.md): 98 errors across 27 files. The latest observed run on 2026-11-11 reports 91 errors; see [the CI audit](ci-audit-2026-11-11.md). The original report is a historical snapshot, not a current count. Do not introduce repository-wide strict mode until the current typing baseline and dependency stubs are understood.

## Security analysis and dependency maintenance

- CodeQL analyzes Python and JavaScript/TypeScript on pull requests, pushes to main and a weekly schedule.
- CodeQL uses the extended security query suite; alerts are reviewed before any blocking security policy is introduced.
- Dependabot checks GitHub Actions, Python and npm dependencies weekly. Related updates are grouped to avoid excessive PR noise.
- Dependency updates still require the normal deterministic CI checks and human review.

## Planned static-quality rollout

1. Coverage baseline — collect reproducible line and branch coverage (implemented).
2. Pyright baseline — collect and classify existing type diagnostics (implemented).
3. CodeQL — add repository security analysis (workflow added; review alerts before introducing blocking policy).
4. Expand blocking Pyright scope incrementally; `models` is now included after resolving its five baseline diagnostics.
5. **Enforced:** 85% combined line/branch coverage with branch coverage enabled; the CI test job fails below `fail_under = 85`.
6. SonarQube (optional) — evaluate only if it adds actionable signal beyond Ruff, Pyright, tests, coverage and CodeQL.

New quality checks should initially be informational where the repository has inherited findings. Promote them to required checks only after the baseline is understood and the workflow is stable.

## CI constraints

- CI must not require a running Ollama instance.
- After the repository ruleset is updated, keep Ruff, deterministic Python tests, JavaScript tests, clean scoped Pyright and CodeQL checks required.
- Fix regressions on the same PR branch; do not merge with failing, pending or cancelled applicable checks.
- Keep quality-tool adoption incremental and avoid unrelated application changes.
