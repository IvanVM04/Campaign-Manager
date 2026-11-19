# PR #272 — optional offline NLP pilot

**Status:** active implementation; resumable checkpoint.
**Branch:** quality/offline-nlp-pilot-pr272
**Base:** main at 9de344d4d36fdfc325c91f34075553d6076f2fc0 (PR #271 merged).
**PR #271:** merged; final deterministic CI success on head a669d194462cced1ab2994a96ce60f25a4250b8 (2,204 passed, 22 real_llm deselected, 85.23% coverage; Ruff, both Pyright scopes, JS and CodeQL all green).
**Scope:** optional Stanza pilot, offline evaluation, test-only/live opt-in comparison scaffolding, documentation closure of #271. No default dependency and no production prompt/normalization/resolver/mechanics/world-write integration.

> Resume rule: before creating another branch or PR for #272, inspect this checkpoint and the existing PR/branch. If it exists, continue from its latest head and only complete unchecked work. Do not reset, recreate or overwrite implemented work.

## Objective

Run an evidence-based, optional Spanish-first NLP pilot after #271 fixed evaluation denominators. Test whether Stanza UD tokenization/POS/lemma/dependency hints can help the existing coherent Intent model without gaining authority. Decide whether a library belongs in production only after reproducible semantic quality, latency, memory/package footprint, offline installation and licensing have been reviewed.

## PR #271 carry-over to close here
- [x] Verify #271 is merged and its final CI is green.
- [ ] Reconcile the stale #271 checkpoint: final status, merged SHA, test count, coverage and CI links.
- [ ] Update the architecture ADR and current quality roadmap to mark #271 integrated and #272 active.
- [ ] Add a short #271 closure record with metric schema/commands and confirm original holdout files were not changed by #271.
- [ ] Final diff review of #271 carry-over docs.

## Pilot decisions
- Stanza is the first runnable candidate because its Python package and Spanish model card are Apache-2.0. Keep it optional and lazily imported.
- Do not bundle spaCy's Spanish model by default: spaCy itself is MIT, but the current Spanish es_core_news_sm model is marked GPL-3.0; model licensing must be reviewed separately from library licensing. Its training domain is news, not the campaign's primary conversational/fantasy domain.
- Never install either library into the default runtime dependency set.
- No model download at application startup. Model acquisition is an explicit local developer action.
- Start CPU-only; avoid GPU/CUDA assumptions.
- Parser output is a hint tied to exact current-message spans. It may not generate canonical IDs, infer permissions, write to the world, replace source evidence or make an action mechanically active.
- Existing production Intent call count and prompt remain unchanged. Any hint prompt is test-only and behind an explicit opt-in live test.
- Held-out utterances and gold labels are never copied into prompts or tuning rules.

## Work packages

### WP0 — Resume, branch and evaluation baseline
- [x] Verify #271 merged.
- [x] Verify final CI: 2,204 deterministic tests pass, 22 real_llm tests deselected, 85.23% coverage; Ruff, both Pyright scopes, JS, CodeQL and CI summary pass.
- [x] Create this branch from latest main.
- [x] Add this resumability checkpoint.
- [ ] Open draft PR #272.
- [ ] Record exact #271 report schema and run commands.

### WP1 — Candidate and licensing/footprint assessment
- [x] Inspect Stanza and spaCy candidates and Spanish models.
- [x] Choose Stanza as optional candidate; record spaCy Spanish model GPL-3.0 as a separate license concern.
- [ ] Pin an opt-in nlp-pilot dependency group only.
- [ ] Document model download size/selected processors, cache path, CPU-only policy, and offline mode; do not guess size if it is not measured.

### WP2 — Typed adapter boundary
- [ ] Add immutable parser result/token records with exact source offsets, lemma, UPOS/XPOS, morphological features, dependency label and head index.
- [ ] Add a lazy Stanza adapter with injected pipeline support for tests.
- [ ] Validate input size, token bounds, offset validity and local dependency indices.
- [ ] Expose only untrusted linguistic hints; no entity IDs, actor authority, action family, permissions or outcomes.
- [ ] Add bounded, content-free parser metadata for reports.

### WP3 — Parser-only offline baseline
- [ ] Add a reproducible offline runner over development and held-out corpora, with split labels and no text in reports.
- [ ] Measure parse coverage, missing annotations, parse errors, token counts, wall/CPU latency P50/P95 and model directory size.
- [ ] Score only narrow, gold-supported probes (e.g. negation/conditional marker candidates and mention-span coverage); do not infer actor/action outcomes from dependency labels.
- [ ] Keep parser-only quality separate from model semantic scores and publish exact denominators.

### WP4 — Model + parser-hint comparison harness
- [ ] Add an opt-in real_llm/nlp_pilot test that compares the unchanged Intent model with an evaluation-only provider wrapper that appends parser hints.
- [ ] Score both variants with #271's exact shared scorer on identical inputs, model digest and generation settings.
- [ ] Include parser latency and model-call latency separately.
- [ ] Ensure no production prompt, schema or call count changes.
- [ ] Keep all real provider runs out of deterministic CI; test the wrapper with fake providers.

### WP5 — Contracts, privacy and docs
- [ ] Unit tests for adapter mapping, multiword tokens, malformed offsets, invalid heads, optional-dependency absence, empty/oversized input, hint serialization and privacy.
- [ ] Update ADR, roadmap, #271 closure record and developer runbook with measured commands and licensing decision.
- [ ] Provide exact commands to install the optional group, download selected models and run offline/live pilot.
- [ ] Make report content-free: no utterances, raw tokens, lemmas, entity names or raw parser payloads.

### WP6 — Validation and decision
- [ ] Run focused offline tests, Ruff, Pyright and full deterministic CI.
- [ ] Inspect diff for no prompt/production runtime integration and no default dependency changes.
- [ ] Complete pilot report and state whether Stanza should remain experiment-only or merits a later production proposal.
- [ ] Keep PR as draft until all deterministic gates pass; do not merge based only on structural tests.

## Acceptance criteria
1. Default install and application startup remain unchanged if Stanza is absent.
2. All parsed source offsets are exact and bounded; no fuzzy text search to fabricate offsets.
3. Every hint can be traced to current player text and has no canonical identity/authority.
4. Reports never contain user text, mention strings, entity names, lemmas or raw token arrays.
5. Held-out text/gold is not embedded in prompts or changed to improve results.
6. Offline benchmark is reproducible and reports denominators and latency, not a single weighted score.
7. Stanza is not promoted into default production dependencies without measured net semantic improvement and a separate approval.

## External assessment sources
- Stanza package/license/version: https://pypi.org/project/stanza/
- Stanza Spanish models/processors and offline model configuration: https://stanfordnlp.github.io/stanza/download_models.html and https://stanfordnlp.github.io/stanza/available_models.html
- Stanza Spanish model card (Apache-2.0): https://huggingface.co/stanfordnlp/stanza-es
- spaCy package (MIT) vs Spanish model (GPL-3.0): https://pypi.org/project/spacy/ and https://huggingface.co/spacy/es_core_news_sm

## Resumption notes
- Last completed work package: WP0 complete, WP1 assessment started.
- Last commit:
- Files changed: this checkpoint only.
- Tests run and results: #271 final CI success; no #272 tests yet.
- Known blockers / next exact action: implement the typed adapter boundary, offline benchmark and opt-in A/B harness; preserve no-default-dependency and no-production-prompt constraints.