# LLM world-processing services

## Responsibility

Turn player intent and confirmed mechanics into bounded, typed proposals for
world operations. Model output is untrusted: it is parsed and classified here,
then semantically validated and applied by the world application boundary.

## Modules

- `llm_world_extractor.py` — coordinates the single structured `propose()` workflow and provider call.
- `llm_world_proposal_prompt_builder.py` — builds the player-intent proposal prompt from typed world context.
- `llm_world_proposal_validator.py` — validates response size and performs at most one compact, separately budgeted repair.
- `llm_world_response_parser.py` — decodes provider output and applies the model-proposable operation trust gate.
- `operation_registry.py` — immutable typed catalogue of parser-supported operations, model-proposable/internal trust classification and generated JSON schemas.
- `operation_parser.py` — structural parser; existence, campaign scope, permission and mutation checks remain in `WorldService` / `WorldApplier`.
- `llm_extraction_errors.py` — package error types.

The former narrative-first `extract()` API, its static prompt builder and its
prompt-section modules have been removed. There is no parallel legacy
world-mutation path.

## Active proposal pipeline

1. `TurnResolutionService` receives the player's original intent.
2. It asks `ContextBuilder.build_proposal_context()` for a bounded,
   typed `WorldContextProjection`, preserving the active character,
   current location and required dependencies.
3. `LLMWorldProposalPromptBuilder` renders the typed projection, active
   character sheet, resource balances, confirmed mechanics and the
   registry-generated operation contract.
4. The extractor checks the complete prompt against its budget before
   calling the provider.
5. `LLMWorldResponseParser` rejects internal-only and unsupported operation
   types before structural parsing.
6. The world application boundary performs semantic validation and applies
   the operations inside the transaction owned by the caller.
7. Presentation narration happens after the consequence commit.

`services/llm_world` depends on shared model contracts and never imports
`services.context`. The application/turn boundary owns context retrieval and
passes a typed projection inward.

## Budgets

| Environment variable | Default | Meaning |
|---|---:|---|
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_PROMPT_MAX_TOKENS` | 8192 | Complete proposal prompt upper bound |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_CONTEXT_MAX_TOKENS` | 4096 | Selected world-record budget |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_MAX_RESPONSE_CHARS` | 16000 | Maximum provider response size |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_REPAIR_MAX_TOKENS` | 2048 | Independent budget for the single repair request |

The current provider port does not expose an exact model tokenizer.
`estimate_tokens()` therefore uses a conservative one-UTF-8-byte-per-token
upper bound. The complete prompt, response and single repair are independently
bounded. Context selection fails closed rather than arbitrarily truncating
campaign facts.

## Dependency and safety rules

- Depend on the provider callable/port supplied by the composition root, not a concrete provider.
- Never write directly to SQLite or bypass typed operation validation.
- Keep prompt construction, parsing, validation and provider invocation distinct.
- Treat model output as untrusted input.
- Character-state operations remain excluded from the model-proposable allowlist; deterministic mechanics and application code remain authoritative.
- Keep world mutation in the world application boundary.
- Do not reintroduce a narrative-first extractor or a second prompt contract.

## Remaining work

- [ ] Add intent-specific operation subsets only when the application can classify intent reliably without hiding legitimate consequences.
- [ ] Add tokenizer-aware accounting if a selected provider exposes an explicit, reliable token-count API.
- [x] Add deterministic large-context proposal and bounded-repair probes that record selected-context size, prompt budget, ranking stability and secret-event exclusion (`tests/test_proposal_scale_quality.py`; PR #207; see [probe documentation](../../docs/quality/context-scale-probes-2026-11-12.md)).
- [ ] Add opt-in real-Ollama model-quality probes after the local environment is mounted; record model and settings.
- [x] Keep operation metadata centralized and model-proposable classification distinct from domain authorization.
