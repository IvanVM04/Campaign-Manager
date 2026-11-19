# PR #271 — complete semantic evaluation contracts

**Status:** completed; merged on 2026-11-19.  
**Merged into:** main at 9de344d4d36fdfc325c91f34075553d6076f2fc0.  
**PR head:** a669d194462cced1ab2994a96ce60f25a4250b8.  
**Original base:** c11e0541b855bcde24a8d86616d9e384a3ebda8c.  
**Follow-on:** PR #272 owns the optional offline NLP pilot and the documentation reconciliation that was not completed before #271 merged.

## Final verification

Final deterministic CI succeeded on the exact PR head a669d19:

- **2,204 passed**, **22 deselected** (real_llm).
- Combined coverage: **85.23%**, above the configured 85% floor.
- Ruff: success.
- Pyright required scope (models rules_engine bootstrap operations): success.
- Repository-wide Pyright baseline: success.
- JavaScript tests: success.
- CodeQL Python and JavaScript: success.
- CI summary: success.

Evidence:
- [Tests run #44559085820](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44559085820)
- [CodeQL run #44559085674](https://github.com/IvanVM04/Campaign-Manager/actions/runs/44559085674)

Deterministic commands from .github/workflows/tests.yml:

    python -m pytest -m "not real_llm" --cov --cov-report=term-missing --cov-report=xml
    ruff check .
    pyright models rules_engine bootstrap operations
    pyright --outputjson
    npm run test:js
    python -m coverage report

The final run did not execute Ollama or SillyTavern. The 22 excluded tests are intentionally marked real_llm; CI passing validates deterministic contracts and code quality, not semantic quality of a particular model.

## Delivered scope

- Text-free exact step-count sidecar for all 35 general language holdout scenarios.
- Text-free explicit action-frame/relation presence sidecar for all 20 semantic-frame holdout scenarios (10 frame positives, 10 relation positives; zero counts are explicit negative controls).
- Ordered Intent scorer for category, active step, clarification, exact step count, and independently golded per-step fields.
- Semantic-frame scorer for exact frame/claim cardinality, family, predicate, role/mention arguments, directed relations, polarity, modality, attribution, temporal expression and step index where gold exists.
- Extra and duplicate predictions counted as FP; omissions counted as FN.
- Unannotated fields remain unmeasured; they are not silently treated as correct or as negative gold.
- Metric schema v1 with case accuracy, TP/FP/FN, gold/prediction denominators, precision/recall/F1 and nearest-rank latency P50/P95.
- Content-free live evaluation reports with bounded allowlists for provider metadata.
- General Intent and semantic-frame live harnesses call the shared scorers; provider failures remain scored misses.

## Integrity / scope audit

The PR changed only these areas: documentation, evaluation helpers, offline tests and two text-free gold sidecars. The changed-file list contained no production prompt/runtime packages and no original held-out utterance corpus files. The original held-out language and semantic-frame corpus inputs were not edited to make the evaluator pass.

The two new sidecars contain only scenario IDs and gold annotations/cardinalities; they do not copy utterance text. No held-out text/gold was embedded in production prompts or few-shot examples.

## Metric contract

- metric_schema_version = 1.
- Per-family case accuracy is reported separately from slot recall.
- Slot metrics expose TP/FP/FN, gold and predicted denominators, precision, recall and F1.
- Zero-denominator precision/recall/F1 is null, not a fabricated 100%.
- Extra predictions and duplicates are false positives; missing gold slots are false negatives.
- Latency percentiles use nearest-rank P50/P95 and publish sample counts.
- Reports exclude player utterances, prompt/completion content and arbitrary provider strings.

## Work package closure

- [x] WP0 — branch/checkpoint and PR created.
- [x] WP1 — gap inventory and explicit count/slot gold.
- [x] WP2 — shared ordered Intent and semantic-frame scorers.
- [x] WP3 — versioned metrics and safe report allowlist.
- [x] WP4 — offline regression tests and corpus integrity.
- [x] WP5 — live harness integration and provider failures scored as misses.
- [x] WP6 — final diff review, CI verification and merge.

The roadmap/ADR reconciliation was left incomplete at merge time. It is being completed as a documentation carry-over in PR #272:
- [x] Update the architecture ADR to mark #271 integrated and #272 active.
- [x] Update the current quality roadmap and record the final CI evidence.
- [x] Add a #271 closure record and verify changed files did not include original holdouts.

## Resume guidance

#271 is historical and must not be recreated. Continue optional NLP work in the existing #272 branch/PR, starting from its latest head and its checkpoint docs/quality/pr-272-optional-offline-nlp-pilot.md.
