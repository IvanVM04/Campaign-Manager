# LLM proposal prompt boundary

## Ownership

- `LLMWorldProposalPromptBuilder` adapts the world-extraction context into a player-intent proposal prompt.
- `LLMWorldExtractor` validates public inputs, invokes the provider, and coordinates proposal validation.
- `LLMWorldProposalValidator` parses proposed operations and performs at most one schema-aware repair.
- `LLMWorldResponseParser` decodes provider JSON and validates typed world-operation results.

## Contracts and invariants

- Prompt construction does not invoke the provider or parse operations.
- Player intent is inserted as untrusted input; it is not represented as confirmed narrative.
- Confirmed mechanics are included only when supplied by the deterministic engine.
- Existing context sections and end markers remain required; malformed context raises `LLMExtractionError`.
- Proposal validation and its single repair attempt remain owned by `LLMWorldProposalValidator`.
