# PR #250 — Predicate-specific evaluation and reproducible telemetry

## Purpose

Turn the predicate-understanding audit into measurable code without changing production prompting, semantic decoding, evidence validation or authorization boundaries.

The 20-case semantic-frame holdout remains evaluation-only. No held-out utterance is copied into a system prompt, JSON Schema description or few-shot example.

## Changes

### 1. Gold predicates for every held-out frame and relation

`semantic_frame_corpus_holdout_v1.json` remains byte-for-byte unchanged at schema version 1. New labels live in `semantic_frame_predicate_gold_v1.json`, a sidecar keyed by the original scenario IDs. It contains no duplicate utterances and declares exact, case-sensitive surface predicates for every action frame and directed relation.

Examples:
- `Entrego el pergamino...` → `Entrego`
- `Mara entrega...` → `entrega`
- `La gema azul forma parte...` → `forma parte`
- `Mara y Aldric son amigos` → `son amigos`

These are surface spans, not lemmas. The scorer does not convert conjugated forms to infinitives or remove accents.

### 2. Separate predicate metrics

The semantic-frame evaluator reports two additional metric families:

- `action_frame_predicate_surface`
- `relation_predicate_surface`

For each family it records exact surface match, per-case accuracy, and precision/recall/F1 using scenario-scoped signatures.

Action-predicate scoring is independent of action-frame family and argument scoring. Relation-predicate scoring is independent of relation endpoint direction and relation-family scoring. A correct predicate cannot hide a wrong frame or direction, and a correct family cannot hide a wrong verb.

Missing predicates count as false negatives. Extra predictions count as false positives. Existing frame, role, relation, modality, polarity and safety metrics remain separate.

### 3. Reproducible privacy-safe JSON reports

Set an output path and run the semantic-frame holdout:

```powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH = ".\\artifacts\\predicate-holdout.json"
$env:CAMPAIGN_MANAGER_GIT_COMMIT = (git rev-parse HEAD).Trim()
$env:CAMPAIGN_MANAGER_REAL_LLM_HARDWARE = "optional hardware label"
python -m pytest tests/test_real_llm_semantic_holdout.py -m real_llm -k "semantic_frame_corpus_v1" -v -s
```

The optional `CAMPAIGN_MANAGER_REAL_LLM_THINK` environment variable controls Ollama reasoning for this live holdout only:
- `false` (also `0`, `no`, `off`) sends `think: false`.
- `true` (also `1`, `yes`, `on`) sends `think: true`.
- Unset preserves the model/provider default.
- Any other value fails fast with a configuration error.

This is useful for comparing latency, but a faster run is not automatically equivalent: verify structured-output validity and semantic metrics before preferring one mode. The effective setting is captured in report metadata.

The report includes the commit SHA (when supplied by the environment), model and digest, Ollama server version, timeout, effective `think`, scenario filter/count, provider-call count, elapsed time, aggregate metrics and allowlisted content-free provider usage counters.

It never stores prompts, completions, player utterances, campaign state, raw exceptions or rejected values. Without a configured path, the test still prints the metrics and records JUnit properties.

A single-case diagnostic run can be selected with:

```powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID = "holdout-transfer-scroll"
```

The filtered run is strict and is not a replacement for the full 20-case holdout.

### 4. JUnit metadata compatibility

The pytest JUnit family is set to `legacy` so `record_property` metadata is retained instead of producing the compatibility warning seen in earlier local Ollama runs. JSON remains the richer recommended report artifact.

## Offline validation

```powershell
python -m pytest tests/test_predicate_evaluation.py tests/test_semantic_evaluation_corpus.py -q
python -m pytest tests/test_real_llm_semantic_holdout.py -m "not real_llm" -q
ruff check tests/test_predicate_evaluation.py tests/semantic_frame_evaluation.py tests/semantic_evaluation_report.py tests/test_real_llm_semantic_holdout.py tests/test_semantic_evaluation_corpus.py
pyright tests
```

The live Ollama evaluation remains opt-in and must be run against the configured local model service.

## Interpretation limits

The new predicate metrics answer: "Did the model preserve the expected written predicate span?" They do not, by themselves, prove full lexical-sense disambiguation. Frame family, argument roles, relation family/direction, polarity and modality are complementary semantic measurements.

For relation claims, endpoint identity matching ignores only a leading Spanish article when comparing the two endpoints; it does not erase meaningful nouns/modifiers, reverse direction or normalize the predicate. This keeps the predicate metric from failing solely because a model omitted an initial article while preserving separate endpoint-direction scoring.

Do not label aggregate semantic-slot F1 as predicate accuracy. Report the new predicate metrics by their own names.

## Follow-up prompt/schema refinement

The semantic interpreter contract also defines the taxonomy for action families, argument roles, relation families, predicate boundaries, negation, reported attribution and temporal expressions. These rules are evaluation-guided and do not weaken literal-evidence validation. In particular, a relation predicate is its lexical core (for example, `pertenece`, not `pertenece a`); negation belongs in polarity/modality, and relationship family must distinguish ownership, possession and membership.
