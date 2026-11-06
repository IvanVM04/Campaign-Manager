# Context services

## Responsibility
Retrieve, expand, rank, select and render campaign context for application and LLM workflows. This package does not own campaign state.

## Modules (migrated into this package)
- context_builder.py — orchestration facade.
- context_expander.py — expands candidates.
- context_ranker.py — relevance ranking.
- context_renderer.py — selection and rendering.

The LLM-specific world-context projection now lives in services/llm_world/llm_world_context_renderer.py. It consumes shared context output but belongs to LLM prompt construction, not generic context retrieval.

## Dependency rules
- Read through explicit collaborators and ports.
- Keep ranking/rendering deterministic where possible.
- Do not own persistence or call provider APIs.
- Preserve context budgets and ranking semantics.

## Pending work
- [ ] Reduce ContextBuilder only where a distinct policy boundary exists.
- [ ] Document source freshness and campaign revision assumptions.
- [ ] Add boundary tests for budgets, ranking stability and exclusion rules.
- [ ] Review duplicated context shaping between native turns and LLM prompts.
- [ ] Keep rendering independent from transport response formatting.

## Migration status
The four context modules now live in this package. The former flat `services.context_*` compatibility modules have been removed; import from this package's canonical modules.
