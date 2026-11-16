# PR #244 — Durable LLM workflow hardening

## Mission

Harden the already implemented intent/correction workflows without expanding semantic understanding, adding new speech-act categories, or broadening the correction prompt. The scope is correctness of existing contracts, candidate selection, evidence boundaries, state transitions, and regression coverage.

## Branch and base

- Branch: `hardening/pr244-durable-llm-workflow-contracts`
- Base branch: `main`
- Audited base commit: `54552127951a58b11c48183bce0a5ac9fe2cc282`
- Intended PR: #244
- Related merged work: PRs #237–#243, especially #240 (atomic selectors), #242 (backend slot catalogue), and #243 (linked-slot deduplication).

## Audited failure surfaces

1. **Evidence boundary drift.** The interpreter validated a correction against the latest answer, but the turn-planning layer applied it again against accumulated conversation evidence. A historical sentence could therefore satisfy the second validation boundary.
2. **Mutable candidate universe within one response.** Correction payloads were decoded against an analysis that was progressively modified by previous corrections. Candidate availability can change as relation links and shared projections change.
3. **Weak second-boundary assertion.** The planner checked whether each replacement appeared somewhere in the returned analysis. That did not prove that the returned object contained only the requested typed edits.
4. **Over-broad relation patch projection.** A relation endpoint selector addresses one claim, but the patch could also rewrite step-level targets, action arguments and action text when the same mention occurred in multiple claims.
5. **Batch collision risk.** Multiple edits to the same normalized mention, duplicate replacements, or replacements already present elsewhere in the same step can create ambiguous or inconsistent projections.

## Implemented hardening

- Added a single typed batch-application boundary, `apply_pending_intent_corrections`.
- Resolve every selector against one immutable catalogue built from the initial pending analysis.
- Apply corrections to a private staged analysis; return only after the entire batch succeeds.
- Reject duplicate/overlapping edits, repeated replacements, existing-target collisions and replacement-to-another-selected-slot overlaps.
- Require the current challenge answer (not cumulative evidence) at both interpreter and turn-planning validation boundaries.
- Compare the complete provider-returned analysis with the deterministic result of applying the typed batch, allowing only the existing clarification flags to differ.
- Scope relation-endpoint corrections to their selected claim when matching mentions are repeated. Synchronize the step-wide projection only when the mention is unique in the relation claims, target mentions, action arguments and action text.
- Add deterministic tests for multi-edit batches, candidate-catalogue drift, repeated relation mentions, stale evidence, replacement collisions and untyped provider mutations.

## Non-goals

- No new semantic capabilities or categories.
- No broader correction prompt or additional world/discourse retrieval.
- No authorization of mechanics or world writes through correction metadata.
- No change to how normal (non-pending) intent interpretation works.
- No claim that an LLM is deterministic or infallible.

## Validation plan

Run from the repository root:

```powershell
python -m pytest tests/test_pending_intent_correction.py tests/test_pending_intent_correction_flow.py tests/test_modular_language_pipeline.py -q
ruff check .
pyright models rules_engine bootstrap operations
python -m pytest -m "not real_llm" --cov --cov-report=term-missing --cov-report=xml
python -m coverage report
```

Then rerun the live Ollama correction holdout with the same model and settings used for the reported 6/7 baseline:

```powershell
python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -k "pending_multi_turn_correction_holdout" -v -s --junitxml=.pr244-correction-metrics.xml 2>&1 | Tee-Object -FilePath .\pr244-correction.log
```

Keep the complete log and JUnit XML. Record per-scenario results, provider model, duration and failure cause. Do not treat deterministic CI as a substitute for the live Ollama run.

## Resume guide

1. Fetch and check out `hardening/pr244-durable-llm-workflow-contracts`.
2. Read this document first, then inspect the current PR diff and latest CI run.
3. Continue from the unfinished checklist below; do not restart or overwrite already completed work.
4. After each additional patch, run the focused correction tests before expanding to repository-wide checks.
5. Never merge while the live Ollama holdout or required CI checks are failing.

### Completion checklist

- [x] Audit PR #237–#243 and identify concrete correction-workflow risks.
- [x] Create an isolated branch from current main.
- [x] Fix latest-answer evidence revalidation at the planner boundary.
- [x] Freeze candidate selection to the initial pending-analysis snapshot.
- [x] Add atomic batch validation and collision rejection.
- [x] Require exact full-analysis equality after typed correction application.
- [x] Prevent one relation selector from editing repeated linked references.
- [x] Add deterministic unit and integration regressions.
- [ ] Run focused tests, Ruff and Pyright.
- [ ] Run full deterministic suite and enforce coverage floor.
- [ ] Run the seven-scenario Ollama holdout and record the result.
- [ ] Review PR diff for accidental semantic/prompt changes.
- [ ] Finalize PR description and request review.

## Execution log

### 2026-11-16 — initial hardening pass

- Confirmed the hardening branch points at the latest main commit after PR #243.
- Identified the historical-evidence revalidation mismatch and mutable-catalogue batch path.
- Implemented the initial model, interpreter, planner and regression-test changes described above.
- Remote test execution has not yet been performed. Do not mark CI or Ollama validation complete until the actual runs are inspected.
