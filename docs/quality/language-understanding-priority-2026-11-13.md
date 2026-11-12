# P0 — Shared natural-language understanding and intent resolution

**Priority:** P0 — highest active product/engineering priority  
**Status:** implementation specification; production implementation is the next large PR  
**Date:** 2026-11-13  
**Verified baseline:** main at 746f40b4e715741a43e5a0a19ae069236c19b7d1, after PR #214  
**Primary model for acceptance:** the configured local Ollama model (currently documented as gemma4:26b); exact tag and Ollama version must be recorded per run.

## Decision

Shared understanding of player language is the next blocking priority. Do not begin the Character Builder, class progression, broad combat expansion or the first-adventure implementation until this work reaches its acceptance gate.

The turn architecture is sufficiently modular for the current local, single-player scope. The unresolved risk is semantic, not structural: the application has strong controls over what an AI proposal may change, but it has not yet demonstrated repeatable understanding of what the player actually said.

This work must not become another prompt-only cleanup. It introduces a shared, typed, untrusted interpretation of the player's utterance and makes mechanics adjudication, world proposals, reference resolution and clarification consume the same interpretation.

## 1. Verified current state

The active pipeline is currently:

1. Preserve and validate the incoming player text.
2. Ask MechanicsAdjudicator to propose a mechanics decision.
3. Build a bounded, visibility-filtered WorldContextProjection.
4. Ask LLMWorldExtractor to propose typed world operations from the raw player text and projection.
5. Parse and validate the proposed operations.
6. Apply them through WorldService and deterministic domain rules.
7. Narrate after commit through DMService, using committed operation evidence.

The existing design already protects important invariants:

- The model does not write to persistence or apply operations.
- The rules engine computes authoritative dice results and character mechanics.
- The world application layer validates campaign scope, references and domain invariants.
- Event provenance and character visibility are enforced through the read/proposal/narration paths (PR #214).
- Durable turns protect idempotency, campaign revisions, leases, clarification/manual-roll continuation and post-commit narration recovery.
- Entity resolution has canonical-name, explicit-alias and evidence-backed lexical description matching, with ambiguity abstention.

The gaps that remain are different:

- MechanicsAdjudicator and LLMWorldExtractor receive the same raw utterance and independently infer its meaning. There is no common typed semantic result between them.
- Much of the meaning contract exists as prompt instructions rather than a validated domain object.
- The deterministic EntityReferenceResolver is lexical. It does not provide general cross-turn pronoun/ellipsis resolution, arbitrary paraphrase understanding or a complete player-correction contract.
- The current live Ollama corpus is useful but small. Normal CI tests prompt construction, parsing and application invariants; it does not prove that the configured model consistently understands natural language.
- The full manual SillyTavern acceptance checklist has not been recorded as passed.

Do not describe the system as having a general natural-language parser today. It has an LLM-assisted two-stage turn flow with deterministic retrieval and application safeguards.

## 2. Desired result

Introduce one canonical, typed interpretation for each player turn. It is an evidence-preserving representation of the utterance, not a source of truth and not an authorization object.

The desired lifecycle is:

1. Keep the exact original player input and durable request identity.
2. Build a bounded read context using the original input, active character perspective and a bounded relevant conversation window.
3. Run one structured understanding/adjudication call that returns both the semantic interpretation and (when applicable) a proposed mechanics decision.
4. Parse the response into strict typed models. Reject malformed, incomplete, contradictory or out-of-budget results.
5. Resolve literal target mentions against canonical world entities and recent conversation using deterministic application logic. The model must not select or invent canonical entity IDs.
6. If the target, actor, choice or intended step remains ambiguous, request clarification instead of guessing.
7. Execute deterministic mechanics from the selected active step and trusted character state.
8. Pass the same typed interpretation, original input, confirmed mechanics and bounded world projection to the consequence proposer.
9. Validate and apply proposals through the existing domain/application boundary.
10. Narrate only the committed result, preserving the player's meaning without introducing additional state changes.

Mechanics adjudication and consequence proposal remain separate responsibilities. They must consume the same interpretation rather than reconstructing meaning independently.

## 3. Proposed typed contract

Add a versioned domain representation, provisionally named PlayerIntentAnalysis, under models. Exact class and enum names may be refined during implementation, but the contract must cover:

### Utterance-level fields

- Schema version.
- Overall speech-act category: action, question, dialogue, report, plan, correction, mixed or unknown.
- Ordered intent steps.
- The active step, if one can be identified safely.
- Whether clarification is required and a concise proposed question.
- A bounded list of literal target/reference mentions.

### Per-step fields

Each step should contain:

- Stable order/index and the source text span or exact excerpt that supports it.
- Actor category: player, NPC, other or unknown.
- Action description in plain text; it is descriptive, not a domain operation.
- Modality: attempted, completed, observed, planned, conditional, question, dialogue, reported, negated, correction or unknown.
- Polarity/attribution sufficient to distinguish the player's own action from quoted or reported speech.
- Player-reported outcome: success, failure, partial, not claimed or uncertain.
- Literal target mentions, not canonical IDs.
- Any explicitly attributed claim needed to preserve who said or observed something.

No confidence score is required in v1. A confidence number without calibration would create false precision.

### Trust restrictions

The interpretation is untrusted model output:

- It cannot contain authoritative entity IDs, campaign IDs, provenance grants, visibility grants, roll results, DCs as authoritative facts, HP changes or operation payloads.
- It cannot mark an NPC statement or quoted claim as confirmed campaign truth.
- A reported success/failure is a claim about what the utterance says; it is not proof that a rules-governed action succeeded or failed.
- Literal references are resolved by EntityReferenceResolver and trusted conversation state. Ambiguous results remain ambiguous.
- The output is strictly schema-validated, size-bounded and versioned. Unknown enum values fail closed.
- Original player text remains available for audit and repair; interpretation must not silently rewrite or discard it.

The implementation must include examples and tests for mixed utterances such as: one confirmed observation followed by a failed attempt, a question containing an imperative quote, and a correction that changes the target of an earlier ambiguous reference.

## 4. Model-call and responsibility design

Do not add a third model call by default.

The initial implementation should evaluate a unified structured understanding/adjudication response. It should return two separately validated sections:

- intent_analysis — the shared semantic interpretation;
- mechanics_decision — the proposed check/clarification/none decision for the active step.

This replaces the current independent mechanics-only interpretation call on ordinary turns. The consequence proposal remains a separate call and consumes the shared interpretation as an explicit input. When no active character exists, the same understanding boundary must still produce semantic interpretation; mechanics must be none and must never invent a character.

This design is preferred because it shares meaning without automatically increasing the normal active-character path from two model calls to three. Measure output size, reliability and latency. If the combined response materially harms either semantic quality or mechanics quality, document the measured trade-off before introducing another provider call.

Keep deterministic rules authoritative. The model may propose a check, skill, ability, DC and clarification within the existing validated contract; only the rules engine rolls, computes modifiers and decides the actual result.

The consequence proposer must be instructed to use the provided interpretation as its semantic input. It may reject unsupported consequences, but must not independently reinterpret a quoted command, negated step, conditional plan or failed attempt as an executed action.

## 5. Conversation and reference resolution

Add a bounded conversation-state contract for references such as “él”, “ella”, “esa puerta”, “el otro guardia”, “vuelve a preguntarle” and player corrections.

Requirements:

- Include only a bounded recent window, with speaker/role and stable turn order.
- Keep chat/external-turn identity and campaign scope explicit; never mix separate SillyTavern chats.
- Resolve references only against entities and facts visible to the active character.
- Use canonical names and explicit aliases first; use deterministic descriptive evidence where available.
- Use the shared interpretation to identify which literal mentions need resolution, not to accept model-selected entity IDs.
- Ask a clarification when multiple referents remain plausible.
- Treat a correction as a new interpretation of the current pending request, preserving the original input and clarification history.
- Do not claim arbitrary semantic paraphrase support without a labelled evaluation case proving it.
- Do not add embeddings, vector storage or a semantic-search provider in this PR unless measurements show that lexical resolution is the remaining blocker and an isolated experiment demonstrates a meaningful gain.

## 6. Durable turn lifecycle

The interpretation must survive retries and the existing durable lifecycle.

Inspect the current turn_resolutions envelope before changing schema. The current adjudication_json stores challenge state (clarifications/manual rolls), so do not overload it with the semantic record.

The expected direction is a dedicated, versioned intent_json field on TurnResolutionRecord/turn_resolutions, introduced with forward-only migration 033 if implementation confirms the need:

- Persist the validated interpretation used to prepare the proposal.
- Store a schema version and a fingerprint binding it to the original player input.
- Preserve it through awaiting-input, prepared, committed and narration-pending states.
- On clarification, append the answer to the same durable resolution and re-run interpretation for the complete original input plus clarification history; persist the new interpretation before preparing operations.
- On manual-roll submission, reuse the stored interpretation and decision. Do not ask the model to reinterpret the action merely because dice were supplied.
- On recovery, reconstruct the typed interpretation through the codec with strict validation and backward-compatible handling for old records that have no intent_json.
- Never re-run or reapply committed consequences when narration is retried or regenerated.
- Keep provider calls outside write transactions and preserve revision/lease fencing.

If code inspection shows that a dedicated column is unnecessary and a versioned existing field can safely own this data without mixing challenge state, document the reason. Do not add a migration as ceremony; choose one unambiguous persistence owner.

## 7. Test and evaluation programme

### Deterministic CI

Add focused tests for:

- Typed schema validation, unknown enum rejection, missing fields, extra fields, maximum steps/mentions/text sizes and Unicode handling.
- Source-span/step ordering and mixed action decomposition.
- Negation scope, conditionals, future plans, questions, dialogue, quoted instructions and reported speech.
- Player-reported success/failure versus authoritative mechanics outcomes.
- Multiple targets, ambiguous targets, role descriptions, aliases, pronouns, ellipsis and explicit player corrections.
- Cross-turn context window bounds, speaker ordering, chat identity and active-character visibility.
- Secret/rumor/inference filtering in context and target resolution.
- The same analysis object reaching mechanics adjudication and proposal generation.
- No model-selected entity IDs, character IDs, provenance or visibility fields being accepted.
- Clarification resumption, manual-roll reuse, idempotency, leases, stale revisions, restart recovery and no double application.
- Proposal and narration contracts continuing to use typed/committed evidence.
- Provider errors, malformed analysis JSON, one bounded repair (if retained) and fail-closed behavior.

Normal CI must remain independent of Ollama, network availability and SillyTavern.

### Live model corpus

Expand the opt-in real-model corpus beyond the existing nine semantic contracts. Build at least 30 labelled scenario cases before calling this phase complete. Cover:

- Simple and compound actions with ordered steps.
- Success, failure, partial completion, interrupted and impossible attempts.
- Negation scope, conditionals, future plans and hypotheticals.
- Questions, ordinary dialogue, quoted speech and reported claims.
- Existing NPC updates versus genuinely new NPC creation.
- Direct names, role references, aliases, Spanish paraphrases and ambiguous similar entities.
- Pronouns, ellipsis, repeated references and player corrections across turns.
- Secrets, character-specific knowledge, rumors and inferences.
- Prompt injection inside names, descriptions, dialogue and quoted text.
- Unknown facts and unnamed people that must remain unknown.
- Mechanics-governed outcomes that the model must not certify.
- Malformed response and bounded repair.

For each case define expected interpretation constraints, expected mechanics behavior, allowed/forbidden operation families, required context facts and forbidden facts. Do not assert one exact JSON string or reward an always-empty proposal.

Run the critical safety subset at least three times with the same exact model tag/settings while debugging. Record every failed run, including false positives, omissions and repair behavior. Keep raw prompts, private campaign facts and full model responses out of normal logs.

### Metrics

Report separately:

- Intent-step precision/recall and step ordering.
- Modality, polarity and reported-outcome classification.
- Target resolution accuracy and ambiguity abstention.
- Context precision/recall for required/forbidden facts.
- Operation precision/recall and duplicate-entity rate.
- False persistent success rate (critical safety metric).
- Correct abstention versus incorrect empty proposals.
- Cross-turn continuity and correction success.
- Secret leakage (acceptance is zero).
- Repair rate and repair success.
- Provider call count, first-response latency and end-to-end latency distributions.

Do not collapse false positives and omissions into one score. Unsupported persistent changes are more severe than a request for clarification.

## 8. SillyTavern and end-to-end acceptance

Extend the manual checklist with cases that prove the new contract survives the real adapter lifecycle:

- A simple action and a two-step compound action.
- A player correction following an ambiguous target.
- A pronoun referring to an NPC from the immediately previous turn.
- A question or quoted instruction that must not mutate the world.
- A failed mechanical attempt that remains failed in both persisted state and narration.
- A clarification spanning more than one round and a backend/extension reload.
- Manual dice submission after restart, proving the stored interpretation is reused.
- Duplicate external-turn delivery and regeneration, proving the same consequences are not applied twice.
- A public discovery followed by recall; a secret/character-scoped fact not known by the active character must stay hidden.

Record backend SHA, extension revision, model tag, Ollama version and individual outcomes. CI success alone does not mark this gate as passed.

## 9. Acceptance gates for the P0 PR

The implementation PR is not complete until all of the following hold:

1. One validated PlayerIntentAnalysis is shared by adjudication and proposal; there is no independent re-interpretation of the same raw sentence downstream.
2. Existing active-character provider-call count is not increased by default; any exception has measured evidence and a documented reason.
3. All interpretation fields are untrusted, bounded, typed and incapable of granting IDs, visibility, provenance, mechanics outcomes or mutation authority.
4. Deterministic CI covers the contracts above, including durable clarification/manual-roll recovery and no double application.
5. Positive controls prove that valid new facts and truly new NPCs can still be recorded; negative controls prove that plans, questions, quotes, failures and negations cannot become false canonical changes.
6. No critical false persistent success and zero secret leakage in the repeated live critical corpus.
7. Ambiguous references abstain or request clarification; corrections and supported multi-turn pronouns resolve to the intended canonical entity.
8. The live report records scenario-level outcomes, model/version/settings and latency; no result is inferred from deterministic tests.
9. The SillyTavern end-to-end checklist is executed and recorded separately.
10. Ruff, Python tests with coverage threshold, JS tests, both Pyright scopes, CodeQL and documentation/architecture checks pass on the final head SHA.

Do not merge with failed, pending, cancelled or skipped required CI. Do not call the P0 phase complete while the live-model or SillyTavern acceptance is unrecorded.

## 10. Explicit non-goals

- Character Builder, race/class/background progression, spellcasting or broad gameplay expansion.
- Full D&D 5e rules implementation.
- Vector database, embeddings, Redis, message bus, microservices or multi-agent framework.
- LLM-controlled authorization or model-written canonical facts without domain validation.
- A rewrite of the durable turn lifecycle or a second parallel turn pipeline.
- Arbitrary free-form memory, unsupported confidence scores or unbounded conversation history.
- A new model call solely to make the architecture look cleaner.
- Prompt shortening as the primary success criterion.

## 11. Suggested implementation blocks inside one large PR

Keep the delivery in one coherent implementation PR, but group commits/review into these blocks:

1. Freeze the baseline corpus, model settings, current provider-call count and latency.
2. Add the typed interpretation contract, strict parser and deterministic examples.
3. Implement the shared understanding/adjudication response and connect one interpretation to mechanics and proposal.
4. Add deterministic target resolution and bounded multi-turn reference/correction context.
5. Persist/recover the interpretation through the durable lifecycle and migration 033 if required.
6. Expand live evaluation and SillyTavern acceptance documentation; record actual results rather than assumed passes.
7. Update module guides, architecture map, dependency matrix and AI roadmap.

Only merge once the entire PR is green and its non-CI acceptance results are recorded. The Character Builder becomes eligible to resume after this P0 gate, not before.
