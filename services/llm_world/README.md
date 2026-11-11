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

## Pending work
- [x] Decouple the proposal prompt builder from the legacy narrative-extraction prompt and remove marker-based text extraction (PR #161).
- [ ] Replace the proposal path's full-world projection with a typed, relevance-ranked context projection and an explicit estimated-token budget. Orchestration must preserve the package dependency matrix; `llm_world` must not import `services.context` directly.
- [ ] Centralize operation metadata/LLM allowlisting without exposing internal-only operations.
- [ ] Add prompt-size diagnostics and bounded repair context; assess provider invocation/retry as a separate boundary.
- [ ] Specify and test retry, timeout and repair limits; retries must not duplicate side effects.
- [ ] Test malformed output, unsupported operations, partial responses, provider failures and context-budget behavior with small/large campaign fixtures.
- [ ] Document the trust boundary from model proposal to deterministic validation/application.

## Migration status
All implementation modules live in `services/llm_world/`. PR #161 separated `LLMWorldProposalPromptBuilder` from the legacy narrative prompt: it now renders from `LLMWorldContextRenderer` directly. The legacy `LLMWorldPromptBuilder` remains for callers of `LLMWorldExtractor.extract()`; it is not used to construct the active durable player-intent proposal prompt. The structured proposal renderer still projects the full world without a relevance filter or size budget; this is the next prompt-pipeline improvement. The former flat `services.llm_extraction_errors` and `services.llm_world_*` compatibility modules have been removed. Import from this canonical package.
