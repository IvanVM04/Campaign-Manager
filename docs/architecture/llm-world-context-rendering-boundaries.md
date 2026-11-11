# LLM world context rendering boundary

## Ownership

- `ContextBuilder` and `ProposalContextSelector` own deterministic retrieval, graph expansion, relevance ranking and bounded selection for the active structured proposal.
- `models/world_context_projection.py` defines the shared detached projection and diagnostics contract; it depends only on domain models.
- `LLMWorldContextRenderer` renders a `TurnContext` or a selected `WorldContextProjection` into localized prompt sections.
- `LLMWorldPromptBuilder` owns the long static instructions for the legacy narrative-extraction path.
- `LLMWorldProposalPromptBuilder` renders the active player-intent proposal prompt from a selected projection; it does not parse or rewrite the legacy prompt (PR #161).
- `TurnResolutionService` owns orchestration between the generic context pipeline and LLM proposal generation.

## Contracts and invariants

- The selector reads a supplied `WorldState`; it does not query SQLite or mutate canonical state.
- The selected records are deep-copied into a detached subset.
- Direct search results and one-hop related entities/relations/events are deterministically ranked. Item instances carry their item definition and relevant owner/location entities; resource balances carry resource definitions and owners; relations and events carry referenced entities.
- The active character entity is mandatory and is expanded before optional candidates are considered.
- Secret events are excluded from model-facing context.
- Resource balances are rendered explicitly; resource definitions alone are not sufficient to represent inventory/economy state.
- The selector has its own context upper bound. The complete prompt, including static instructions, player intent and confirmed mechanics, is checked against the total prompt upper bound.
- The estimator counts UTF-8 bytes as a conservative upper bound in the absence of a provider tokenizer; diagnostics label values as estimated tokens and never claim an exact model token count.
- The renderer retains deterministic ordering and localized empty fallbacks.
- Do not introduce a direct `services.llm_world` -> `services.context` dependency.
- The legacy extraction path still uses the full-world renderer and is separate from the bounded durable proposal path.
