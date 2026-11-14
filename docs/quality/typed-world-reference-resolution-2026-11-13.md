# Typed world-reference resolution — PR #222

**Status:** implemented on `feat/222-typed-world-reference-evaluation`; live-model and SillyTavern acceptance remain separate.
**Purpose:** resolve references to world records that are not `Entity` records without merging their ID namespaces or treating an object definition as a physical copy.

## Supported referent categories

| Semantic kind | Canonical source | Identifier namespace |
|---|---|---|
| `item_definition` | `WorldState.items` | item ID |
| `item_instance` | active `WorldState.item_instances` joined to its `Item` definition | physical instance ID |
| `resource` | `WorldState.resources` | resource ID |
| `event` | visible `WorldState.events` | event string ID |

Character, creature, faction and location identity remains handled by `EntityReferenceResolver` and `ConversationReferenceResolver`. The conversation resolver now skips the four non-entity semantic kinds so an entity with a similar name cannot steal a typed item/resource/event reference.

## Resolution contract

- The resolver consumes the visibility-filtered `WorldContextProjection.world` and at most six recent turns already scoped to the active SillyTavern conversation.
- Direct matching is restricted to the declared semantic kind. It considers canonical names and descriptive text; competing physical copies with the same item definition remain ambiguous.
- Anaphoric matching uses literal mention evidence, recency, player-authored focus and topic continuity. Narrator evidence is retained as narrator evidence, not relabelled as player input.
- Item definitions and physical copies are distinct. A definition ID is never substituted for an instance ID.
- Inactive item instances are excluded. GM-only and secret events are excluded. Character-scoped events require the active character to be in `known_by_entity_ids`.
- When multiple candidates remain tied, the resolver asks for clarification rather than selecting one.
- Resource balances are not treated as resource definitions. Resolving the kind of resource does not decide which holder's balance is intended; that requires an explicit owner/holder relation and the deterministic domain layer.

## Proposal integration

`TurnResolutionService` passes typed references to `LLMWorldExtractor`. The prompt displays category and canonical ID in a separate section from entity references and explicitly instructs the proposal model not to exchange IDs between namespaces. These references are backend-produced evidence only: they do not authorize a write, visibility change, transfer, or operation.

No provider call is added. The normal shared interpretation remains the source for mechanics and consequences.

## Evaluation additions

- Deterministic tests cover item definition vs instance, duplicate physical copies, anaphoric item references, resources, public/character/GM visibility, inactive instances and narrator-only evidence.
- Semantic frame evaluation now records argument/relation slot precision, recall and F1 using multiset matching. Extra or duplicated arguments/claims are false positives, not invisible additions.
- An opt-in real-Ollama probe exercises an evidence-bound recipient correction on a still-pending intent.

## Remaining limits

- The resolver does not yet resolve resource balances by holder, arbitrary item nicknames, pronoun gender/number, broad paraphrase, causal relations or long-distance ellipsis.
- Events are resolved only when already present in the visibility-filtered projection; this layer never infers event existence.
- Matching thresholds must be evaluated against real campaign data. Embeddings/vector storage remain deferred until held-out measurements show a material gain.
- Deterministic CI validates the application contract, not the configured model's semantic accuracy. Run the `real_llm` suite and the two-chat SillyTavern acceptance checklist separately.
