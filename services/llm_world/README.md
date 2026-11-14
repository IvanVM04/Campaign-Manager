# LLM world-processing services

## Responsibility

Turn the shared player-intent interpretation and confirmed mechanics into
bounded, typed proposals for world operations from the validated shared
`PlayerIntentAnalysis`. The planner does not independently re-interpret the
player's utterance or decide mechanical outcomes. Model output is untrusted: it
is parsed and classified here, then semantically validated and applied by the
world application boundary.

## Modules

- `llm_world_extractor.py` — coordinates the single structured `propose()` workflow and provider call.
- `llm_world_proposal_prompt_builder.py` — builds the proposal prompt from typed world context, the shared intent analysis and trusted resolved references.
- `llm_world_proposal_validator.py` — validates response size and performs at most one compact, separately budgeted repair.
- `llm_world_response_parser.py` — decodes provider output and applies the model-proposable operation trust gate.
- `operation_registry.py` — immutable typed catalogue of parser-supported operations, model-proposable/internal trust classification and generated JSON schemas.
- `operation_parser.py` — structural parser; existence, campaign scope, permission and mutation checks remain in `WorldService` / `WorldApplier`.

## Active proposal pipeline

1. `TurnResolutionService` receives the player's original intent and the shared v1/v2 `PlayerIntentAnalysis`.
2. It builds a bounded `WorldContextProjection`, preserving the active character, current location, dependencies and additional signals from literal mentions, v2 action arguments and relation endpoints.
3. `LLMWorldProposalPromptBuilder` renders the projection, character sheet, resource balances, confirmed mechanics, shared semantic analysis and registry-generated operation contract. A shared trust contract is composed with proposal-specific policy; schema structure is enforced by the parser/structured response contract.
4. The extractor checks the complete prompt against its budget before calling the provider.
5. The response parser rejects internal-only/unsupported operation types before structural parsing.
6. The world application boundary performs semantic validation and applies operations inside the caller-owned transaction.
7. Narration happens after consequence commit.

## Shared semantic input

V1 and v2 analysis are supported. V2 action frames distinguish predicate and
semantic roles (agent, patient/theme, recipient, source, destination,
instrument, location/path, owner/holder/container, etc.). Typed object hints
distinguish item definitions from physical instances. Relation claims preserve
directed subject/predicate/object, polarity, modality, attribution and temporal
evidence.

These fields help the proposal model understand what the utterance describes;
they are not IDs, confirmed facts or authorization. Do not promote a negative,
hypothetical, questioned, quoted or merely reported relation into a positive
canonical edge. Do not infer ownership, kinship, allegiance or location from
proximity or a conversation. Existing operation/domain validation remains
authoritative.

The extractor does not call `services/context`; the application layer selects
a bounded projection and passes it inward.

## Budgets

| Environment variable | Default | Meaning |
|---|---:|---|
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_PROMPT_MAX_BYTES` | 8192 | Complete proposal prompt upper bound in UTF-8 bytes |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_CONTEXT_MAX_BYTES` | 4096 | Selected world-record budget in UTF-8 bytes |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_MAX_RESPONSE_CHARS` | 16000 | Maximum provider response size |
| `CAMPAIGN_MANAGER_LLM_EXTRACTION_REPAIR_MAX_BYTES` | 2048 | Independent UTF-8 byte budget for the single repair request |

The prior `*_MAX_TOKENS` names remain accepted as compatibility aliases, but
their values have always been interpreted as UTF-8 byte ceilings by the
conservative estimator. They are not exact model-token counts. Prompt,
response and repair remain independently bounded. Context selection fails
closed rather than arbitrarily truncating mandatory campaign facts.

## Dependency and safety rules

- Depend on the provider port supplied by the composition root, not a concrete provider.
- Never write directly to SQLite or bypass typed operation validation.
- Keep prompt construction, parsing, validation and provider invocation distinct.
- Treat model output as untrusted input.
- Character-state operations remain excluded from the model-proposable allowlist.
- Keep world mutation in the world application boundary.
- Do not reintroduce a narrative-first extractor or an independent prompt contract.
