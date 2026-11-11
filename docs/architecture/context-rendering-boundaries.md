# Context rendering boundary

## Ownership

- `MemorySearchService` (`services/context/memory_search_service.py`) finds structured candidates from the supplied world snapshot and exports its public representation.
- `ContextExpander` follows active world relations and resolves related records.
- `ContextRanker` calculates candidate relevance.
- `ContextRenderer` converts structured records and recent turns into textual candidates, orders them, applies independent character budgets, and renders category sections.
- `ContextBuilder` validates input and coordinates those collaborators while preserving the public result shape.

## Contracts and invariants

- The structured context and recent-turn history retain independent character budgets.
- Candidate lines remain whole; oversized candidates are skipped rather than truncated.
- Candidate ordering remains score-first for selection and category/index order for final presentation.
- Category headers and localized field labels remain unchanged.
- Internal entity relevance/depth metadata is stripped before returning the public result.
- Rendering does not mutate the world snapshot or the structured source records.
- The public `ContextBuilder.build()` result keys and text contract remain compatible.

## Scope

`ContextRenderer` owns presentation and budget policy only. It does not search memory, traverse the world graph, access persistence, or mutate domain state. The current budgets are measured in characters, not model tokens.
