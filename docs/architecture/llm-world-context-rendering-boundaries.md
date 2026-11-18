# LLM world context rendering boundary

**Status:** active structured proposal context contract, aligned to the 2026-11-18 source baseline.

## Ownership

- `ContextBuilder` and `ProposalContextSelector` own deterministic retrieval, graph expansion, relevance ranking and bounded selection.
- `models/world_context_projection.py` defines the detached, typed projection and diagnostics contract.
- `TurnResolutionService` orchestrates context selection and passes the projection inward to `services/llm_world`.
- `LLMWorldProposalPromptBuilder` renders the single active structured consequence-proposal prompt from typed context, shared `PlayerIntentAnalysis`, trusted resolved references, confirmed mechanics and the operation registry.
- `LLMWorldExtractor.propose()` coordinates the provider call, response parsing, model-proposable operation gate and one bounded repair.
- Domain validation and `WorldService` remain authoritative for identity, permissions, resource constraints, campaign scope and mutation.
- `DMService` and external SillyTavern generation produce presentation prose only after consequence commit.

There is no active narrative-first extraction prompt or parallel extraction path. The former `LLMWorldPromptBuilder`/legacy extractor and `POST /integration/turn` route were retired. Do not document them as active ownership.

## Contracts and invariants

- The selector reads a supplied `WorldState`; it does not query SQLite or mutate canonical state.
- Selected records are deep-copied into a detached `WorldContextProjection`.
- Direct search results and related entities/relations/events are deterministically ranked. Item instances carry their item definition and relevant owner/location entities; resource balances carry definitions and owners; relations and events carry referenced entities.
- The current implementation requires one trusted active-character focus and preserves the current location, mandatory related records and dependency bundles. The broader product requirement for several controlled PJ and manually selected known entities is not yet implemented; see product requirements v0.2.
- Event visibility is applied before context selection. Secret/GM-only information fails closed and is not projected to the player/model-facing proposal path.
- Superseded events may be retained as labelled history; they are not current facts.
- Resource balances are rendered explicitly; resource definitions alone are not sufficient to represent current state.
- The selector has its own upper bound. The complete prompt, including static instructions, original player evidence and confirmed mechanics, is checked separately.
- The estimator counts UTF-8 bytes as a conservative upper bound, not exact model tokens. Prompt, output and repair budgets are independent.
- The renderer retains deterministic ordering and localized empty fallbacks.
- Do not introduce a direct `services.llm_world` → `services.context` dependency.
- Model output remains untrusted. The prompt registry is not an authorization mechanism; schema validity does not establish permission or factual truth.

## Related current references

- [Context services guide](../../services/context/README.md)
- [LLM world proposal prompt boundary](llm-world-proposal-prompt-boundary.md)
- [Turn pipeline contract](turn-pipeline-compatibility.md)
- [Current system state](current-state-2026-11-18.md)
