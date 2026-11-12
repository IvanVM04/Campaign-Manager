# Context services

## Responsibility
Retrieve, expand, rank, select and render campaign context for application and LLM workflows. This package does not own campaign state.

## Modules (migrated into this package)
- memory_search_service.py — deterministic retrieval and public world-state export.
- context_builder.py — orchestration facade.
- context_expander.py — expands candidates.
- context_ranker.py — relevance ranking.
- context_renderer.py — ranked character-budget rendering for narrative context.
- proposal_context_selector.py — intent-ranked record selection with dependency-aware bundles and a conservative token upper bound.

The LLM-specific world-context projection is a shared typed model in `models/world_context_projection.py`; its LLM renderer remains in `services/llm_world`. The active proposal flow is orchestrated here without introducing a `context` -> `llm_world` dependency.

## Dependency rules
- Read through explicit collaborators and ports.
- Keep ranking/rendering deterministic where possible.
- Do not own persistence or call provider APIs.
- Preserve context budgets and ranking semantics.

## Proposal context contract

`ContextBuilder.build_proposal_context()` exposes the proposal-specific path while preserving the existing narrative `build()` API and its character budgets.

- Search, graph expansion and ranking are reused from the existing deterministic collaborators.
- The active character is mandatory; owned records and other related records are candidates ranked against the player intent.
- Relations retain referenced entities; item instances retain item definitions and owner/location entities; resource balances retain resource definitions and owners; events retain linked entities.
- Secret events remain excluded by the existing search/export and expander contracts.
- Selected domain records are deep-copied into a detached `WorldState` subset.
- `ContextProjectionDiagnostics` provides available/candidate/selected/excluded counts and estimated use of the context budget.

The byte-based budget is an upper bound rather than a model-specific token count. The LLM package checks the final rendered prompt independently. The selector raises `ProposalContextBudgetError` rather than dropping mandatory player facts.

## Remaining work
- [ ] Add representative medium/large campaign probes for stable ranking, dependency expansion, mandatory character/location retention, budget exhaustion and non-mutation. Keep deterministic probes in CI; use opt-in live Ollama probes for model-quality evaluation.
- [ ] Revisit source freshness/campaign-revision assumptions only if a context projection is cached or persisted; the current selector builds a detached projection from the supplied state.
- [ ] Consider richer semantic retrieval or tokenizer-aware accounting only after representative workloads or a provider tokenizer contract justify them.
- [x] Keep rendering independent from transport response formatting.
- [x] Preserve the existing ContextBuilder facade unless a distinct policy boundary emerges; no broad decomposition is currently justified.

## Migration status
The five generic context modules plus `proposal_context_selector.py` live in this package. The former flat `services.memory_search_service` import path has been removed; import from this package's canonical modules.
