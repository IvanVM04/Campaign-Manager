# Context services

## Responsibility
Retrieve, expand, rank, select and render campaign context for application and LLM workflows. This package does not own campaign state.

## Modules (migrated into this package)
- memory_search_service.py — deterministic retrieval and active-character-scoped player export.
- entity_reference_resolver.py — explicit name/alias/role matching with ambiguity abstention.
- conversation_reference_resolver.py — ranks visible discourse candidates from typed, speaker-separated player-input/narration evidence, semantic-kind compatibility and recency; returns evidence and abstains when the margin is insufficient.
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
- Event visibility is applied before context selection: public events are shared, character-scoped events require the active character to be in their known-by set, and GM-only/legacy secret events fail closed.
- Superseded events remain available as labelled history; they are not treated as current facts.
- Player projections omit internal known-by character ID lists. The active character is supplied by trusted runtime state, never from player request text.
- Selected domain records are deep-copied into a detached `WorldState` subset.
- `ContextProjectionDiagnostics` provides available/candidate/selected/excluded counts and estimated use of the context budget.

The byte-based budget is an upper bound rather than a model-specific token count. The LLM package checks the final rendered prompt independently. The selector raises `ProposalContextBudgetError` rather than dropping mandatory player facts.

## Remaining work
- [x] Preserve deterministic retrieval, dependency bundles, mandatory character/location facts, budget failure and non-mutation at medium/large campaign scale (PR #207).
- [x] Render selected entity descriptions and contextual notes so the model can reason about known state rather than seeing only names and types (PR #210).
- [x] Add explicit, bounded entity aliases through the domain, bootstrap API, read model, structured operations and SQLite migration 031 (roadmap PR #211).
- [x] Resolve canonical names and explicit aliases with accent-insensitive normalization; descriptions and notes remain lower-confidence fallbacks, and ambiguous references return no selected entity IDs.
- [x] Record resolution status, match kind and candidate count in the detached proposal projection without storing the raw player query.
- [x] Add conversation-scoped, visibility-filtered deterministic reference resolution with bounded recency and ambiguity abstention (PR #216).
- [ ] Expand labelled coverage for speaker attribution, correction chains, broader ellipsis and semantic paraphrases; do not claim general coreference.
- [ ] Revisit source freshness/campaign-revision assumptions only if a context projection is cached or persisted; the current selector builds a detached projection from the supplied state.
- [ ] Consider tokenizer-aware accounting only after a provider exposes a reliable tokenizer contract.
- [x] Keep rendering independent from transport response formatting.
- [x] Apply the same event visibility policy to direct search, graph expansion, proposal selection and public export.
- [x] Preserve the existing ContextBuilder facade unless a distinct policy boundary emerges; no broad decomposition is currently justified.

## Migration status
The five generic context modules plus `proposal_context_selector.py` live in this package. The former flat `services.memory_search_service` import path has been removed; import from this package's canonical modules.


## Multi-signal retrieval

`MemorySearchService.search_many(world, queries)` unions independent retrieval
signals in stable order and deduplicates records by category-local ID. The
primary query must be first. Supplemental queries add candidates but do not
replace the primary query used by the context renderer and ranker.

`ContextBuilder.build(..., supplemental_queries=...)` and
`ContextBuilder.build_proposal_context(..., supplemental_queries=...)` accept
optional extra signals. Existing callers remain compatible.

The SillyTavern adapter maps the current player action to its primary query and
the configured campaign-scope text to an optional supplemental query. Its
`retrieval_diagnostics` contains only query/record counts; it never echoes the
actual search text.

Entity-reference resolution continues to prioritize canonical names and
explicit aliases. Descriptive references can now match shared, more-specific
terms inside a longer player sentence. When descriptive candidates remain
similarly plausible, the resolver reports ambiguity and emits no singular
entity ID. The memory search may still retain the descriptive candidates as
retrieval evidence; that is not a resolved identity. Explicit name/alias
collisions remain fail-closed and return no candidate records.

The turn resolver supplies literal target mentions and a bounded selection of
recent visible turns. The dedicated conversation resolver supports a narrow
subset of Spanish/English pronouns, same-object references and “other
[role]” references. It selects only active entities present in the caller's
visibility-filtered world and only when recent history yields one unique
antecedent. Multiple candidates, hidden entities and missing evidence remain
unresolved and require clarification. This is not general natural-language
coreference: broader ellipsis, correction chains and paraphrases remain open
and require a labelled evaluation corpus.
