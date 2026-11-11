# LLM world-processing services

## Responsibility
Construct world-extraction prompts, project world context, coordinate extraction, validate proposed operations and parse structured responses. Model output is always a proposal, never an authorized database mutation.

## Modules
- `llm_world_extractor.py` — extraction workflow and provider coordination.
- `llm_world_prompt_builder.py` — legacy narrative-extraction prompt.
- `llm_world_context_renderer.py` — dynamic world-context projection.
- `llm_world_proposal_prompt_builder.py` — player-intent proposal prompt.
- `llm_world_proposal_validator.py` — proposal validation and one bounded repair.
- `llm_world_response_parser.py` — provider-response decoding and LLM-specific operation trust checks.
- `operation_parser.py` — canonical structural parser that normalizes untrusted operation payloads into typed operations; domain existence and permission checks remain in `WorldService` / `WorldApplier`.
- `llm_extraction_errors.py` — package error type.

## Dependency rules
- Depend on the provider callable/port supplied by the composition root, not a concrete provider.
- Never write directly to SQLite or bypass typed operation validation.
- Keep prompt construction, parsing, validation and provider invocation distinct.
- Treat model output as untrusted input and fail closed on malformed/unsupported operations.
- Keep world mutation in the world application boundary.

## Verified prompt-size findings

- The active durable proposal path calls `LLMWorldProposalPromptBuilder`, which renders every supported world record through `LLMWorldContextRenderer`; it does not rank records by player intent or enforce a prompt/token budget.
- `ContextBuilder` already provides deterministic retrieval, relation expansion, ranking and 6,000/2,000-character budgets for world/recent-turn context. Those character budgets are not token budgets and are not applied to the active proposal path.
- The legacy `LLMWorldPromptBuilder` is 2,193 lines / 46,851 characters and remains behind `LLMWorldExtractor.extract()` for the deprecated narrative-first route. It is not used by the active durable structured proposal path.
- `LLMWorldProposalValidator.parse_with_repair()` makes one retry, but the repair prompt repeats the full original prompt, validation error and full invalid provider response. Retry count is bounded; repair input size is not.
- The validator reads the parser's private `_BUILDERS` mapping to determine allowed operation types.

## Pending work — ordered by risk
- [ ] **P0 — Context selection:** typed, read-only, intent-relevant projection at the turn/application boundary; preserve mandatory character, scene, permissions and confirmed mechanics; deterministic ordering; estimated-token budget and provider safety margin. Do not add a direct `llm_world` -> `context` dependency or truncate arbitrary strings.
- [ ] **P0 — Repair bounds:** cap provider response size and define a separate repair prompt budget; send a bounded validation summary rather than an unbounded invalid response; retain exactly one repair and fail closed.
- [ ] **P1 — Diagnostics:** selected/excluded counts, rendered characters, estimated tokens and budget utilization without logging campaign text.
- [ ] **P1 — Operation metadata:** public typed metadata distinguishing model-proposable from internal-only operations, schemas and prompt descriptions.
- [ ] **P2 — Regression coverage:** small/medium/large campaigns, mandatory-fact retention, stable ordering, secret-event exclusion, output/repair limits and budget overflow.
- [ ] **P2 — Provider contract:** document timeout/retry ownership and prove retries cannot duplicate side effects.
- [ ] Document the trust boundary from model proposal to deterministic validation/application.

## Migration status
All implementation modules live in `services/llm_world/`. PR #161 separated `LLMWorldProposalPromptBuilder` from the legacy narrative prompt: it now renders from `LLMWorldContextRenderer` directly. The legacy `LLMWorldPromptBuilder` remains for callers of `LLMWorldExtractor.extract()`; it is not used to construct the active durable player-intent proposal prompt. The structured proposal renderer still projects the full world without a relevance filter or size budget; this is the next prompt-pipeline improvement. The former flat `services.llm_extraction_errors` and `services.llm_world_*` compatibility modules have been removed. Import from this canonical package.
