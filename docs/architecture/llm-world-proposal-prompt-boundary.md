# LLM proposal prompt boundary

## Ownership

- `LLMWorldProposalPromptBuilder` renders player-intent proposal instructions from `LLMWorldContextRenderer` output.
- `LLMWorldExtractor.propose()` validates input, invokes the provider and coordinates proposal parsing/validation.
- `LLMWorldProposalValidator` validates proposed operations and performs at most one schema-aware repair.
- `LLMWorldResponseParser` decodes provider JSON and validates typed world-operation results.
- `TurnResolutionService` selects the proposal path for durable turns and remains the orchestration boundary for future context projection.

## Contracts and invariants

- Prompt construction does not invoke the provider or parse operations.
- PR #161 removed the proposal builder's dependency on the legacy prompt builder and its marker-based text extraction.
- The active durable turn path uses `proposal_from_intent=True`; player intent is untrusted input, not confirmed narrative.
- Confirmed mechanics are included only when supplied by the deterministic engine.
- Model output remains an untrusted proposal; parsing and semantic application are separate authorities.
- The proposal path currently renders all known world collections through `LLMWorldContextRenderer` and does not yet apply relevance ranking or a size budget.
- Do not import `services.context` from `services.llm_world`; pass a typed projection from the turn/application boundary to preserve the dependency matrix.
- Proposal validation and its single repair attempt remain owned by `LLMWorldProposalValidator`.
