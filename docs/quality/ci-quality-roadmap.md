# CI quality roadmap

## Required pull-request checks

The following deterministic checks remain required for every pull request:

- Ruff lint.
- Python tests, excluding the real_llm marker (live Ollama dependency).
- JavaScript integration tests.

A green deterministic pipeline does not replace the manual SillyTavern smoke test or live-provider validation.

## Coverage baseline

The Python test job collects line and branch coverage and publishes coverage.xml as a short-lived workflow artifact.

Coverage is report-only at this stage:

- No minimum percentage is enforced.
- Existing uncovered code is recorded as baseline debt, not treated as a reason to block unrelated work.
- Do not lower test assertions or remove tests to improve the percentage.
- Establish a stable baseline before proposing a threshold. Any future threshold should prevent newly introduced coverage debt rather than require an immediate repository-wide cleanup.

## Pyright baseline

Pyright runs in an informational CI job against first-party application code (API, bootstrap, models, operations, repositories, rules engine and services).

- The version is pinned in the development dependency group.
- Diagnostics are collected as JSON and published as a short-lived workflow artifact.
- Existing type errors do not block pull requests while the baseline is being assessed.
- Tool/configuration failures remain visible in the job result.
- Do not suppress diagnostics globally or change runtime behavior merely to make the initial report smaller.

The first report has been classified in [pyright-baseline-2026-11-11.md](pyright-baseline-2026-11-11.md): 98 errors across 27 files, concentrated in services and repositories. The next step is to fix and verify a small clean package scope before making any Pyright diagnostics blocking. Do not introduce a repository-wide strict mode until the current typing baseline and dependency stubs are understood.

## Security analysis and dependency maintenance

- CodeQL analyzes Python and JavaScript/TypeScript on pull requests, pushes to main and a weekly schedule.
- CodeQL uses the extended security query suite; alerts are reviewed before any blocking security policy is introduced.
- Dependabot checks GitHub Actions, Python and npm dependencies weekly. Related updates are grouped to avoid excessive PR noise.
- Dependency updates still require the normal deterministic CI checks and human review.

## Planned static-quality rollout

1. Coverage baseline — collect reproducible line and branch coverage (implemented).
2. Pyright baseline — collect and classify existing type diagnostics (implemented; see the dated report).
3. CodeQL — add repository security analysis (workflow added; review alerts before introducing blocking policy).
4. SonarQube (optional) — evaluate only if it adds actionable signal beyond Ruff, Pyright, tests, coverage and CodeQL.

New quality checks should initially be informational where the repository has inherited findings. Promote them to required checks only after the baseline is understood and the workflow is stable.

## CI constraints

- CI must not require a running Ollama instance.
- Keep Ruff, deterministic Python tests and JavaScript tests as required checks.
- Fix regressions on the same PR branch; do not merge with failing required checks.
- Keep quality-tool adoption incremental and avoid unrelated application changes.
