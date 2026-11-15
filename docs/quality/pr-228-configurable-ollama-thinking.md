# PR #228 — Configurable Ollama thinking mode

## Status and purpose

This follow-up is intentionally separate from merged PR #227. It makes Ollama's
`think` request field configurable without changing existing defaults, so
live evaluation can compare the model's own default thinking behavior with
explicit thinking disabled.

## Evidence motivating the change

- The local model is `gemma4:26b` (digest prefix `001e5dafc3c7`).
- `/api/show` reports `thinking.default=true` and supports both boolean values.
- A direct `/api/generate` call with `num_predict=16` and no `think` field
  completed with `done_reason=length`, `eval_count=16`, non-empty `thinking`
  and empty `response`.
- The same short direct request with `think=false` completed with `response=OK.`
  and `done_reason=stop`.
- The first held-out intent evaluation exceeded a 300-second request timeout.
  This is evidence of an unusable current setup, not a measured semantic failure.
  The request omitted `think` because `OllamaProvider` previously inherited the
  model default.

## Design

- Add optional `think: bool | None` to `OllamaProvider`.
- `None` omits the API field and preserves existing Ollama/model defaults.
- `True` and `False` are passed explicitly on both text and structured generation.
- Add one common environment variable, `CAMPAIGN_MANAGER_OLLAMA_THINK`, plus optional
  per-role overrides for narrative, extraction, mechanics and intent.
- Per-role environment settings override the common setting.
- Record explicit thinking mode in safe request telemetry; never log prompts,
  completions or hidden thinking text.
- Do not change prompts, temperature, token budgets, or default provider behavior.

## Validation

Deterministic coverage:
- Default requests omit `think`.
- Explicit false and true values are sent on text and structured requests.
- Invalid non-boolean direct settings and invalid environment values are rejected.
- Common setting fallback and per-role overrides are verified.
- CI tests, lint and Pyright must pass before local evaluation.

## Local PowerShell A/B procedure

Set the existing model and URL, and pin a longer timeout for this local hardware:

```powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_MODEL = "gemma4:26b"
$env:CAMPAIGN_MANAGER_REAL_LLM_BASE_URL = "http://localhost:11434"
$env:CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT = "300"
```

Run the focused Intent/discourse evaluation with thinking disabled:

```powershell
$env:CAMPAIGN_MANAGER_OLLAMA_THINK = "false"
python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -k "held_out_discourse_intent_and_resolution_corpus" -v -s 2>&1 | Tee-Object -FilePath .\pr228-intent-think-off.log
```

For a second run using the model default, remove the common override:

```powershell
Remove-Item Env:CAMPAIGN_MANAGER_OLLAMA_THINK -ErrorAction SilentlyContinue
python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -k "held_out_discourse_intent_and_resolution_corpus" -v -s 2>&1 | Tee-Object -FilePath .\pr228-intent-default.log
```

The first command should be attempted before the default-mode rerun because the
default-mode run has already timed out at 300 seconds. Do not interpret the
short direct `OK` probe as a semantic-quality benchmark. Compare live corpus
metrics, provider usage, timing and all failure details. If thinking-off still
times out, investigate prompt prefill, CPU/GPU offload, memory pressure and
Ollama runner health before changing prompts.


## Validation-failure diagnostics

The live Intent probe accepts an optional scenario selector so a single non-critical
case can be inspected without replaying the complete holdout:

```powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID = "dp-topic-current-shift-01"
$env:CAMPAIGN_MANAGER_LLM_INTENT_THINK = "false"
python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -k "held_out_discourse_intent_and_resolution_corpus" -v -s
```

Invalid provider completions now report a bounded validation stage/code (JSON
decoding, top-level envelope, analysis schema/evidence or correction contract).
The exception text intentionally excludes provider output and player evidence.
The evaluator prints the scenario ID and safe stage/code in its mismatch summary.
A non-critical selected scenario may leave pytest green while printing a mismatch;
inspect that summary rather than only the exit code.

## Acceptance boundary

This PR only exposes an existing Ollama API control and adds deterministic
contract tests. It does not claim thinking-off is more accurate, faster for all
hardware, or universally preferable. Preserve the server default unless an
explicit setting is supplied. Semantic baseline acceptance remains pending
until the held-out evaluation completes with a pinned model digest and recorded
per-family metrics.
