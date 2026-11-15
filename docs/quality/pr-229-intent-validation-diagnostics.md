# PR #229 — Intent validation diagnostics

## Why this follow-up exists

After Ollama thinking became configurable in merged PR #228, the held-out intent
test began receiving completed provider responses. However, the interpreter logged
`llm.intent.invalid_response` without exposing the validation stage, and the live
evaluator reduced the failure to the exception class. This made JSON/envelope/
semantic-schema failures indistinguishable.

## Changes

- Classify failures into safe stages: JSON decoding, top-level contract,
  PlayerIntentAnalysis schema/evidence validation and pending-correction validation.
- Log only bounded `validation_stage`, `validation_code` and exception class.
- Do not log provider completions, prompts, player evidence or raw exception text.
- Include the safe interpreter diagnostic in the local evaluation mismatch output.
- Add `CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID` to execute one non-correction
  held-out Intent scenario instead of repeating the full corpus.
- Add a deterministic test proving validation diagnostics do not include the
  private model response content.

## Local focused reproduction

Update your local branch:

```powershell
git fetch origin
git switch fix/229-intent-validation-diagnostics
git pull --ff-only origin fix/229-intent-validation-diagnostics
```

Set the pinned model and thinking mode:

```powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_MODEL = "gemma4:26b"
$env:CAMPAIGN_MANAGER_REAL_LLM_BASE_URL = "http://localhost:11434"
$env:CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT = "300"
$env:CAMPAIGN_MANAGER_LLM_INTENT_THINK = "false"
$env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID = "dp-topic-current-shift-01"
```

Run the one-scenario test:

```powershell
python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -k "held_out_discourse_intent_and_resolution_corpus" -v -s 2>&1 | Tee-Object -FilePath .\pr229-intent-diagnostic.log
```

Inspect the `Non-critical mismatches` line even if pytest exits successfully.
It should contain the scenario ID and a safe stage/code, for example:

- `json_decode: malformed_json`
- `top_level_contract: invalid_top_level_contract`
- `intent_analysis_validation: schema_or_evidence_validation_failed`

These examples describe possible classifications, not an observed result.

## Acceptance

- Deterministic tests, Ruff, repository-wide and scoped Pyright, JS tests and CodeQL pass.
- The focused local run reports a specific validation stage/code, or a successful
  `llm.intent.analysis_completed` event.
- The complete held-out run is only resumed after the first focused response is
  understood. No prompt changes are made as part of this diagnostic PR.
