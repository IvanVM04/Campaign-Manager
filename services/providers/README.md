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

## Pending work
- [ ] Verify narrative, extraction and mechanics roles receive intended models and timeouts.
- [ ] Make provider construction/configuration explicit in runtime composition.
- [ ] Define behavior for unavailability, timeouts, malformed responses and cancellation.
- [ ] Add provider contract tests for fake and production adapter boundaries.
- [ ] Document supported capabilities and Ollama-specific assumptions.
- [ ] Decide retry ownership and avoid hidden duplicate retry layers.

## Migration status
This is a documented target boundary only. Source modules and imports remain in services/ until a separate migration preserves compatibility.
