# PR #245 — Fix the live correction holdout selector assertion

## Finding

The 2026-11-16 Ollama holdout failed at
`dp-correction-relation-endpoint-26` with
`correction argument role mismatch`.

The model result had already passed these checks in the live test:

- exactly one correction was returned;
- the selected slot was `relation_object`;
- `previous_value` matched `Bram`;
- the replacement matched `Aldric`.

The interpreter also returned successfully from
`understand_pending()`, which applies the correction against the backend
candidate catalogue and compares the full analysis with the deterministic
typed patch.

The remaining assertion incorrectly compared
`correction.argument_role` with the fixture's `role: object`.

## Root cause

`argument_role` belongs only to `action_argument` corrections. The
`PendingIntentCorrection` model rejects a non-null `argument_role` for
`relation_subject` and `relation_object` slots. A relation endpoint is
identified by the correction slot and its backend-derived
`relation_claim_index`.

The holdout fixture represented the object endpoint as `role: object`, and
the live test applied the action-argument assertion to every correction.
That made the test fail even when the relation endpoint was selected
correctly. This is an evaluation-contract defect, not evidence of a prompt,
Ollama, or production correction failure.

## Fix

- Represent action-frame metadata as `role` only for `action_argument`.
- Represent relation endpoint metadata as `endpoint` plus
  `relation_claim_index`.
- Validate `argument_role` only for action-argument corrections.
- For relation corrections, require `argument_role is None` and validate
  the backend-resolved `relation_claim_index`.
- Strengthen the deterministic fixture test to enforce the distinction.

No production model, prompt, schema, or correction-application behavior is
changed.

## Validation

Run the focused offline contracts:

```powershell
python -m pytest tests/test_discourse_pipeline_holdout.py tests/test_pending_intent_correction.py tests/test_pending_intent_correction_flow.py -q
ruff check tests/test_real_llm_discourse_pipeline.py tests/test_discourse_pipeline_holdout.py
```

Then rerun the live holdout with the same Ollama model and settings. A
passing deterministic test is not a substitute for the live run.
