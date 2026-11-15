# PR #231 — Intent category / active-step consistency and Ollama performance

## Problem

The focused held-out scenario `dp-topic-current-shift-01` sends:

> Cambiando de tema, ¿qué ocurre en la biblioteca?

With `gemma4:26b`, Ollama completed the structured request, but Intent validation rejected the result:

```text
category_active_step_mismatch (field=category)
```

The category was `question`, while the model also supplied a non-null `active_step_index`. The domain invariant is intentional: only `action` and `mixed` analyses may select an active mechanical step.

## Change

- Strengthen the Intent system prompt and JSON Schema descriptions with the category/active-step rule.
- At the provider boundary, clear an in-range active-step pointer when the model returns a non-action category (`question`, `dialogue`, `report`, `plan`, `correction`, `unknown`).
- Emit `llm.intent.non_action_active_step_cleared` with only category, discarded index and normalization name. No player evidence, prompt or completion is logged.
- Never rewrite the category, steps, action text, evidence, modality, polarity or reported outcome.
- Leave invalid categories and malformed/out-of-range active-step values untouched so the existing domain validation rejects them.
- Keep `PlayerIntentAnalysis.from_payload()` strict. The normalization applies only to untrusted provider output before domain decoding; it is not a relaxation of the domain contract.
- Add deterministic regression coverage for each non-action category and for out-of-range indices.
- Preserve provider timing/token metadata in the focused evaluation's JUnit properties so local model performance can be measured without logging prompts or completions.

## Safety rationale

Clearing an active-step pointer is fail-closed: it removes authorization to run mechanics. It does not transform a question into an action or grant a world mutation. The downstream mechanics stage still requires a validated actionable analysis.

If the model returns `category=question` and `active_step_index=0`, the accepted analysis remains a question and has `active_step_index=null`; `analysis.is_actionable` is false.

## Deterministic tests

```powershell
python -m pytest tests/test_modular_language_pipeline.py tests/test_player_intent_analysis.py tests/test_intent_validation_diagnostics.py -q
```

## Focused live evaluation

```powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_MODEL = "gemma4:26b"
$env:CAMPAIGN_MANAGER_REAL_LLM_BASE_URL = "http://localhost:11434"
$env:CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT = "900"
$env:CAMPAIGN_MANAGER_LLM_INTENT_TIMEOUT_SECONDS = "900"
$env:CAMPAIGN_MANAGER_LLM_INTENT_THINK = "false"
$env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID = "dp-topic-current-shift-01"

python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -k "held_out_discourse_intent_and_resolution_corpus" -v -s --junitxml=.pr231-ollama-metrics.xml
```

The test records safe provider metadata as JUnit properties, including prompt evaluation and output evaluation durations, token counts, model and thinking mode. It never stores the prompt or generated completion in those metrics.

## Ollama latency investigation

### Observed baseline

The 15 November 2026 focused run completed the Ollama request with `think=false` and a 900-second timeout, then failed semantic validation. The measured Intent case latency was **336.854 seconds**. A separate `ollama ps` observation reported `21%/79% CPU/GPU` and a `16384` token context. This establishes that reasoning-off alone did not make the local run fast.

Ollama documents that a split CPU/GPU percentage means some model layers are resident in system memory and some on the GPU; a fully GPU-resident model is generally preferable when the available VRAM can hold it. See [Ollama FAQ — GPU loading and context size](https://github.com/ollama/ollama/blob/main/docs/faq.mdx).

### Measure before tuning

Use the JUnit properties from the focused run to separate:
- model load duration;
- prompt evaluation duration and prompt token count;
- output evaluation duration and generated token count;
- total provider duration.

This determines whether the bottleneck is cold loading, prompt prefill, or token generation. Do not infer the cause from wall-clock time alone.

### Safe experiments, in order

1. **Check GPU residency and available VRAM.** Compare `ollama ps` before and during/after a request. On NVIDIA hardware, also inspect `nvidia-smi`. The 21% CPU / 79% GPU observation indicates partial offload; if the complete model does not fit, test a smaller model or a smaller quantization against the same held-out corpus.
2. **Keep the model loaded between probes.** Ollama's Generate API supports `keep_alive` (default five minutes). A longer value reduces repeated load time, but does not speed up tokens within one generation. See [Ollama Generate API](https://github.com/ollama/ollama/blob/main/docs/api.md).
3. **Measure context size before reducing it.** Ollama supports request `options.num_ctx`. Smaller contexts can reduce KV-cache memory pressure, but the Intent prompt must still fit with headroom. The current interpreter has a 24,000-byte prompt budget; do not set an 8K context without checking actual prompt token counts.
4. **Try Flash Attention and an 8-bit KV cache only if memory pressure is present.** Ollama documents `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0`; the latter uses approximately half the KV-cache memory of `f16`, with a small quality impact described by Ollama. These are server-level settings and require restarting the Ollama server to take effect. See [Ollama FAQ — Flash Attention and KV cache quantization](https://github.com/ollama/ollama/blob/main/docs/faq.mdx).
5. **Do not cap `num_predict` blindly.** Ollama exposes it as a request option, but a low cap can truncate the JSON response. First inspect the actual `eval_count` and verify `done_reason` before setting a role-specific limit.
6. **Compare a smaller quantized model.** The current Ollama Gemma 4 tags include `gemma4:12b-it-q4_K_M` at about 8.0 GB, while `gemma4:26b` is listed at 16–19 GB. The 12B Q4 tag is a useful first same-family comparison; it is not assumed to preserve the 26B model's semantic accuracy. Run the same held-out scenarios and compare latency, category accuracy, action-frame/argument recall, grounding failures and abstention quality. A faster model is useful only if semantic quality and safety remain acceptable. See the [Gemma 4 Ollama tags](https://ollama.com/library/gemma4/tags).

### Current scope boundary

This PR does not silently change Ollama context, sampling, quantization or GPU settings. Those choices are hardware- and workload-dependent. A follow-up provider-tuning change should expose narrowly scoped, role-specific `num_ctx`, `num_predict` and `keep_alive` settings only after the metrics above identify a justified configuration.
