# LLM provider adapters

## Responsibility
Define and implement external LLM provider boundaries: provider contracts, settings, transport, timeouts and test doubles.

## Current modules (still in services/)
- llm_provider.py — provider port.
- ollama_provider.py — Ollama adapter.
- llm_settings.py — configuration.
- fake_llm_provider.py — test provider.

## Dependency rules
- Application services depend on the provider port, not directly on Ollama.
- Adapters do not own campaign state, persistence or domain decisions.
- Validate settings at startup/composition boundaries.
- Test doubles implement the same contract as production adapters.

## Current implementation
- LLMSettings validates provider URL, model names and finite positive timeouts at startup.
- Narrative, extraction and mechanics roles are constructed explicitly and can use separate model and timeout settings.
- OllamaProvider is the concrete HTTP adapter; FakeLLMProvider is used by tests.
- LLMProvider is currently a small generate(prompt) abstraction, not a structured-output or streaming capability contract.

## Pending work
- [ ] Add provider contract tests covering success, timeout, unavailable provider and malformed response behavior.
- [ ] Document Ollama-specific assumptions and the error contract seen by application services.
- [ ] Decide retry ownership and avoid hidden duplicate retry layers; preserve the bounded proposal-repair policy in llm_world.
- [ ] Add structured-output/cancellation capabilities only when an actual provider or gameplay use case requires them.

## Migration status
This remains a documented target boundary only. Provider source modules and imports remain under services/; move them into this package after import consumers and test doubles have been mapped.
