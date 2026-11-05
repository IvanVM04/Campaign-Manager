# LLM world-processing services

## Responsibility
Construct world-extraction prompts, project world context, coordinate extraction, validate proposed operations and parse structured responses. Model output is always a proposal, never an authorized database mutation.

## Current modules (still in services/)
- llm_world_extractor.py — extraction workflow/provider coordination.
- llm_world_prompt_builder.py — extraction prompt.
- llm_world_context_renderer.py — dynamic context projection.
- llm_world_proposal_prompt_builder.py — player-intent proposal prompt.
- llm_world_proposal_validator.py — proposal validation and repair.
- llm_world_response_parser.py — structured response decoding.
- llm_extraction_errors.py — extraction errors.

## Dependency rules
- Depend on the provider port, not a concrete provider.
- Never write directly to SQLite or bypass typed operation validation.
- Keep prompt construction, parsing, validation and provider invocation distinct.
- Treat model output as untrusted input and fail closed on malformed/unsupported operations.

## Pending work
- [ ] Audit remaining responsibilities and size of LLMWorldExtractor; assess provider invocation/retry as a separate boundary.
- [ ] Specify and test retry, timeout and repair limits; retries must not duplicate side effects.
- [ ] Review shared prompt contracts without introducing a generic prompt framework.
- [ ] Test malformed output, unsupported operations, partial responses and provider failures.
- [ ] Document the trust boundary from model proposal to deterministic validation/application.
- [ ] Remove compatibility shims only after all callers migrate.

## Migration status
This is a documented target boundary only. Source modules and imports remain in services/ until a separate migration preserves compatibility.
