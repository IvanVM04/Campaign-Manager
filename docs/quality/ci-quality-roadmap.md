# CI quality roadmap

## Required pull-request checks

The following deterministic checks remain required for every pull request:

- Ruff lint.
- Python tests, excluding the real_llm marker (live Ollama dependency).
- JavaScript integration tests.
- Pyright for the clean `models`, `rules_engine`, `bootstrap` and `operations` scopes.

A green deterministic pipeline does not replace the manual SillyTavern smoke test or live-provider validation.

## Coverage baseline

The Python test job collects line and branch coverage and publishes coverage.xml as a short-lived workflow artifact.

Coverage is report-only at this stage:

- No minimum percentage is enforced.
- Existing uncovered code is recorded as baseline debt, not treated as a reason to block unrelated work.
- Do not lower test assertions or remove tests to improve the percentage.
- Establish a stable baseline before proposing a threshold. Any future threshold should prevent newly introduced coverage debt rather than require an immediate repository-wide cleanup.

## Pyright baseline and progressive enforcement

Pyright runs in two scopes:

- **Required:** `pyright models rules_engine bootstrap operations`. These scopes currently have no baseline diagnostics and are checked together as the first blocking type-checking boundary.
- **Informational:** repository-wide first-party application scope (API, bootstrap, models, operations, repositories, rules engine and services). Diagnostics are collected as JSON and published as a short-lived workflow artifact.

The version is pinned in the development dependency group. Do not suppress diagnostics globally or change runtime behavior merely to make reports smaller. Expand the required scope package by package only after fixing its existing diagnostics and validating the same command in CI.

The original repository-wide report is classified in [pyright-baseline-2026-11-11.md](pyright-baseline-2026-11-11.md): 98 errors across 27 files. It is a historical snapshot, not a current count. Do not introduce repository-wide strict mode until the current typing baseline and dependency stubs are understood.

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
5. Improve coverage quality and introduce incremental thresholds only after reviewing the baseline.
6. SonarQube (optional) — evaluate only if it adds actionable signal beyond Ruff, Pyright, tests, coverage and CodeQL.

New quality checks should initially be informational where the repository has inherited findings. Promote them to required checks only after the baseline is understood and the workflow is stable.

## CI constraints

- CI must not require a running Ollama instance.
- Keep Ruff, deterministic Python tests, JavaScript tests and clean scoped Pyright checks required.
- Fix regressions on the same PR branch; do not merge with failing required checks.
- Keep quality-tool adoption incremental and avoid unrelated application changes.
