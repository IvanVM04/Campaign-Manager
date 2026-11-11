# LLM proposal prompt boundary

## Ownership

- `TurnResolutionService` selects the structured proposal path for durable turns and owns orchestration of the context projection.
- `ContextBuilder.build_proposal_context()` uses the generic context search/expansion/ranking pipeline and returns a typed `models.world_context_projection.WorldContextProjection`.
- `LLMWorldProposalPromptBuilder` renders static proposal instructions with the selected projection, allowed operation types and confirmed mechanics.
- `LLMWorldExtractor.propose()` validates input, invokes the provider, records size/selection diagnostics and coordinates parsing/validation.
- `OperationParser.model_proposable_operation_types()` exposes the public sorted allowlist. The parser still performs structural normalization; domain and permission validation remain in the world application layer.
- `LLMWorldProposalValidator` caps output size and performs at most one compact bounded repair.

## Contracts and invariants

- Prompt construction does not invoke the provider or parse operations.
- PR #161 removed the proposal builder's dependency on the legacy narrative-extraction prompt and marker-based text extraction.
- The active durable turn path passes `proposal_from_intent=True`; player intent is untrusted input, not confirmed narrative.
- The active path selects world records by intent and expands them through relevant relationships. Required entity/item/resource dependencies travel with their parent records.
- The active character and current campaign-location entities are mandatory. Campaign/session summaries and active-character conditions/exhaustion are rendered separately. If mandatory entity records cannot fit the context budget, planning fails closed rather than silently dropping them.
- Secret events remain excluded. The selected projection is detached from the runtime world; it never mutates canonical state.
- The shared estimator is a pessimistic one-UTF-8-byte-per-token upper bound because the provider contract has no tokenizer method. The complete rendered prompt has a separate upper bound.
- Confirmed mechanics are included only when supplied by the deterministic engine.
- The model-proposable type list excludes character-state operations; the deterministic rules/application pipeline remains authoritative. There is no separate typed permission model in the current domain; future authorization policy must be implemented as a domain/application contract, not inferred from prompt wording.
- Model output remains an untrusted proposal. Parsing, semantic validation and mutation are separate authorities.
- The repair request never resends the full world prompt. It includes a bounded error and bounded invalid-response excerpt and is limited to one attempt.
- Do not import `services.context` from `services.llm_world`; the turn/application boundary passes the shared typed projection.
