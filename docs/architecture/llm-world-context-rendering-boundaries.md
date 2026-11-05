# LLM world context rendering boundary

## Ownership

- `LLMWorldContextRenderer` projects the current `TurnContext` world snapshot into prompt-ready sections for the extractor.
- `LLMWorldPromptBuilder` owns the static extraction instructions and assembles the final prompt from the rendered sections and narrative.
- `LLMWorldExtractor` coordinates provider invocation, response decoding, operation parsing, and proposal validation.

## Contracts and invariants

- The renderer is read-only: it does not mutate `WorldState` or its records.
- Secret events are excluded from the model-facing context.
- Missing collections retain their existing localized fallback labels.
- Active-character markers and all existing field formatting remain unchanged.
- The prompt's static instructions, section order, and narrative placement remain owned by the prompt builder.
- This extraction changes responsibility boundaries only; it does not alter the prompt contract or operation semantics.
