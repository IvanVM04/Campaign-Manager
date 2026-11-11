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
- [ ] Remove the proposal builder's dependency on the legacy prompt builder and its marker-based text extraction; share a typed context projection instead.
- [ ] Introduce relevance-based context selection and an explicit token budget for structured proposals.
- [ ] Centralize operation metadata/LLM allowlisting without exposing internal-only operations.
- [ ] Audit remaining responsibilities and size of `LLMWorldExtractor`; assess provider invocation/retry as a separate boundary.
- [ ] Specify and test retry, timeout and repair limits; retries must not duplicate side effects.
- [ ] Test malformed output, unsupported operations, partial responses and provider failures.
- [ ] Document the trust boundary from model proposal to deterministic validation/application.

## Migration status
All eight implementation modules live in `services/llm_world/`. The former flat `services.llm_extraction_errors` and `services.llm_world_*` compatibility modules have been removed. Import from this canonical package.
