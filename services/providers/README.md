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

## Pending work
- [ ] Add provider contract tests covering success, timeout, unavailable provider and malformed response behavior.
- [ ] Document Ollama-specific assumptions and the error contract seen by application services.
- [ ] Decide retry ownership and avoid hidden duplicate retry layers; preserve the bounded proposal-repair policy in `llm_world`.
- [ ] Add structured-output/cancellation capabilities only when an actual provider or gameplay use case requires them.

## Migration status
Provider implementations now live in this package. Production and test consumers use the canonical `services.providers` API; the former flat modules under `services/` have been removed.
