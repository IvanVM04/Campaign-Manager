# PR #271 — complete semantic evaluation contracts

**Status:** active implementation; resumable checkpoint.  
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

### WP1 — Gap inventory and scoring design
- [x] Inspect language, compound-intent and semantic-frame gold contracts.
- [x] Identify missing exact step-count checks in the general language holdout.
- [x] Identify extra/duplicate frame, argument and relation false-positive gaps.
- [ ] Define canonical slot signatures and matching semantics for arguments and relations.
- [ ] Decide whether every absence is explicitly gold or remains unmeasured; never assume unannotated fields are empty.

### WP2 — Shared scoring contracts
- [ ] Add a reusable scorer for ordered Intent steps and global category/active-step/clarification fields.
- [ ] Make exact step count mandatory where the corpus gold defines it.
- [ ] Score actor, modality, polarity, reported outcome and attribution only where gold exists.
- [ ] Score semantic frame count/family/predicate/arguments using multiset matching.
- [ ] Score relation claim count/direction/predicate/family/polarity/modality/attribution/temporal fields using multiset matching.
- [ ] Ensure extra and duplicate predictions become FP, missing gold becomes FN.
- [ ] Keep unknown/unannotated fields unmeasured rather than treating them as correct.

### WP3 — Stable metric/report schema
- [ ] Define a versioned metric schema with per-family TP/FP/FN, precision, recall and F1.
- [ ] Publish exact-case accuracy and step-count accuracy separately from slot metrics.
- [ ] Publish per-field/per-family denominators, including zero/unmeasured denominators.
- [ ] Add latency P50/P95 if reliable observations are available in the current harness; otherwise document as deferred.
- [ ] Preserve content-free report allowlists and reject sensitive provider strings.

### WP4 — Offline tests and corpus integrity
- [ ] Add fake-analysis tests for missing, extra, duplicate, swapped, direction-inverted and wrong-attribution outputs.
- [ ] Add zero-denominator and missing-analysis tests.
- [ ] Prove held-out fixtures remain immutable and gold sidecars stay text-free.
- [ ] Prove evaluation-only gold is not embedded in the Intent prompt.
- [ ] Keep existing compound scorer behavior and add parity tests.

### WP5 — Live harness integration and documentation
- [ ] Integrate shared scoring into existing real-LLM harnesses without requiring Ollama during CI.
- [ ] Ensure provider errors are scored as misses and not silently omitted.
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
- Last completed work package:
- Last commit:
- Files changed:
- Tests run and results:
- Known blockers / next exact action:
