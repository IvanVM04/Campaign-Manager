# Modular language-understanding pipeline — P0 architecture decision

**Status:** PR #225 merged at `e59bc47e85edb8efa4d02e5eb9990de0438d3486`; deterministic CI passed (1,810 passed, 16 deselected, 85.05% coverage). Live-model and SillyTavern acceptance remain separate pending gates.  
**Priority:** P0 / Priority #1 — blocks additional semantic feature work until the pipeline and prompt-budget contracts are reliable.  
**Decision date:** 2026-11-14.  
**Current implementation baseline:** PR #223 merge `7f4f8b10a072665471370fab4493a338835b875c`. PR #224 documentation baseline is merged at `ed65d62269ccf8a86f523d2224d5c33f4d5c7055`.  
**Related audit:** [Independent language-understanding audit](language-understanding-audit-2026-11-14.md).  
**Current priority register:** [P0 language-understanding implementation specification](language-understanding-priority-2026-11-13.md).

## 1. Decision

Refactor the current combined language/mechanics call into a small number of responsibility-aligned stages:

1. one coherent **Intent Interpreter** produces the authoritative, versioned `PlayerIntentAnalysis`;
2. deterministic validation and reference resolution verify that interpretation against evidence and visible canonical state;
3. a separate **Mechanics Adjudicator** is called only when an active unresolved attempt needs a mechanical decision, and returns only a `MechanicsDecision`;
4. the **World Consequence Planner** receives the same validated interpretation plus only the relevant world projection and confirmed mechanics outcome, and proposes typed operations;
5. deterministic domain validation, commit and post-commit narration remain authoritative.

The project must keep one shared semantic interpretation. It must not split action detection, role extraction, relation extraction, attribution and discourse into independent LLM calls that can contradict each other. The separation is between distinct responsibilities, not between fields of one meaning representation.

The number of provider calls is conditional, not fixed. A routine observed fact may need interpretation and a world proposal but no mechanics call. A question, negation or unexecuted hypothesis may need interpretation only. An active uncertain attempt may additionally need mechanics adjudication. A planner call is made only where a persistent consequence is justified and ready to be proposed.

## 2. Why this is Priority #1

The current `MechanicsAdjudicator.understand()` combines two independent jobs in one structured response: semantic interpretation and mechanics adjudication. Its prompt includes the large semantic v2 contract, discourse rules, D&D decision policy, character data and context. The shared intent is then passed to `LLMWorldExtractor`, so the extraction stage is already downstream of a reusable typed analysis, but the initial interpretation and mechanics decision remain coupled.

A real Ollama run on 2026-11-14 exposed a concrete pre-provider failure. The focused known-NPC test failed in `MechanicsAdjudicator._understand()` with:

```text
MechanicsAdjudicatorError:
mechanics prompt exceeds the configured estimated token budget
```

The failure occurs before `generate_structured()`; it is not evidence of a Gemma semantic error. In the inspected source, the mechanics system prompt is approximately 7,250 UTF-8 bytes while the default configured prompt cap is 8,192. The shared `estimate_tokens()` function actually counts UTF-8 bytes, so that cap is a conservative byte ceiling, not a model-token count. The remaining prompt framing, evidence and context can exceed it even for a short utterance.

The first full run also emitted `llm.provider.failed` for some other cases. Their underlying provider exceptions have not yet been classified and must remain a separate open diagnostic item; this architecture change must not label them all as budget failures.

The immediate goal is therefore not simply to raise the cap. It is to make responsibilities, context, schemas and budgets explicit and independently measurable.

## 3. Target execution flow

### Stage 0 — deterministic evidence preparation

- Preserve the exact player-authored input and durable turn/chat identity.
- Select bounded same-chat history and visible world facts.
- Keep player text, narrator text, NPC dialogue, canonical world facts and mechanics outcomes distinguishable.
- Prepare compact role-specific context slices; do not render the full campaign state into every prompt.
- Record selection and compaction diagnostics without logging prompts, secrets or raw campaign text.

### Stage 1 — Intent Interpreter (one coherent semantic call)

Input:
- exact current player evidence;
- bounded relevant same-chat discourse/history evidence;
- compact visible context needed to resolve references and perspective;
- shared safety rules and the v2 interpretation schema.

Output:
- one `PlayerIntentAnalysis` v2 containing ordered steps, actor, modality, polarity, reported outcome, action frames, role-labelled arguments, relation claims, attribution, active step and clarification state.

Responsibilities:
- understand the utterance as a whole;
- preserve action order, dependencies, discourse callbacks and ambiguity;
- distinguish player intent from NPC/narrator speech and quoted instructions;
- identify literal evidence and semantic roles without assigning canonical IDs or confirming world facts.

Do not create separate normal-path calls for action extraction, relation extraction, argument roles, dialogue attribution or ellipsis. They are mutually dependent parts of one interpretation and must remain one coherent output.

### Stage 2 — deterministic semantic validation and reference resolution

- Validate schema, literal excerpts, evidence provenance, step indices, limits and v1/v2 compatibility.
- Resolve mentions only through existing typed resolvers and visible canonical records.
- Abstain or ask for clarification when identity or role cannot be safely resolved.
- Do not treat the model's kind hints, relation claims or action frames as permissions or facts.

This stage makes no LLM call.

### Stage 3 — Mechanics Adjudicator (conditional mechanics call)

Call only when an active positive attempt remains unresolved and a mechanics decision is needed. Skip it for questions, plans, hypotheses, dialogue, negation, passive observation, completed reports and cases with no active character where no check can be applied.

Input:
- the validated active step and only the action-frame arguments relevant to adjudication;
- the relevant visible obstacle/state facts;
- the active character's required mechanical statistics/proficiencies;
- a mechanics-specific policy and a mechanics-only response schema.

Output:
- `MechanicsDecision` only (`none`, `clarification`, check or saving throw as supported).

The adjudicator must not reconstruct the full conversation, re-extract intent, emit action frames or rewrite relation claims. Deterministic rules still calculate and apply rolls and outcomes.

### Stage 4 — World Consequence Planner (conditional proposal call)

Call only when the validated analysis and available outcomes support a possible persistent world consequence.

Input:
- the exact same validated `PlayerIntentAnalysis` object (never a second interpretation);
- trusted resolved references and a bounded `WorldContextProjection`;
- confirmed mechanics outcomes where applicable;
- the operation allowlist/schema and concise proposal-specific safety rules.

Output:
- typed world-operation proposals, or an empty list.

The planner must not reinterpret the raw utterance independently, invent successful outcomes, mutate state, issue character operations or bypass the domain layer. Failed, negated, hypothetical or unresolved steps must not be converted into success proposals. For compound actions, respect step order and do not propose later consequences before their prerequisites are confirmed.

### Stage 5 — deterministic validation, commit and narration

Existing parsers, domain services, revision/lease checks and durable transaction boundaries remain authoritative. Persist the validated intent and evidence. Generate narration only from committed results and confirmed mechanics outcomes.

## 4. Prompt and schema architecture

Use reusable composition without making every role inherit every instruction:

- **Common safety contract:** inputs/history/context are untrusted; model output is evidence/proposal only; no IDs, permissions, visibility grants, persistence or mechanical results.
- **Intent policy:** language, discourse, action structure, modality, attribution, argument roles, relation direction and literal evidence.
- **Mechanics policy:** D&D 5e adjudication, uncertainty, checks/saves, DC limits and mechanical-only output.
- **Proposal policy:** operation allowlist, typed references, evidence, identity reuse and persistence constraints.
- **Response schemas:** enforce structure and enums. Do not repeat every schema field, enum and a full JSON example in natural-language instructions when the schema already expresses that contract.

The common safety contract should be concise and shared by composition, while role-specific rules remain independently owned and tested. Avoid broad copy/paste prompt duplication; a change to one responsibility must not silently change the others.

## 5. Prompt budget and diagnostics

The existing `estimate_tokens()` counts UTF-8 bytes. Until a tokenizer matching the configured model is available, do not call this value an exact token count.

Required changes:
- distinguish estimated UTF-8 prompt bytes from provider-reported `prompt_eval_count` / actual token usage;
- give each role explicit limits for fixed instructions, current evidence, history/discourse, world context and output schema;
- protect mandatory player evidence and required mechanical facts from silent truncation;
- compact or omit only ranked optional context, with a recorded reason;
- fail with a diagnostic that identifies the role and section sizes, not only a generic budget error;
- record total bytes, per-section bytes, selected/omitted context counts, model/digest, duration, retries and provider error type;
- never log the complete prompt, raw response, secrets or full campaign data.

A larger cap may be a configuration adjustment after the prompt is decomposed and measured. It is not the architectural fix by itself.

## 6. Compatibility and migration strategy

- Preserve `PlayerIntentAnalysis` v2 and existing v1 durable decoding/serialization behavior.
- Preserve pending clarification/correction semantics, exact evidence, correction audit and committed-resolution restrictions.
- Reuse existing deterministic resolvers, `WorldContextProjection`, operation parser and world application trust boundary.
- Prefer role-specific schemas and provider contracts over making a second component parse fields it does not own.
- Migrate callers behind narrow interfaces. If a temporary compatibility facade is required for `MechanicsAdjudicator.understand()`, it must be explicitly transitional and must not secretly retain the monolithic prompt.
- Do not add a database migration, embedding/vector service, multi-agent framework or new provider retry policy unless an independently demonstrated need requires it.

## 7. Acceptance criteria

### Architecture and call routing
- One authoritative `PlayerIntentAnalysis` is created per interpretation and reused unchanged by mechanics and proposal stages.
- Action, relation, discourse, attribution and argument roles are emitted coherently by the one Intent Interpreter call.
- Mechanics receives only the active unresolved step and relevant mechanical context; it returns only `MechanicsDecision`.
- Questions, plans, hypotheses, dialogue, negations and already-completed observations do not trigger an unnecessary mechanics call.
- Proposal generation is skipped when no persistent consequence is justified or when an unresolved mechanical prerequisite prevents it.
- Unit tests assert exact provider-call counts and the payload passed to every stage.

### Correctness and safety
- Existing v1/v2 durable compatibility and correction lifecycle remain green.
- The same analysis object (or immutable equivalent with identical fingerprint) is handed to downstream stages.
- No extra false persistent changes, false successes, identity errors, relation reversals or cross-chat history leaks.
- Existing deterministic trust/domain validation remains the final authority.

### Prompt quality and operation
- The Aldric known-NPC prompt-budget regression reaches the provider under the configured supported budget rather than failing in local preflight.
- Every role has a measured, documented section budget and a useful over-budget diagnostic.
- Evidence required by the active stage is never silently clipped to make the prompt fit.
- Live tests record per-family outcomes, model/digest, Ollama version, settings, prompt bytes, actual token usage when available, latency and classified provider failures.
- Compare the current combined baseline and the refactored pipeline on the same fixtures/model/settings; preserve all failures and report both semantic quality and latency/call count.

### Integration gates
- Deterministic Python/coverage, JS, lint, typing and CodeQL remain green.
- The opt-in Ollama suites pass the agreed critical positive/negative controls and the labelled corpora; no semantic acceptance is inferred from deterministic CI.
- Manual SillyTavern multi-chat, clarification, retry/restart and durable replay acceptance remains a separate required gate.

## 8. Implementation order

1. Add focused tests that characterize current behavior, provider-call counts, budget failure and prompt sections.
2. Introduce the Intent Interpreter interface and dedicated intent-only response schema; migrate the current combined prompt responsibilities without changing the v2 analysis contract.
3. Extract a mechanics-only adjudicator interface, response schema and compact mechanics context.
4. Update `TurnResolutionService` to orchestrate the conditional stages and preserve one interpretation across clarification/manual-roll/durable paths.
5. Adapt the proposal planner to consume validated analysis and confirmed outcomes, and measure its compact role-specific prompt.
6. Add safe per-stage budget/latency/call diagnostics and provider error classification.
7. Run deterministic regressions, then the full local Ollama baseline and SillyTavern acceptance.

**Do not resume broader semantic feature PRs until this P0 architecture tranche is implemented and its deterministic contracts pass.** The baseline live suite follows immediately after that tranche; the focused Aldric budget failure must no longer block the provider call.


## 9. Implementation status — PR #225 (merged)

The first implementation pass on `feat/225-modular-language-understanding-pipeline` currently includes:

- [x] Dedicated `IntentInterpreter` with one coherent v2 analysis response; its own exception/result types and a correction-only response contract.
- [x] Dedicated mechanics-only `MechanicsAdjudicator.adjudicate_analysis()` that accepts a validated `PlayerIntentAnalysis` and returns `MechanicsDecision` only.
- [x] Shared common trust contract composed into intent, mechanics and proposal prompts, with role-specific instructions retained separately.
- [x] Production composition root creates distinct intent and mechanics providers; `TurnResolutionService` uses the interpreter first and conditionally adjudicates only a positive active attempt with no pending semantic clarification and an active character.
- [x] The same analysis object is passed to `LLMWorldExtractor`; the proposal prompt is now consequence-planning focused and no longer owns the full semantic interpretation policy.
- [x] Pending clarification/correction flow uses the new interpreter result without requiring a mechanics decision, then optionally adjudicates the corrected active step.
- [x] Role-specific intent/mechanics/extraction prompt and context byte budgets; legacy `*_MAX_TOKENS` configuration names remain supported as byte aliases.
- [x] UTF-8 byte diagnostics for intent, mechanics and proposal context/prompt, plus safe role/model/duration/error metadata. No prompt or full model output is logged.
- [x] Deterministic tests added for schema separation, exact provider-call routing, shared-analysis hand-off, pending corrections, byte budgets and API error classification; live intent corpus moved to the dedicated interpreter and a mechanics-only live probe added.
- [x] GitHub deterministic tests, coverage, lint, type checks and CodeQL passed on the final PR #225 head (`eecad52fb8b2fd79d3b11750795eaa8e6e91e8f9`): 1,810 passed, 16 deselected, 85.05% coverage; lint, both Pyright jobs, JavaScript and CodeQL passed.
- [ ] Full local Ollama corpus and operation-quality runs must be executed with the pinned model/configuration; adding the test code does not constitute a live pass.
- [ ] Manual SillyTavern multi-chat, clarification and durable recovery acceptance remains open.

**Compatibility note:** the old combined `MechanicsAdjudicator.understand()` API remains temporarily for external/legacy callers and historical unit tests. Production runtime composition injects the dedicated interpreter and does not use that combined path. It should be retired only after callers and durable fixtures have migrated.

**Byte-budget configuration:**

- `CAMPAIGN_MANAGER_LLM_INTENT_PROMPT_MAX_BYTES` / `...INTENT_CONTEXT_MAX_BYTES`
- `CAMPAIGN_MANAGER_LLM_MECHANICS_PROMPT_MAX_BYTES` / `...MECHANICS_CONTEXT_MAX_BYTES`
- `CAMPAIGN_MANAGER_LLM_EXTRACTION_PROMPT_MAX_BYTES` / `...EXTRACTION_CONTEXT_MAX_BYTES` / `...EXTRACTION_REPAIR_MAX_BYTES`

The old extraction/mechanics `*_MAX_TOKENS` environment names are accepted as compatibility aliases. They are interpreted as UTF-8 byte budgets, not model-token counts.


## 10. Follow-up hardening — PR #226

PR #225 establishes the modular production architecture and has passed deterministic CI. PR #226 continues with context hardening and integrated validation rather than adding more semantic feature breadth.

The first identified improvement is mechanics context retrieval: canonical names from deterministic references resolved for the active step should be supplemental retrieval signals, so pronouns/ellipsis can still retrieve the obstacle/item details needed for adjudication. This work is tracked with explicit packages and a durable continuation checkpoint in [PR #226 integrated pipeline hardening](pr-226-integrated-llm-pipeline-hardening.md).

PR #226 must separately demonstrate:
- integrated Intent → resolution → Mechanics → Planner routing with one shared analysis;
- no false persistent changes for critical negative controls;
- mechanics retrieval using only active-step canonical references;
- planner prompts that prioritize shared analysis without duplicating untrusted discourse;
- live Ollama results and telemetry on a pinned model;
- migration of remaining callers from the legacy combined adjudicator.

Deterministic CI, live Ollama and SillyTavern acceptance remain distinct gates.
