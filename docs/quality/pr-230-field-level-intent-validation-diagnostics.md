# PR #230 — Field-level Intent validation diagnostics

## Why this follow-up exists

PR #229 proved that Ollama completes a response and that the JSON envelope is
accepted, but the semantic parser still reported the same
schema_or_evidence_validation_failed code for unrelated failures. A model
could therefore be rejected because of an excerpt, action predicate, argument,
relation, enum or cross-field invariant without revealing which contract failed.

This PR improves the trust-boundary diagnostics. It does not weaken validation,
change the Intent prompt, change model settings or accept unsupported output.

## Changes

- Wrap semantic payload rejection in IntentAnalysisValidationError, retaining
  ValueError compatibility for existing callers.
- Classify failures into stable codes and bounded field paths, including:
  evidence_not_in_player_text, evidence_not_in_step_excerpt,
  unsupported_enum_value, invalid_object_shape, collection_out_of_bounds,
  invalid_step_order, invalid_relation_reference, invalid_active_step,
  category_active_step_mismatch and intent_step_invariant_violation.
- Record only validation_stage, validation_code, validation_field and
  validation_reason. Raw model completions, player text and exception messages
  remain excluded from logs and public diagnostics.
- Include the safe field path in IntentInterpreterError, so the held-out
  evaluation can identify the failing semantic slot.
- Make a filtered single-scenario live evaluation strict: a mismatch in that
  focused run now fails pytest even when the corpus case is marked non-critical.
  Full-corpus behavior remains unchanged.
- Add deterministic tests for source excerpts, action predicates, action
  arguments, relation step-local evidence, unsupported enums and log privacy.

## Focused local reproduction (PowerShell)

Update the local checkout:

~~~powershell
git fetch origin
git switch --track origin/fix/230-detailed-intent-validation-diagnostics
~~~

Use the same pinned model and settings:

~~~powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_MODEL = "gemma4:26b"
$env:CAMPAIGN_MANAGER_REAL_LLM_BASE_URL = "http://localhost:11434"
$env:CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT = "300"
$env:CAMPAIGN_MANAGER_LLM_INTENT_THINK = "false"
$env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID = "dp-topic-current-shift-01"
~~~

Run only the failing scenario:

~~~powershell
python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -k "held_out_discourse_intent_and_resolution_corpus" -v -s 2>&1 | Tee-Object -FilePath .\pr230-intent-diagnostic.log
~~~

Capture pytest's exit code:

~~~powershell
$testExitCode = $LASTEXITCODE; Write-Host "pytest exit code: $testExitCode"
~~~

In this focused mode, a mismatch is now a failing test. The output should
identify the stage, code and semantic field, for example:

intent_analysis_validation: evidence_not_in_step_excerpt (field=steps[].action_frame.arguments[].mention)

That example is illustrative, not a claim about the current Gemma response.
A successful interpretation is reported by llm.intent.analysis_completed.

Run the deterministic regression tests without Ollama:

~~~powershell
python -m pytest tests/test_intent_validation_diagnostics.py tests/test_player_intent_analysis.py tests/test_semantic_frames.py tests/test_modular_language_pipeline.py -q
~~~

## Privacy and compatibility

- Diagnostic fields are selected from fixed internal vocabularies; no model
  value, player evidence or raw validation message is copied into them.
- IntentAnalysisValidationError remains a ValueError subclass, preserving
  existing parser caller behavior.
- V1 persisted Intent payloads, V2 semantic frames, correction validation and
  operation authorization rules are unchanged.
- A focused live failure is expected to have a non-zero pytest exit code; this
  does not mean the complete non-critical corpus has changed its policy.

## Acceptance

- New deterministic diagnostics tests and all existing Intent/semantic-frame
  tests pass.
- Ruff, repository-wide/scoped Pyright, full Python tests, JavaScript tests and
  CodeQL pass on the PR head.
- The local focused run reports either llm.intent.analysis_completed or one
  field-level validation failure. Do not resume the complete held-out run until
  the first failing field is understood.
