# CI quality roadmap

## Required pull-request checks

The following deterministic checks remain required for every pull request:

- Ruff lint.
- Python tests, excluding the `real_llm` marker (live Ollama dependency).
- JavaScript integration tests.

A green deterministic pipeline does not replace the manual SillyTavern smoke test or live-provider validation.

## Coverage baseline

The Python test job now collects line and branch coverage and publishes `coverage.xml` as a short-lived workflow artifact.

Coverage is report-only at this stage:

- No minimum percentage is enforced.
- Existing uncovered code is recorded as baseline debt, not treated as a reason to block unrelated work.
- Do not lower test assertions or remove tests to improve the percentage.
- Establish a stable baseline before proposing a threshold. Any future threshold should prevent newly introduced coverage debt rather than require an immediate repository-wide cleanup.

## Planned static-quality rollout

1. **Coverage baseline** — collect reproducible line and branch coverage (current step).
2. **Pyright** — establish a baseline, classify existing findings, then gradually enforce clean scopes.
3. **CodeQL** — add repository security analysis and review alerts before introducing blocking policy.
4. **SonarQube (optional)** — evaluate only if it adds actionable signal beyond Ruff, Pyright, tests, coverage and CodeQL.

New quality checks should initially be informational where the repository has inherited findings. Promote them to required checks only after the baseline is understood and the workflow is stable.

## CI constraints

- CI must not require a running Ollama instance.
- Keep Ruff, deterministic Python tests and JavaScript tests as required checks.
- Fix regressions on the same PR branch; do not merge with failing required checks.
- Keep quality-tool adoption incremental and avoid unrelated application changes.
