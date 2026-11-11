# LLM world context rendering boundary

## Ownership

- `LLMWorldContextRenderer` projects a `TurnContext` world snapshot into prompt-ready sections.
- `LLMWorldPromptBuilder` owns the long static instructions and assembles the legacy narrative-extraction prompt.
- `LLMWorldProposalPromptBuilder` reuses the typed renderer output for player-intent proposals; it no longer parses or rewrites the legacy prompt (PR #161).
- `LLMWorldExtractor` coordinates provider invocation, response decoding, operation parsing and proposal validation.

## Contracts and invariants

- The renderer is read-only: it does not mutate `WorldState` or its records.
- Secret events are excluded from model-facing context.
- Missing collections retain their existing localized fallback labels.
- Active-character markers and field formatting remain deterministic.
- The renderer currently includes all known records in its supported collections; it does not rank by player intent or enforce a token/character budget.
- The active proposal path therefore needs a relevance-ranked, bounded projection supplied at the turn/application boundary.
- The narrative DM and mechanics-adjudication paths use `ContextBuilder` and its character budgets; this does not currently bound the structured proposal renderer.
- Do not introduce a direct `services.llm_world` -> `services.context` dependency; keep ownership and dependency direction explicit.
