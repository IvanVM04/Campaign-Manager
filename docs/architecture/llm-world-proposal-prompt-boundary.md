# LLM proposal prompt boundary

## Ownership

- `TurnResolutionService` selects the structured proposal path for durable turns and owns orchestration of the context projection.
- `ContextBuilder.build_proposal_context()` uses the generic context search/expansion/ranking pipeline and returns a typed `models.world_context_projection.WorldContextProjection`.
- `LLMWorldProposalPromptBuilder` renders static proposal instructions with the selected projection, allowed operation types and confirmed mechanics.
- `LLMWorldExtractor.propose()` validates input, invokes the provider, records size/selection diagnostics and coordinates parsing/validation.
- `OperationMetadataRegistry` is the single typed catalog for parser-supported operations, explicit model-proposable/internal classification, dataclass-derived JSON Schemas, field descriptions, required fields and examples.
- `OperationParser` uses that catalog for operation builders and reference-field normalization. Its structural parser remains separate from world-state validation.
- `LLMWorldProposalPromptBuilder` renders a compact registry-derived typed manifest; `LLMWorldResponseParser` checks the same registry before parsing and rejects internal-only or unknown operation types.
- Domain existence, permissions, resource constraints and atomic mutation remain in the world application layer; the prompt registry is not an authorization system.
- `LLMWorldProposalValidator` caps output size and performs at most one compact bounded repair.

## Contracts and invariants

- Prompt construction does not invoke the provider or parse operations.
- PR #161 removed the proposal builder's dependency on the legacy narrative-extraction prompt and marker-based text extraction.
- The active durable turn path passes the player's normalized intent to `LLMWorldExtractor.propose()`; player intent is untrusted input, not confirmed narrative. There is no separate boolean switch that upgrades intent into confirmed facts.
- The active path selects world records by intent and expands them through relevant relationships. Required entity/item/resource dependencies travel with their parent records.
- The active character and current campaign-location entities are mandatory. Campaign/session summaries and active-character conditions/exhaustion are rendered separately. If mandatory entity records cannot fit the context budget, planning fails closed rather than silently dropping them.
- Secret events remain excluded. The selected projection is detached from the runtime world; it never mutates canonical state.
- The shared estimator is a pessimistic one-UTF-8-byte-per-token upper bound because the provider contract has no tokenizer method. The complete rendered prompt has a separate upper bound.
- Confirmed mechanics are included only when supplied by the deterministic engine.
- The registry marks each operation explicitly as model-proposable or internal-only. Character-state operations are internal-only; the response parser rejects them before object construction. The deterministic rules/application pipeline remains authoritative.
- Full JSON Schemas are derived from operation dataclass definitions, while the prompt receives a compact typed manifest to preserve room for selected world context. Required fields and declared types stay aligned with constructors. Reference fields are explicitly declared once in registry metadata and drive both prompt rendering and ID normalization.
- There is no separate typed permission model in the current domain; future authorization policy must be implemented as a domain/application contract, not inferred from prompt wording.
- Model output remains an untrusted proposal. Parsing, semantic validation and mutation are separate authorities.
- The prompt distinguishes desire, attempt, failure/negation, hypothesis and explicitly established fact; persistence is proposed only for new, durable, grounded information.
- The context renderer exposes selected entity descriptions and notes, item descriptions/significance/notes, instance conditions and notes, and resource notes. The selector already budgets the underlying record payloads; the renderer must not discard those useful fields.
- Operation field notes explain identity/category/description and relationship/event semantics. The registry is guidance for model output, not a domain authorization policy.
- See the [AI world-understanding roadmap](../quality/ai-world-understanding-roadmap-2026-11-12.md) for the sequenced retrieval, intent, provenance and narrative-quality work.
- The repair request never resends the full world prompt. It includes a bounded error and bounded invalid-response excerpt and is limited to one attempt.
- Do not import `services.context` from `services.llm_world`; the turn/application boundary passes the shared typed projection.


## Evaluation and acceptance

Deterministic contracts are kept in the normal test suite; real-model probes
are opt-in and must assert semantic outcomes rather than exact wording. See
[Prompt evaluation](../quality/prompt-evaluation-2026-11-12.md) for the current
corpus, local Ollama command and planned semantic cases. A live model result
does not replace the separate SillyTavern integration smoke test.
