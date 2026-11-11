# Context services

## Responsibility
Retrieve, expand, rank, select and render campaign context for application and LLM workflows. This package does not own campaign state.

## Modules (migrated into this package)
- memory_search_service.py — deterministic retrieval and public world-state export.
- context_builder.py — orchestration facade.
- context_expander.py — expands candidates.
- context_ranker.py — relevance ranking.
- context_renderer.py — selection and rendering.

The LLM-specific world-context projection lives in `services/llm_world/llm_world_context_renderer.py`. It belongs to prompt construction, not generic context retrieval. The active proposal path currently bypasses this package's retrieval/ranking/budget pipeline and projects the full world; see the `llm_world` package guide.

## Dependency rules
- Read through explicit collaborators and ports.
- Keep ranking/rendering deterministic where possible.
- Do not own persistence or call provider APIs.
- Preserve context budgets and ranking semantics.

## Pending work
- [ ] Reduce `ContextBuilder` only where a distinct policy boundary exists; retain its current orchestration contract unless a real consumer requires a different projection.
- [ ] Document source freshness and campaign revision assumptions for cached/persisted context.
- [x] Keep deterministic tests for character budgets, ranking and exclusion rules, including secret-event filtering; these do not cover the proposal-specific estimated-token budget.
- [ ] Provide a typed selected-record projection for the turn/application boundary to pass to the structured proposal builder without introducing a `context` -> `llm_world` dependency.
- [ ] Review duplicated context shaping between native turns and LLM prompts.
- [x] Keep rendering independent from transport response formatting.

## Migration status
All five context modules now live in this package. The former flat `services.memory_search_service` import path has been removed; import from this package's canonical modules.
