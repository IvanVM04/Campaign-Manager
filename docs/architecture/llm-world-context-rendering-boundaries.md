# LLM world-context rendering boundary

**Status:** current structured-proposal path, verified 2026-11-18  
**Code baseline:** `f4fb3914ebab4579118863796e6f6d4b7183d0cf` (PR #255).

## Ownership

- `ContextBuilder` and `ProposalContextSelector` own deterministic retrieval, graph expansion, relevance ranking and bounded selection.
- `models/world_context_projection.py` defines the detached typed projection and diagnostics contract. It depends on domain models, not services.
- `LLMWorldContextRenderer` renders a `TurnContext` or selected `WorldContextProjection` into prompt sections.
- `LLMWorldProposalPromptBuilder` renders the active consequence-proposal prompt using the selected projection, shared intent analysis, trusted resolved references, confirmed mechanics and the typed operation catalogue.
- `TurnResolutionService` owns orchestration across context selection, intent interpretation, mechanics adjudication and proposal generation.
- `LLMWorldExtractor.propose()` calls the provider and coordinates response parsing, trust classification and bounded validation/repair.
- `WorldService` and domain appliers own semantic validation and mutation; repositories own persistence.

The retired narrative-first extraction path and its static legacy prompt are not an active turn path. Do not document or restore a second narrative-extraction pipeline.

## Active projection and rendering contract

- Context selection reads a supplied `WorldState`; it does not query SQLite or mutate canonical state.
- The selected records are deep-copied into a detached subset.
- Direct search results and one-hop related entities/relations/events are deterministically ranked. Item instances retain item definition and owner/location dependencies; resource balances retain resource definitions and owners; relations/events retain referenced entities.
- The active character and current campaign-location entity are mandatory. If mandatory records cannot fit the selected-context budget, planning fails closed rather than silently dropping them.
- Campaign/session summaries and active-character conditions/exhaustion are rendered in their appropriate blocks. GM-only session notes and secret/GM-only events are not projected into player-facing proposal context.
- Event visibility and supersession are applied before context selection. Character-scoped event facts are restricted to the relevant character knowledge projection.
- Resource balances are rendered explicitly; resource definitions alone do not express inventory/economy state.
- The selected-context byte budget and complete rendered-prompt byte budget are separate limits. The proposal repair request also has its own small bound.
- The estimator uses a conservative UTF-8 byte upper bound because the provider port has no model tokenizer. It must not be described as an exact token count.
- Rendering is deterministic and uses localized empty-state fallbacks.
- The proposal registry is guidance/schema/trust classification, not authorization. Internal-only operations are rejected before domain construction; domain permissions/existence/resource constraints remain downstream.

## Trust and dependency boundaries

- The selector and renderer do not publish changes to canonical `WorldState`.
- LLM output remains untrusted even when it conforms to the generated JSON schema.
- Canonical IDs are added by deterministic resolvers, not invented by the model.
- A negative, hypothetical, interrogative, quoted, merely reported or uncertain claim cannot silently become a positive persistent relation.
- Do not introduce a direct `services.llm_world` → `services.context` dependency. The application/turn boundary passes the typed projection inward.
- Do not use a future player-selected context entity list as proof of new intent or permission; selection can add available facts only after the backend verifies their visibility.

## Current limitations and future requirements

The active turn path uses a bounded detached projection for consequence planning. The product requirements v0.2 additionally request a player-visible compendium, inline entity links/previews, pinned entity context selection, multi-character knowledge projections and configurable NPC per-field visibility. These are not fully implemented. The current projection still distinguishes the active character and event visibility; it does not yet provide a complete per-assertion provenance system for every free-text field.

See [services/context](../../services/context/README.md), [services/llm_world](../../services/llm_world/README.md), the [current architecture map](architecture-map-2026-11-18.md) and [product requirements](../product/product-requirements-2026-11-18.md).
