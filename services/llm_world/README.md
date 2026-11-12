# LLM world-processing services

## Responsibility
Construct world-extraction prompts, project world context, coordinate extraction, validate proposed operations and parse structured responses. Model output is always a proposal, never an authorized database mutation.

## Modules
- `llm_world_extractor.py` — extraction workflow and provider coordination.
- `llm_world_prompt_builder.py` — stable façade for the legacy narrative-extraction prompt.
- `legacy_prompt_sections/` — ordered static instruction sections grouped by rule family; dynamic campaign data remains in the context renderer.
- `llm_world_context_renderer.py` — renders the complete legacy snapshot or a typed selected projection; includes resource balances.
- `llm_world_proposal_prompt_builder.py` — player-intent proposal prompt.
- `llm_world_proposal_validator.py` — proposal validation, response-size enforcement and one compact budgeted repair.
- `llm_world_response_parser.py` — provider-response decoding and LLM-specific operation trust checks.
- `operation_registry.py` — immutable typed catalog of parser-supported operations, explicit model-proposable/internal trust classification, dataclass-derived JSON Schemas, field descriptions and examples.
- `operation_parser.py` — canonical structural parser driven by the operation registry; domain existence and permission checks remain in `WorldService` / `WorldApplier`.
- `llm_extraction_errors.py` — package error type.

## Dependency rules
- Depend on the provider callable/port supplied by the composition root, not a concrete provider.
- Never write directly to SQLite or bypass typed operation validation.
- Keep prompt construction, parsing, validation and provider invocation distinct.
- Treat model output as untrusted input and fail closed on malformed/unsupported operations.
- Keep world mutation in the world application boundary.

## Active structured proposal pipeline

The durable/native path no longer sends the full campaign world to the proposal model by default.

1. `TurnResolutionService` asks the injected `ContextBuilder` for a typed `WorldContextProjection`.
2. `ContextBuilder` delegates to `ProposalContextSelector`, which reuses deterministic memory search, one-hop graph expansion and the existing context ranker.
3. The selector preserves the active character and current campaign location as mandatory entities, renders campaign/session summaries and active conditions, filters secret events through existing search/export rules, and admits related records with their required entity/item/resource dependencies.
4. The projection contains deep-copied domain records, not references to the mutable runtime world.
5. `LLMWorldProposalPromptBuilder` renders the selected records, active-character sheet, resource balances, the compact registry-generated operation contract (field types, required/optional fields, field notes and representative examples) and confirmed mechanics.
6. `LLMWorldResponseParser` rejects operation types not explicitly classified as model-proposable before the structural parser constructs domain objects.
7. The completed structured proposal prompt is checked against its total estimated-token budget before provider invocation.

`services/llm_world` depends only on shared model contracts and never imports `services.context`. The application/turn boundary owns context retrieval and passes the typed projection inward.

## Budgets and configuration

| Environment variable | Default | Meaning |
|---|---:|---|
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_PROMPT_MAX_TOKENS` | 8192 | Upper bound for the complete structured proposal prompt |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_CONTEXT_MAX_TOKENS` | 4096 | Budget for selected world records |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_MAX_RESPONSE_CHARS` | 16000 | Maximum provider response size for extraction/proposal responses |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_REPAIR_MAX_TOKENS` | 2048 | Independent maximum for the one repair request |
| `CAMPAIGN_MANAGER_LLM_LEGACY_EXTRACTION_PROMPT_MAX_TOKENS` | 65536 | Upper bound for the complete legacy narrative-extraction prompt |
| `CAMPAIGN_MANAGER_LLM_LEGACY_EXTRACTION_CONTEXT_MAX_TOKENS` | 8192 | Budget for selected public world records in legacy extraction |

The current provider contract does not expose a model tokenizer. `estimate_tokens()` therefore uses one token per UTF-8 byte as a deliberately pessimistic upper bound. This is not an exact count of Gemma/Qwen tokens, but it prevents a short character-based estimate from silently accepting an oversized request. The complete rendered prompt is checked separately from the structured-record budget.

The selector reports available, candidate, selected and excluded record counts and the projection's estimated budget use. The extractor logs prompt characters, estimated size, budget utilization and selection counts at debug level. Campaign text is never included in these diagnostic fields.

## Legacy narrative extraction compatibility

The legacy `extract()` path now has its own bounded-context and complete-prompt safeguards, separate from the active structured proposal budget:

- The composition root injects `ContextBuilder.build_relevant_world_projection()` into `LLMWorldExtractor`; the LLM package depends only on the callback contract and shared projection model, not on `services.context`.
- The selector searches from the narrative being extracted, expands dependencies, ranks candidates deterministically and preserves the active character/current location as mandatory entities.
- Secret events are excluded by the existing public memory export/search path. Records are copied into a detached `WorldContextProjection`; the source `WorldState` is not mutated.
- `LLMWorldPromptBuilder.build_prompt()` accepts an optional projection and renders the selected world records. Calls that do not inject a selector retain the old full-context builder behavior, but still pass through the total prompt cap.
- The complete rendered prompt is checked with `estimate_tokens()` before provider invocation. If context selection fails or the assembled prompt exceeds the legacy budget, extraction fails closed; it does not call the provider or truncate individual facts.
- The legacy static instructions and assembly order remain unchanged, so the byte-for-byte prompt compatibility fixture still applies. This bounds dynamic campaign context, not the size or quality of the static instructions themselves.

Defaults are a 65,536 estimated-token upper bound for the complete legacy prompt and 8,192 for selected world records. These are independent from the structured proposal limits (8,192 / 4,096). The estimator is one UTF-8 byte per estimated token, a conservative upper bound rather than the selected model's exact tokenizer. Both budgets are configurable at startup.

The compatibility path remains used by the narrative-first branch in `TurnResolutionService` and deprecated SillyTavern mutation workflow. Representative large-campaign tests protect deterministic selection and fail-closed behavior. The static instruction set is still long (the existing representative prompt is about 46,851 characters); shortening it or changing its wording remains a separate quality task that requires live Ollama probes. Never truncate arbitrary world facts or silently fall back to an unbounded snapshot.

## Response and repair safety

- The first model response is capped before parsing.
- Invalid proposals receive at most one repair request.
- Repair does not repeat the full original prompt or world snapshot.
- The repair request contains a bounded validation error, the public model-proposable operation list and a byte-bounded excerpt of the invalid output.
- The repair request has its own upper-bound budget and is rejected if its safety header cannot fit.
- Character-state operations remain excluded from the model-proposable allowlist; deterministic mechanics/application code remains authoritative. The current domain has no separate permission object, so do not claim prompt filtering substitutes for a future explicit GM/player permission contract.

## Remaining work

- [x] Centralize operation metadata: one immutable registry drives parser builders/reference fields, prompt operation contract and the inbound model-proposal trust gate. Runtime semantic validation and permissions remain owned by the world application layer.
- [ ] Add intent-specific operation subsets only when the application can classify intent reliably without hiding legitimate consequences; do not infer authorization from a prompt.
- [ ] Add tokenizer-aware accounting if a selected provider exposes an explicit, reliable token-count API; keep the byte upper bound as a safe fallback.
- [ ] Add representative large-campaign quality probes with real Ollama models; deterministic CI remains provider-independent.
- [x] Bound legacy `extract()` context and total prompt before provider invocation (PR #197); verify with deterministic selector/budget tests.
- [ ] Measure the static legacy prompt against real Ollama models and simplify its instructions only when the quality probes show equivalent or better extraction.
- [x] Map the remaining `extract()` consumers and separate legacy extraction tests from player-intent proposal tests (PR #193).
- [x] Decompose the legacy narrative prompt into cohesive instruction sections behind the unchanged `LLMWorldPromptBuilder.build_prompt()` façade; PR #194 adds a byte-for-byte regression fixture for the complete rendered prompt.

## Migration status
All implementation modules live in `services/llm_world/`. PR #161 separated `LLMWorldProposalPromptBuilder` from the legacy narrative prompt: it now renders from `LLMWorldContextRenderer` directly. The legacy `LLMWorldPromptBuilder` remains for the narrative-first `extract()` compatibility path; production consumers are the legacy branch in `TurnResolutionService` and `LegacySillyTavernTurnService`. The active durable player-intent path uses `propose()` and `LLMWorldProposalPromptBuilder`. Regression tests are separated into `test_llm_world_legacy_extraction.py` and `test_llm_world_proposals.py` (PR #193). The active structured proposal path now uses a typed relevant projection and independent prompt/response/repair budgets. The legacy builder still renders its complete snapshot for compatibility callers; its static instructions are now split under `legacy_prompt_sections/` and concatenated in their original order. PR #194 preserves the complete rendered output byte-for-byte for a fixed representative fixture. Dynamic world context remains in `LLMWorldContextRenderer`; do not confuse that path with the durable proposal pipeline. The former flat `services.llm_extraction_errors` and `services.llm_world_*` compatibility modules have been removed. Import from this canonical package.
