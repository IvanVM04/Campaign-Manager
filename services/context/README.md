# Context services

## Responsibility
Retrieve, expand, rank, select and render campaign context for application and LLM workflows. This package does not own campaign state.

## Current modules (still in services/)
- context_builder.py — orchestration facade.
- context_expander.py — expands candidates.
- context_ranker.py — relevance ranking.
- context_renderer.py — selection and rendering.

The LLM-specific world-context projection is currently llm_world_context_renderer.py and is proposed for llm_world/.

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
This is a documented target boundary only. Source modules and imports remain in services/ until a separate migration preserves compatibility.
