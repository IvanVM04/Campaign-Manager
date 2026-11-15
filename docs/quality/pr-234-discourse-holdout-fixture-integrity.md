# PR #234 — discourse holdout fixture integrity

## Triggering live baseline

The 16 November 2026 live run of
`test_real_ollama_meets_held_out_discourse_intent_and_resolution_corpus`
used `gemma4:12b-it-q4_K_M` and completed 44 Intent calls in 260.69 seconds.
The run failed, as expected for this development baseline; several critical
Intent cases repeatedly failed evidence validation and reference expectations.

The report also exposed two evaluation defects independent of model quality.

## Defect 1 — NPC speaker fixture entities never reached the live prompt

The discourse fixture stores ordinary visible references in
`visible_entities`, and the NPC speaker-attribution examples in
`npc_entities`. The live harness's `_context()` helper populated
`WorldState.entities` from `visible_entities` only.

Consequently, the prompt's `DiscourseContextBuilder` received no NPC candidates
for scenarios 21–24 even though those scenarios explicitly supplied
`npc_entities` and expected speaker hints. In the observed live run,
`dp-npc-explicit-visible-21` expected `speaker:mara` but the rendered
discourse section contained no NPC speaker hint.

The helper now includes both fixture entity collections in the evaluation
world, with `visible_entities` taking precedence if an ID is repeated.
Existing production filters remain responsible for requiring an active,
unique visible NPC before attributing quoted speech.

A new offline regression test builds the actual Intent prompt using
`FakeLLMProvider` for each scenario with an `npc_speaker_ids` expectation.
It asserts the rendered hint set is correct for:
- an active, uniquely labelled speaker;
- duplicate/ambiguous aliases;
- an inactive speaker;
- a speaker whose quoted content mentions another NPC.

This checks the integration path from fixture → world → ContextBuilder →
DiscourseContextBuilder → rendered Intent prompt.

## Defect 2 — incorrect held-out action argument label

Scenario `dp-distance-most-recent-15` uses the player input
`Le pregunto a él si ha visto la llave.`, but expected the recipient mention
`ella`. The expected label contradicted the literal player evidence and would
score a correct model output as wrong.

The fixture now expects `él`.

A new corpus-integrity test verifies that every expected action-frame argument
mention and every expected conversation-reference mention occurs literally in
its scenario's current player input (NFKC-normalized and case-insensitive).
Context-derived action recovery remains a separate expectation and is not
subject to this literal-mention check.

## Scope and non-goals

This PR corrects evaluation inputs and harness wiring only. It does not loosen
semantic evidence validation, repair model completions, change the held-out
scenario text, or claim that Gemma 4 12B has passed the discourse corpus.

The broad baseline still demonstrates genuine model issues:
- repeated `action_frame.predicate` grounding failures;
- unsupported or non-literal target/relation mentions;
- category confusion in some third-person utterances;
- ellipsis actions that need prior-turn context;
- reference/abstention accuracy that cannot be judged reliably until Intent
  decoding succeeds.

These remain follow-up work after the benchmark is corrected.

## Validation

Deterministic checks added:
- expected frame/reference mentions are literal in their own player utterance;
- the live Intent prompt receives only the speaker hints justified by the NPC
  fixture's active/unique speaker data.

Commands:

```powershell
python -m pytest tests/test_discourse_pipeline_holdout.py -q
python -m pytest tests/test_real_llm_discourse_pipeline.py -m "not real_llm" -q
```

The second command is expected to collect no live tests unless deterministic
tests are added to that module later; the primary new regression is in
`test_discourse_pipeline_holdout.py`.

After merge, rerun the 24-scenario live holdout before interpreting per-family
model results or beginning another prompt-tuning iteration.
