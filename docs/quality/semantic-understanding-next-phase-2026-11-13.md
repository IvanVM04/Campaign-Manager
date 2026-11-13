# Next phase — structured semantic frames and grounded world relations

**Status:** proposed; not yet implemented  
**Priority:** P0.1 — next language-understanding phase after recording the PR #215/#216 acceptance baseline  
**Baseline:** `main` at `868ae7ae29c6c1c0cfb5b3aaf181b630a0039ff6` (2026-11-13)

## Why this is the next step

PRs #215/#216 provide a shared typed interpretation, evidence validation, durable continuations, chat isolation and narrow cross-turn reference resolution. The remaining gap is the representation of meaning: `IntentStep.action` is free text, `target_mentions` is a flat list, and there are no structured semantic argument roles, relation claims, typed object mentions or correction links. Improving only the prompt cannot reliably recover information the contract has nowhere to store.

## Target contract (new schema version)

Preserve v1 decoding for existing durable records; never silently reinterpret persisted v1 data.

### 1. Action frames

Represent each step as a predicate/action family plus evidence-bound arguments. Candidate roles:

| Role | Meaning |
|---|---|
| agent | who performs the action |
| patient/theme | entity affected or moved |
| recipient | who receives something |
| source / destination | transfer or movement origin and endpoint |
| instrument | tool used |
| location / path | where the action happens or movement passes |
| beneficiary / companion | who benefits or participates |
| experiencer | who perceives or feels something |

Keep the literal surface mention and excerpt/span for every argument. These are not IDs. Application code resolves them after campaign, visibility, active-state and semantic-type checks. Missing roles stay missing; the model must not invent a recipient/object/location. Action families should be a small vocabulary mapped to existing domain capabilities, while preserving the original predicate as evidence.

### 2. Directed relation assertions

Represent a claim as subject–predicate–object, with literal endpoints, supported relation predicate, polarity, modality, attribution/source, temporal applicability and grounded excerpt.

Distinguish “Mara is Aldric's sister” (assertion), “Mara says Aldric is her brother” (attributed claim), “Are they related?” (question), “If they were related…” (hypothesis), “Mara is not his sister” (negative assertion), and “Mara used to work for the captain” (historical relation).

Derive allowed predicates from the existing relation model and operation registry. Unknown relation kinds abstain or request clarification; no free-form relation writes.

### 3. Typed object mentions

Add untrusted type hints such as character/NPC, location, item definition, item instance, event, faction, relation or unknown. Keep separate: item definition vs unique instance; owner vs holder; carried/equipped/stored; container/current location; condition; observed/discovered/used/transferred. The application remains responsible for canonical resolution and state changes.

### 4. Discourse and corrections

Resolve references using chat/turn identity, speaker/role, mention order, grammatical number/gender where reliable, semantic-type compatibility, recency/topic focus and active-character visibility. Keep ambiguity when evidence conflicts.

A correction must identify what is corrected, the replacement mention/value and whether it changes a pending intent or reports a world-knowledge correction. Never rewrite already committed history because the player later corrects their wording. Distinguish “I meant the red door, not the blue one” from “the door used to be red” and “Mara says the door is red”.

### 5. Sequence, time and causality

Preserve step dependencies and conditional boundaries. Capture before/after/while/then and because/therefore only as evidence-backed temporal/causal relations. A stated cause is not automatically proven; intended future events are not completed events.

## Delivery sequence

### Immediate prerequisite — baseline

1. Run the existing live Ollama suite with pinned model/version/settings.
2. Save per-scenario outcomes for the 34-case intent corpus and seven current real-LLM test functions.
3. Record the six-case conversation corpus as deterministic resolver coverage, not live model accuracy.
4. Complete the SillyTavern multi-chat and recovery smoke test.
5. Classify failures as intent, relation, object identity, semantic role, attribution, reference, retrieval, mechanics or narration.

### PR #217 — semantic frame v2 and typed arguments

- Review the schema against actual `Relation`, `Item`, `ItemInstance`, `Event`, location and operation models before implementation.
- Add typed action arguments and typed mention hints with literal evidence.
- Add relation assertions only for predicates supported by domain validation.
- Keep canonical ID resolution and authorization outside the model.
- Preserve v1 decoding, durable recovery and the single shared interpretation; do not add another normal-path call.
- Add deterministic schema, prompt, codec, repository, migration (only if required), integration and live corpus regressions.

### PR #218 — discourse resolution and correction chains

- Replace string-only antecedent heuristics with a typed evidence-producing resolver.
- Add semantic-type and grammatical constraints where reliable, speaker-aware turn structure and topic continuity.
- Resolve corrections to pending target/action/argument slots without rewriting committed facts.
- Expand Spanish-first and English-control multi-turn cases, with explicit ambiguity/abstention controls.
- Preserve chat isolation, visibility and durable clarification/manual-roll behavior.

### PR #219 — evaluation corpus and quality gate

- Expand from 34 intent and six resolver cases to at least 100 balanced labelled scenarios.
- Cover action roles, relation direction/polarity, object identity/transfer/ownership, attribution, corrections, temporal language, compound actions, ambiguity, secrets and negative controls.
- Keep a held-out tranche separate from prompt/schema tuning examples.
- Report per-family frame/slot accuracy, relation accuracy, entity-link precision/recall/abstention, context recall, operation precision/recall, false persistent changes, secret leakage and latency.
- Require zero critical false persistent changes and zero secret leakage. Set per-family accuracy targets after baseline measurement rather than inventing one aggregate score.

### Later — retrieval and model selection only when measured

First test whether aliases, relation edges, dependency expansion and context ranking can satisfy the expanded cases. Consider embeddings only if a reproducible held-out evaluation shows a material gain over the deterministic baseline.

## Acceptance rules

- Every argument, relation endpoint and correction target has literal evidence.
- The model never supplies canonical IDs or writes state.
- References are active, visible, campaign-scoped and semantically compatible.
- Direction, negation, attribution, conditionality and time are preserved.
- Item definitions and instances are not conflated; transfer source/recipient/ownership are correct.
- Earlier unresolved steps cannot be bypassed; reported outcomes are not authoritative mechanics.
- Ambiguity asks for clarification; v1 durable records still recover.
- Deterministic CI remains model/network independent; Ollama and SillyTavern acceptance is recorded separately.
- No provider call, vector store or service is added without measured justification.

**Recommendation:** after the baseline, make PR #217 the first implementation step: typed action arguments, object roles and evidence-bound relation assertions. This directly addresses the largest semantic gap found in the current code.
