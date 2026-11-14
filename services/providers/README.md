# LLM provider adapters

## Responsibility
Define the external LLM boundary: provider contract, Ollama transport adapter, role-specific configuration and deterministic test double.

## Modules
- `llm_provider.py` — text-generation port, optional structured-generation capability and provider error.
- `ollama_provider.py` — concrete Ollama HTTP adapter.
- `llm_settings.py` — validated URL, model, timeout and role-specific byte-budget configuration for narrative, extraction, intent and mechanics roles.
- `fake_llm_provider.py` — deterministic provider for tests.

## Dependency rules
- Application services depend on `LLMProvider`, never directly on Ollama transport.
- Adapters do not own campaign state, persistence or domain decisions.
- Validate settings at startup/composition boundaries.
- Test doubles implement the same contract as production adapters.
- Keep provider-internal imports relative; consumers import from `services.providers`.

## Current implementation
- `LLMSettings` validates provider URL, model names and finite positive timeouts at startup.
- Narrative, extraction, intent and mechanics roles can use separate model and timeout settings.
- Intent, mechanics and extraction have independent UTF-8 byte budgets:
  `CAMPAIGN_MANAGER_LLM_INTENT_PROMPT_MAX_BYTES`,
  `CAMPAIGN_MANAGER_LLM_INTENT_CONTEXT_MAX_BYTES`,
  `CAMPAIGN_MANAGER_LLM_MECHANICS_PROMPT_MAX_BYTES`,
  `CAMPAIGN_MANAGER_LLM_MECHANICS_CONTEXT_MAX_BYTES`,
  `CAMPAIGN_MANAGER_LLM_EXTRACTION_PROMPT_MAX_BYTES`,
  `CAMPAIGN_MANAGER_LLM_EXTRACTION_CONTEXT_MAX_BYTES` and
  `CAMPAIGN_MANAGER_LLM_EXTRACTION_REPAIR_MAX_BYTES`. Existing extraction and
  mechanics `*_MAX_TOKENS` environment names remain supported as deprecated
  byte-budget aliases.
- The intent role emits only the shared semantic analysis schema; the mechanics role emits only a mechanics decision. Extraction remains a separate downstream proposal responsibility.
- `estimate_tokens()` counts UTF-8 bytes as a conservative upper bound; it is not a model-specific tokenizer. All role budgets and diagnostics name this unit explicitly.
- `OllamaProvider` performs non-streaming text requests and supports native JSON Schema constraints through `generate_structured(prompt, schema=...)`; transport, HTTP and malformed-response failures normalize to `LLMProviderError`.
- `FakeLLMProvider` supports fixed responses, prompt-matched responses and injected failures.
- `LLMProvider.generate_structured()` is a backwards-compatible capability: text-only providers use the fallback, while Ollama overrides it with native constraints. The caller still validates semantic content and trust boundaries independently.

## Contract validation status
- [x] Deterministic adapter tests cover successful requests, timeout, unavailable provider/connection failure, HTTP failures with and without provider error JSON, malformed/non-object JSON, malformed response payloads and prompt/config validation (`tests/test_ollama_provider.py`).
- [x] The adapter performs one transport attempt and does not hide retries. Proposal repair remains a separate, bounded application-level behavior in `services/llm_world`.
- [x] The fake provider contract is covered for fixed/prompt-selected results, injected errors and call/prompt tracking (`tests/test_llm_provider.py`).
- [ ] Run live Ollama acceptance with the configured local model. Unit tests do not prove model availability, model quality, latency or compatibility with local hardware.
- [x] Structured JSON Schema generation uses separate intent-only, pending-correction and mechanics-only response contracts. The former combined intent/mechanics schema remains for temporary compatibility callers; streaming/cancellation remain deferred.

Ollama error normalization and timeout handling were strengthened in PR #203. Keep deterministic provider tests in CI and live model checks opt-in.

## Diagnostics

Provider success/failure duration, role, configured model where available,
response character count and stable error type are emitted through the shared
[observability configuration](../../docs/architecture/observability-and-diagnostics.md).
Never log API keys, full prompts or model completions.

## Migration status
Provider implementations now live in this package. Production and test consumers use the canonical `services.providers` API; the former flat modules under `services/` have been removed.
