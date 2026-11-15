# PR #232 — Intent step position canonicalization

## Problem

The focused held-out case `dp-topic-current-shift-01` completed successfully with
`gemma4:12b-it-q4_K_M`, but its Intent payload was rejected at:

```text
invalid_step_order (field=steps[].index)
```

The domain model requires the step indexes to be contiguous and ordered
(`0, 1, ...`). A model can produce valid integer index values that do not
match the positions of the corresponding objects in the JSON array.

## Contract

The `steps` JSON array is the authoritative ordered sequence. The
`index` field is redundant metadata and must equal that element's zero-based
array position. The interpreter does not reorder step objects based on
model-supplied indexes.

## Change

- State the zero-based array-position rule in the Intent prompt and JSON
  Schema description.
- At the untrusted provider boundary, canonicalize integer `index` fields
  to their array positions when all step objects are dictionaries and every
  supplied index is an integer (booleans are not integers for this contract).
- Preserve each step object and the array order; only the redundant index
  fields change.
- Emit `llm.intent.step_indices_canonicalized` with step count, old/new
  integer indexes and the normalization name. No prompt, player evidence or
  generated action text is logged.
- Leave non-object steps, non-integer indexes, empty arrays and arrays above
  the domain maximum untouched for strict validation.
- Keep `PlayerIntentAnalysis.from_payload()` strict. This normalization only
  applies to untrusted provider output before decoding.

## Safety

Changing indexes to the positions of the existing array does not reorder,
merge, add or remove actions. It does not change category, actor, action,
predicate, arguments, modality, polarity, reported outcome, attribution or
evidence. The active-step pointer continues to refer to the same array
position. The previous PR #231 normalization still clears active-step
authorization for non-action categories. A question cannot become actionable
through either normalization.

Direct domain decoding remains strict, including its contiguous-index checks.
The negative regression test also verifies that a non-integer index is not
silently repaired.

## Deterministic tests

```powershell
python -m pytest tests/test_modular_language_pipeline.py tests/test_player_intent_analysis.py tests/test_intent_validation_diagnostics.py -q
```

## Live evaluation and observed latency

On 15 November 2026, the single held-out scenario completed with
`gemma4:12b-it-q4_K_M`, `think=false`, and a 900-second timeout:

| Metric | Observed |
|---|---:|
| End-to-end Intent case latency | 26.371 s |
| Ollama request duration | 26.366 s |
| Model load | 4.326 s |
| Prompt evaluation | 9.795 s |
| Output evaluation | 10.141 s |
| Prompt tokens | 860 |
| Generated tokens | 196 |

The response reached semantic validation and failed only at
`invalid_step_order`. The same scenario on `gemma4:26b` had taken
336.854 seconds. These are single-run observations, not statistically
controlled benchmarks.

## Acceptance

- Deterministic tests prove zero-based position canonicalization and preserved
  array order.
- Malformed step object shapes and non-integer indexes remain rejected.
- Existing strict domain model tests remain unchanged and pass.
- The focused live case proceeds beyond step-index validation. Any subsequent
  semantic or evidence error is recorded separately; normalizing indexes
  does not make the scenario pass by itself.
