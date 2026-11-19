# PR #271 — complete semantic evaluation contracts

**Status:** active implementation; resumable checkpoint. PR [#271](https://github.com/IvanVM04/Campaign-Manager/pull/271) is open as draft.  
**Branch:** `quality/semantic-evaluation-contracts-pr271`  
**Base:** `main` at `c11e0541b855bcde24a8d86616d9e384a3ebda8c` (PR #270 merged).  
**Scope:** evaluation/tests/fixtures/documentation only; no production prompt, model schema, resolver, mechanics or world-write changes planned.

> Resume rule: before creating another branch or PR for #271, inspect this file and the existing branch/PR. If this branch exists, continue from its latest head and only complete unchecked work. Do not reset, recreate or overwrite already-implemented work.

## Objective

Make semantic evaluation reliable enough to compare prompt/model/parser changes without optimistic scoring. A response must be penalized for omitted and extra steps, arguments, frames and relation claims. Scoring must publish explicit TP/FP/FN denominators and independent per-family metrics. A missing gold annotation is not a passing field.

## Verified gaps on the base commit

- `tests/test_real_llm_semantic_holdout.py::_score_language_scenario` checks category/active-step/clarification and only explicitly named `step`, `first_step`, and `later_step` fields. It does not enforce exact step count, so extra steps can pass.
- `tests/semantic_frame_evaluation.py::score_semantic_frame_scenario` checks that at least one expected frame/claim/argument exists. It does not fully penalize extra frames, extra arguments, extra relation claims or duplicate semantic slots.
- `tests/compound_intent_evaluation.py::score_compound_intent_analysis` already checks exact step count and per-step actor/modality/polarity; preserve this behavior and extend coverage only where independent gold exists.
- Predicate surface scoring exists separately through `semantic_frame_predicate_gold_v1.json`; integrate it into the same versioned metric contract without merging prompt/holdout data.
- `SemanticEvaluationLedger.record_semantic_slots` already uses multiset TP/FP/FN, but the live scorers do not consistently submit complete predicted and expected slot sets.

## Non-negotiable constraints

1. Do not change utterance text or expected values in existing held-out corpus files to make tests pass.
2. Do not copy held-out utterances or gold labels into prompts, few-shot examples or production code.
3. Keep corpus text and entity IDs out of persisted reports. Reports may contain only fixed metric names, counts, ratios, scenario IDs where already allowed by test output policy, model/runtime metadata and allowlisted numeric usage.
4. Missing provider/decoder output is a scored miss for every gold dimension, not a skipped case.
5. Extra predictions and duplicates count as false positives; missing predictions count as false negatives.
6. Precision/recall/F1 with zero denominator must be `null` (not a fabricated 100%). For a family with gold but no predictions, recall/F1 are 0.
7. Preserve the current single LLM call and production contracts. This PR changes evaluation, not model behaviour.
8. Preserve backwards-compatible report consumers where possible; version new metric structures explicitly.

## Work packages

### WP0 — Branch, specification and resumability
- [x] Verify PR #270 merged and read current main.
- [x] Confirm no existing PR/branch for this #271 task.
- [x] Create `quality/semantic-evaluation-contracts-pr271` from the exact main SHA above.
- [x] Add this durable checkpoint before implementation.
- [x] Open draft PR #271 and keep all work on its existing branch.

### WP1 — Gap inventory and scoring design
- [x] Inspect language, compound-intent and semantic-frame gold contracts.
- [x] Identify missing exact step-count checks in the general language holdout.
- [x] Identify extra/duplicate frame, argument and relation false-positive gaps.
- [x] Define canonical slot signatures and multiset matching semantics for arguments and relations.
- [x] Add explicit frame/relation presence-count gold for all 20 semantic-frame holdout cases; zero counts are explicit negative controls, while missing detailed annotations remain unmeasured.

### WP2 — Shared scoring contracts
- [x] Add a reusable scorer for ordered Intent steps and global category/active-step/clarification fields.
- [x] Make exact step count mandatory for all 35 general-language holdout cases using a text-free sidecar.
- [x] Score actor, modality, polarity, reported outcome and attribution only where gold exists.
- [x] Score semantic frame count/family/predicate/arguments using explicit counts and multiset matching.
- [x] Score relation claim count/direction/predicate/family/polarity/modality/attribution/temporal fields using explicit counts and field-level gold.
- [x] Ensure extra and duplicate predictions become FP, missing gold becomes FN.
- [x] Keep unknown/unannotated fields unmeasured rather than treating them as correct.

### WP3 — Stable metric/report schema
- [x] Define metric schema v1 with per-family TP/FP/FN, precision, recall and F1.
- [x] Publish exact-case accuracy and step-count accuracy separately from slot metrics.
- [x] Publish gold/prediction denominators, including zero/unmeasured values.
- [x] Add latency P50/P95 (nearest-rank) and sample counts.
- [x] Harden JSON reports to retain only bounded identifiers, fixed enums and non-negative numeric telemetry; reject untrusted provider strings.

### WP4 — Offline tests and corpus integrity
- [x] Add fake-analysis tests for missing/extra steps, duplicate/extra arguments, extra frames/claims, direction inversion, wrong family, attribution and temporal fields.
- [x] Add zero-denominator, missing-analysis and latency-percentile tests.
- [x] Prove step-count and frame-presence gold sidecars are text-free and cover their immutable holdouts.
- [x] Prove evaluation-only gold is not embedded in the Intent prompt.
- [x] Preserve compound scorer behavior and make exact-case accuracy fail on extra-step predictions.

### WP5 — Live harness integration and documentation
- [x] Integrate shared scoring into the general Intent and semantic-frame real-LLM harnesses without requiring Ollama during CI.
- [x] Ensure provider errors are scored as misses and not silently omitted.
- [x] Write a content-free language holdout JSON report through the existing report directory/path configuration.
- [ ] Update PR record, architecture roadmap and quality roadmap with exact metric definitions and commands.
- [ ] Run focused offline tests, Ruff, Pyright and full deterministic CI.
- [ ] Confirm no production files or prompts changed.

### WP6 — Review and completion
- [ ] Inspect final diff for fixture/prompt leakage and accidental denominator changes.
- [ ] Verify branch and CI state.
- [ ] Open/update the #271 PR and leave this checkpoint current.

## Decisions log

- 2026-11-19: #270 was merged; implementation begins from main SHA `c11e0541b855bcde24a8d86616d9e384a3ebda8c`.
- 2026-11-19: PR #271 is the evaluation-contract milestone. PR #272 remains the optional NLP pilot, #273 uncertainty/checkpoints, and #274 live acceptance.

## Resumption notes

Update this section after each implementation batch:
- Last completed work package: WP0–WP4 complete; WP5 partially complete. WP6 pending.
- Last commit: `d6f498af7e87ffc3e00f3d2f56adb17e64c03809`.
- Files changed: checkpoint, two text-free gold sidecars, Intent scorer, semantic-frame scorer, metric ledger, safe report builder, compound scorer, live harnesses and offline tests.
- Tests run and results: no full run has yet completed on the current head. An earlier lint run found two RUF059 unused-variable errors in the Intent harness; fixed in `992c438`. Subsequent runs were cancelled by newer pushes. Current CI run on this checkpoint SHA `d6f498a` is in progress: Tests [44557775808](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44557775808), CodeQL [44557775805](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44557775805).
- Known blockers / next exact action: wait for current CI. Inspect failure logs, fix any Ruff/Pyright/Python test regressions, update this checkpoint to the new head, then add evaluator/roadmap documentation and complete final diff review. Do not run Ollama live as part of deterministic CI.
