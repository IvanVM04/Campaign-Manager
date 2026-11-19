# PR #272 — optional offline NLP pilot

**Status:** active implementation; resumable checkpoint.  
**Branch:** quality/offline-nlp-pilot-pr272  
**PR:** [#272](https://github.com/IvanVM04/Campaign-Manager/pull/272), open as draft.  
**Base:** main at 9de344d4d36fdfc325c91f34075553d6076f2fc0 (PR #271 merged).  
**Current scope:** optional Stanza pilot, offline evaluation, test-only/live opt-in comparison scaffolding, documentation closure of #271. No default dependency and no production prompt/normalization/resolver/mechanics/world-write integration.

> Resume rule: before creating another branch or PR for #272, inspect this checkpoint and the existing PR/branch. If it exists, continue from its latest head and only complete unchecked work. Do not reset, recreate or overwrite implemented work.

## Objective

Run an evidence-based, optional Spanish-first NLP pilot after #271 fixed evaluation denominators. Test whether Stanza UD tokenization/POS/lemma/dependency hints can help the existing coherent Intent model without gaining authority. Decide whether a library belongs in production only after reproducible semantic quality, latency, memory/package footprint, offline installation and licensing have been reviewed.

## PR #271 carry-over — completed in this branch

- [x] Verify #271 is merged and its final CI is green.
- [x] Reconcile the stale #271 checkpoint with final status, merge SHA, test count, coverage and CI links.
- [x] Update architecture ADR and current quality roadmap to mark #271 integrated and #272 active.
- [x] Add a #271 closure record with metric schema/commands and verify original holdout files were not changed by #271.
- [x] Complete the documentation carry-over.

Final #271 verification: merge commit 9de344d4d36fdfc325c91f34075553d6076f2fc0; PR head a669d194462cced1ab2994a96ce60f25a4250b8; 2,204 passed, 22 real_llm deselected, 85.23% coverage; Ruff, both Pyright scopes, JS, CodeQL and CI summary passed. Evidence: Tests #44559085820 and CodeQL #44559085674.

## Pilot decisions

- Stanza 1.15.1 is the first runnable candidate; it stays optional and lazily imported.
- spaCy's Python package is MIT, but the current Spanish es_core_news_sm model is marked GPL-3.0; model licensing is reviewed separately. Its training domain is news, unlike the campaign's conversational/fantasy domain.
- Never install either library into default runtime dependencies.
- No model download at application startup. Model acquisition is explicit via the download helper.
- Start CPU-only; no GPU/CUDA assumptions.
- Parser output is an untrusted hint tied to exact current-message spans. It may not generate canonical IDs, infer permissions, write to the world, replace source evidence or make an action mechanically active.
- Existing production Intent call count, prompt, schema and normalization remain unchanged. The hint provider decorator exists only in test support and is used only by the opt-in A/B test.
- Held-out utterances and gold labels are never copied into prompts or tuning rules.
- A parser error is marked unavailable, not counted as a predicted negative cue.

## Work packages

### WP0 — Resume, branch and evaluation baseline
- [x] Verify #271 merged.
- [x] Verify final #271 CI: 2,204 deterministic tests pass, 22 real_llm deselected, 85.23% coverage; all gates green.
- [x] Create this branch from latest main.
- [x] Add resumability checkpoint.
- [x] Open draft PR #272.
- [x] Record #271 report schema, validation and closure in the ADR/quality roadmap/closure record.

### WP1 — Candidate and licensing/footprint assessment
- [x] Inspect Stanza and spaCy candidates and Spanish models.
- [x] Choose Stanza as optional candidate; record spaCy Spanish model GPL-3.0 as a separate license concern.
- [x] Pin stanza==1.15.1 in the opt-in nlp-pilot dependency group only.
- [x] Document explicit model download, cache directory, CPU-only policy, offline mode and commands.
- [ ] Measure the actual installed model directory size on the target machine; no unmeasured size is asserted here.

### WP2 — Typed adapter boundary
- [x] Add immutable parser document/sentence/word contracts with exact source offsets, lemma, UPOS/XPOS, morphology, dependency label and head index.
- [x] Add a lazy Stanza adapter with injected pipeline support for tests.
- [x] Validate input size, sentence/word bounds, exact token surfaces/offsets and local dependency indices.
- [x] Expose only untrusted linguistic hints; no entity IDs, actor authority, action family, permissions or outcomes.
- [x] Add bounded, content-free parser metadata and prompt-hint serialization.
- [x] Truncate oversized hint payloads deterministically and mark truncation.

### WP3 — Parser-only offline baseline
- [x] Add a reproducible offline runner over development and held-out language corpora.
- [x] Report parse coverage/errors, token counts, lemma/POS/dependency coverage, wall/CPU latency P50/P95 and local model-directory size.
- [x] Score only binary gold-supported utterance-level negation/conditional cue probes against a lexical baseline.
- [x] Keep parser-only cue metrics separate from #271 step-level semantic metrics with explicit denominators.
- [x] Count failed parser executions as unavailable rather than false negatives.
- [ ] Run the benchmark with an actual locally installed Stanza Spanish model and retain its aggregate report. It has not been run in this environment.

### WP4 — Model + parser-hint comparison harness
- [x] Add opt-in real_llm/nlp_pilot test comparing unchanged Intent against an evaluation-only provider decorator with Stanza hints.
- [x] Score both variants with #271's shared scorer on identical utterances/gold.
- [x] Separate parser latency from model call latency and provider telemetry by variant.
- [x] Keep production prompt/schema/call count unchanged.
- [x] Keep real provider calls out of deterministic CI and test provider wrapper with fake providers.
- [ ] Run the opt-in A/B locally against the configured Ollama model. It has not been run and no quality improvement is claimed.

### WP5 — Contracts, privacy and docs
- [x] Unit tests for adapter mapping, multiword token spans, mismatched offsets, invalid heads, optional-dependency absence, empty/oversized input, hint serialization, parse failures and privacy.
- [x] Update ADR, quality roadmap and #271 closure record.
- [x] Add this developer runbook with install/download/offline/live commands.
- [x] Keep reports content-free: no utterances, raw tokens, lemmas or entity names.

### WP6 — Validation and decision
- [ ] Run focused offline tests, Ruff, Pyright and full deterministic CI on this branch.
- [ ] Inspect diff for no prompt/production runtime integration and no default dependency changes.
- [ ] Complete actual Stanza benchmark report and decide whether Stanza remains experiment-only or merits a later production proposal.
- [ ] Keep PR as draft until deterministic gates pass; do not merge based only on structural tests.

## Acceptance criteria

1. Default install and application startup remain unchanged if Stanza is absent.
2. All parsed source offsets match exact token surfaces; no fuzzy text search is used to fabricate offsets.
3. Every hint is traceable to current player text and has no canonical identity/authority.
4. Reports never contain user utterances, mention strings, entity names, lemmas or raw token arrays.
5. Held-out text/gold is not embedded in prompts or changed to improve results.
6. Offline benchmark reports denominators and latency, not a single weighted score.
7. Stanza is not promoted into default production dependencies without measured net semantic improvement and separate approval.

## Runbook

See docs/quality/nlp-pilot-runbook.md for the explicit installation, model download, offline runner and opt-in A/B commands.

## External assessment sources

- Stanza package/license/version: https://pypi.org/project/stanza/
- Stanza Spanish models/processors and offline configuration: https://stanfordnlp.github.io/stanza/download_models.html and https://stanfordnlp.github.io/stanza/available_models.html
- Stanza Spanish model card (Apache-2.0): https://huggingface.co/stanfordnlp/stanza-es
- spaCy package (MIT) vs Spanish model (GPL-3.0): https://pypi.org/project/spacy/ and https://huggingface.co/spacy/es_core_news_sm

## Resumption notes

- Last completed work package: WP0, WP2, WP3, WP4 scaffolding and WP5 complete; WP1 measurement and WP6 remain.
- Last commit: update this field when a validation batch is pushed.
- Files changed: #271 closure record/checkpoint reconciliation, architecture ADR, quality roadmap, Stanza contracts/adapter/probes, optional dependency group, download/benchmark scripts, fake-provider support, offline tests, opt-in live A/B test and runbook.
- Tests run and results: no complete #272 CI run yet. #271 final CI is green (2,204 passed, 22 deselected, 85.23% coverage). The actual Stanza model is not downloaded or run in this environment.
- Known blockers / next exact action: run Ruff/Pyright/Python tests on current head, fix failures, inspect current diff and keep PR draft until CI is green. Then run the optional offline Stanza benchmark and the guarded Ollama A/B on the target machine; record results without exposing utterance text.
