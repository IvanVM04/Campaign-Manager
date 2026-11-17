# Discourse understanding evaluation and actor hardening — 2026-11-17

## Purpose

This increment closes a measurement gap left by the discourse/continuity work in #246–#248. It does not replace the shared Intent architecture, add another model call, or relax evidence, entity-resolution, mechanics, or world-write gates.

The change is deliberately split into:

1. A frozen sidecar gold for the fictional actor of the primary Intent step.
2. Independent deterministic scores for topic boundaries, callbacks, history scope and ellipsis cues.
3. A privacy-safe, reproducible live Ollama report.
4. A compact actor decision matrix in the Intent prompt and JSON Schema.

## Audit findings

The current deterministic discourse tests already cover 28 balanced cases across seven families. They check topic segmentation, callback anchor selection, ellipsis hint rendering, local grammatical agreement, NPC quote attribution, reference resolution and multi-turn corrections.

The live holdout, however, had several blind spots:

- The expected Intent category and action arguments were scored, but the fictional actor of the primary step was not an independent semantic metric. An answer could therefore have the right category and frame family while assigning the act to the wrong participant.
- Topic shift, callback and history-scope behavior were observed in diagnostic counters but were not exposed as a compact independent accuracy ledger in the optional JSON report.
- The ellipsis family checked action recovery for a few examples, but did not separately report whether the deterministic ellipsis cue itself was correct.
- The discourse report persisted aggregate semantic metrics and failure counts, but omitted commit, model digest, server version, timeout, reasoning mode, control accuracy and allowlisted provider usage in one versioned artifact.

These are evaluation deficiencies, not proof that the production resolver is incorrect. The existing deterministic tests remain the source of truth for deterministic selection; live model interpretation remains a separate acceptance gate.

## Implementation

### 1. Primary fictional actor gold

New sidecar: `tests/fixtures/discourse_pipeline_actor_gold_v1.json`.

- Labels the primary actor as `player` or `npc` for all 24 non-correction cases in the existing 28-case held-out discourse corpus.
- References existing scenario IDs; it does not duplicate utterances or modify the original fixture.
- The gold distinguishes the message sender from the actor in the fiction. Third-person NPC speech and physical events are NPC actions; the player speaking to an NPC remains a player act.
- The live evaluator records `intent_primary_actor` independently from category and action-frame family. Missing or invalid actor output is scored as a miss, not silently omitted.

### 2. Independent deterministic discourse controls

New `DiscourseControlLedger` reports exact accuracy for:

- `topic_shift`
- `callback`
- `history_scope` (ordered turn IDs)
- `ellipsis_hint`

Only dimensions explicitly present in a fixture's expected data are scored. Empty dimensions remain unmeasured (`null`), not 100%.

### 3. Reproducible and privacy-safe report

The live discourse report is upgraded to schema version 5 and records:

- commit SHA, model name/digest, Ollama server version, timeout and configured reasoning mode;
- scenario count/filter, provider calls and elapsed time;
- semantic ledger and independent discourse-control scores;
- per-family call counts, prompt-size/retention counters and numeric provider-usage aggregates only;
- critical and observational failure counts.

It does not persist prompts, completions, utterances, player input, narrative, source excerpts, campaign state, raw exceptions or rejected payloads. Only non-negative numeric timing/token counters are aggregated from provider callbacks. No provider event dictionary or provider-supplied text value is persisted, even when its key appears in the runtime telemetry payload.

### 4. Actor decision contract

The Intent prompt and structured schema now include concise contrastive examples for:

- NPC dialogue vs. NPC physical report;
- player dialogue directed to an NPC;
- plural NPC speech;
- a question to the DM about an unknown speaker;
- a quoted NPC speaker vs. the agent inside the quoted event.

These examples clarify classification without adding new deterministic rewrites or changing the evidence validator.

## Validation

Offline commands:

```powershell
python -m pytest tests/test_discourse_actor_evaluation.py tests/test_discourse_context_builder.py tests/test_discourse_pipeline_holdout.py tests/test_intent_speech_act_contract.py -q
python -m pytest tests/test_real_llm_discourse_pipeline.py -m "not real_llm" -q
ruff check tests/discourse_evaluation.py tests/test_discourse_actor_evaluation.py tests/test_real_llm_discourse_pipeline.py tests/test_intent_speech_act_contract.py services/turns/intent_interpreter.py services/turns/intent_response_schema.py
pyright tests services/turns
```

Live Ollama acceptance remains local to the user's environment:

```powershell
$env:CAMPAIGN_MANAGER_GIT_COMMIT = (git rev-parse HEAD).Trim()
$env:CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH = ".\\artifacts\\discourse-holdout-v5.json"
python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -k "held_out_discourse_intent_and_resolution_corpus" -v -s --junitxml=.discourse-holdout-v5.xml 2>&1 | Tee-Object -FilePath .\\discourse-holdout-v5.log
```

Compare the new actor F1, control accuracies, category accuracy, argument scores, entity precision/recall and abstention counts against the same model digest and server version. A control score does not establish that the model understood the corresponding cue; both deterministic and live metrics must pass.

## Safety invariants

- Existing holdout utterances and expected values are not changed.
- Historical names, predicates and arguments are not copied into current player evidence.
- Ambiguous singular/plural references remain unresolved or ask for clarification.
- NPC speech attribution remains restricted to explicit, unique, visible, active NPC labels.
- No new world-write authority, mechanics authorization, entity canonicalization or provider call is introduced.
- The local Ollama and SillyTavern acceptance gates are not claimed as passed by GitHub CI.

## Known limitations

- The sidecar scores only the primary step actor; mixed multi-step messages need a dedicated per-step gold corpus before actor accuracy can be generalized to all steps.
- The 24 actor labels are a focused discourse holdout, not a general Spanish actor benchmark.
- The deterministic control ledger measures the current bounded heuristics, not the semantic quality of the LLM response.
- No SillyTavern live session can be run from GitHub Actions.
