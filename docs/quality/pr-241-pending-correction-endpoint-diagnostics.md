# Pending correction endpoint diagnostics

## Context

The PR #240 live Ollama correction holdout removed the earlier conflict between
independent nullable selector fields. Its remaining relation scenario failed
with a generic endpoint mismatch. The validator knew the selected relation
endpoint did not contain `previous_value`, but did not distinguish a subject /
object swap from a value absent from the relation.

The two-round action fixture also contained an inconsistent expected value:
the pending action argument is stored as `la llave`, while the second-round
expectation used `llave`. The live model returned the stored value and the
holdout reported a mismatch despite the correction being correctly grounded.

## Changes

- Relation selector validation now distinguishes a selector that names the
  opposite endpoint from a previous value that matches neither endpoint.
- The interpreter maps those fixed diagnostic messages to stable structured
  reason codes: `relation_selector_opposite_endpoint` and
  `relation_selector_previous_value_mismatch`. The codes contain no
  player-supplied or model-generated text.
- The two-round fixture now expects the exact stored theme mention
  (`la llave`) in both its round-level and scenario-level expectation.
- A deterministic fixture test applies each accepted correction to a synthetic
  pending state before validating the next round. This catches stale or
  inconsistent `previous_value` fields without invoking an LLM.
- Unit tests cover both relation mismatch categories and assert that diagnostic
  messages do not echo names or supplied values.

## Safety and scope

This change does not relax correction validation, infer a missing slot, repair
a model selector automatically, or change prompt size. A subject/object swap
still fails closed. The new reason codes are classification-only diagnostics;
the backend never substitutes the opposite endpoint or mutates pending state
after a rejected correction.

The live Ollama holdout must be rerun after this PR. A deterministic pass does
not establish that Gemma selects the correct relation endpoint.

## Validation

Run the offline focused suite:

```powershell
python -m pytest tests/test_pending_intent_correction.py tests/test_discourse_pipeline_holdout.py -q
```

Then rerun the live correction holdout with the project's configured Ollama
model:

```powershell
python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -k "pending_multi_turn_correction_holdout" -v -s
```
