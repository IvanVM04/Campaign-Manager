# LLM provider adapters

## Responsibility
Define the external LLM boundary: provider contract, Ollama transport adapter, role-specific configuration and deterministic test double.

## Modules
- `llm_provider.py` — minimal `generate(prompt) -> str` port and provider error.
- `ollama_provider.py` — concrete Ollama HTTP adapter.
- `llm_settings.py` — validated URL, model and timeout configuration for narrative, extraction and mechanics roles.
- `fake_llm_provider.py` — deterministic provider for tests.

## Dependency rules
- Application services depend on `LLMProvider`, never directly on Ollama transport.
- Adapters do not own campaign state, persistence or domain decisions.
- Validate settings at startup/composition boundaries.
- Test doubles implement the same contract as production adapters.
- Keep provider-internal imports relative; consumers import from `services.providers`.

## Current implementation
- `LLMSettings` validates provider URL, model names and finite positive timeouts at startup.
- Narrative, extraction and mechanics roles can use separate model and timeout settings.
- `OllamaProvider` performs a non-streaming HTTP request and normalizes transport, HTTP and malformed-response failures to `LLMProviderError`.
- `FakeLLMProvider` supports fixed responses, prompt-matched responses and injected failures.
- `LLMProvider` remains a deliberately small text-generation contract; it does not promise structured output, streaming or cancellation.

## Contract validation status
- [x] Deterministic adapter tests cover successful requests, timeout, unavailable provider/connection failure, HTTP failures with and without provider error JSON, malformed/non-object JSON, malformed response payloads and prompt/config validation (`tests/test_ollama_provider.py`).
- [x] The adapter performs one transport attempt and does not hide retries. Proposal repair remains a separate, bounded application-level behavior in `services/llm_world`.
- [x] The fake provider contract is covered for fixed/prompt-selected results, injected errors and call/prompt tracking (`tests/test_llm_provider.py`).
- [ ] Run live Ollama acceptance with the configured local model. Unit tests do not prove model availability, model quality, latency or compatibility with local hardware.
- [ ] Add structured-output/streaming/cancellation capabilities only when an actual provider or gameplay use case requires them.

Ollama error normalization and timeout handling were strengthened in PR #203. Keep deterministic provider tests in CI and live model checks opt-in.

## Migration status
Provider implementations now live in this package. Production and test consumers use the canonical `services.providers` API; the former flat modules under `services/` have been removed.
