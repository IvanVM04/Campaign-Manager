# Semantic-understanding next phase — delivery status and remaining roadmap

**Status:** PR #218 implementation is present on `feat/218-semantic-frames-v2`; it is not yet merged or accepted.  
**Priority:** P0.1 — semantic representation and grounding.  
**Baseline:** `main` at `14070b007246d7a58243c58eadc66b9f54781472` (2026-11-13).  
**Implementation branch:** `feat/218-semantic-frames-v2`.

## 1. Why this phase exists

PRs #215/#216 established the shared typed intent, durable evidence, chat isolation and a narrow cross-turn resolver. V1 still represented the action as free text and targets as a flat list. That representation could not explicitly distinguish the transferred object from its recipient, or a directed relationship from a mere mention.

PR #218 introduces semantic frames v2 without changing the authority boundaries or adding another normal-path model call.

## 2. V2 contract implemented on the branch

### Action frames

Every v2 intent step carries an `action_frame`:

- literal predicate and bounded action-family hint;
- bounded list of typed semantic arguments;
- each argument has a role and an exact literal mention;
- each mention has an untrusted kind hint, including a distinction between item definition and item instance.

Roles include agent, patient/theme, recipient, source, destination, instrument, location/path, beneficiary/companion, experiencer, owner, holder, container, cause and result.

The example “Entrego la llave de hierro a Mara” can represent the key as theme/item instance and Mara as recipient/character. Neither role is assigned a canonical ID by the model.

### Directed relations

V2 supports bounded relation claims with step index, literal subject, predicate and object, relation-family hint, polarity, modality, source excerpt, optional attribution and temporal expression. Direction and epistemic modality remain explicit. A reported/negative/question/conditional claim is not automatically a positive confirmed relation.

### Validation and compatibility

- V1 and v2 analysis payloads are both decoded.
- V1 serializes back to its original shape; v1 durable rows are not rewritten as v2.
- V2 requires an action frame for each step and a relation-claims array.
- Literal evidence is checked for predicate, arguments, endpoints, attribution, temporal expression and source excerpt.
- Unknown fields/enums, oversized arrays, nonliteral mentions, model-supplied IDs and references to nonexistent steps fail closed.
- The durable intent codec round-trips v2 inside the existing fingerprinted JSON envelope; no migration is currently required.
- The turn service uses action-frame arguments and relation endpoints as supplemental retrieval signals.
- The proposal prompt receives the same shared analysis and is instructed to preserve roles/direction/modality without promoting evidence to authority.

### Files changed

- `models/semantic_frames.py` — semantic mention, argument, action-frame and relation-claim value objects.
- `models/player_intent_analysis.py` — v1/v2 decoder, serializer and invariants.
- `services/turns/intent_response_schema.py` — combined structured-output schema v2.
- `services/turns/mechanics_adjudicator.py` — v2 interpretation instructions and schema example.
- `services/turns/turn_resolution_service.py` — supplemental retrieval from typed frame/claim mentions.
- `services/llm_world/llm_world_proposal_prompt_builder.py` — proposal guidance for semantic roles, object kinds and relation claims.
- `tests/test_semantic_frames.py` — frame parsing, evidence grounding, relation semantics, v1 compatibility and durable recovery.
- `tests/test_mechanics_adjudicator.py` — regression for the v2 structured schema contract.

## 3. PR #218 acceptance still required

Before merge, run the full deterministic suite and all required quality checks on the final commit. Review the real diff for typing, prompt budgets, structured-generation compatibility and accidental changes to the v1 durable representation.

Then run the live Ollama corpus with a pinned model/version/settings. The existing 34 utterance scenarios validate category/step interpretation and now pass through v2 structural validation, but they do not yet constitute a comprehensive semantic-role or relation benchmark. Preserve all live failures.

The SillyTavern multi-chat/recovery smoke test also remains a separate gate. Do not infer it from unit/API tests.

## 4. Remaining PR roadmap

### PR #219 — discourse resolution and correction chains

- Replace string-only antecedent heuristics with typed, evidence-producing candidates.
- Add speaker role and turn identity, semantic-type agreement, grammatical gender/number where reliable, recency, topic continuity and explicit discourse focus.
- Support corrections to pending action/target/argument slots without rewriting committed world history.
- Keep ambiguity explicit and ask the player when multiple candidates remain plausible.
- Expand Spanish-first and English-control multi-turn sequences, including topic shifts, competing referents, ellipsis and correction loops.
- Preserve chat isolation, active-character visibility, durable clarification and manual-roll behavior.

### PR #220 — evaluation corpus and quality gate

- Expand from 34 utterance cases and six deterministic resolver cases to at least 100 labelled scenarios.
- Include action roles, item definitions versus instances, inventory transfer, directed relation types, polarity/modality, attribution, correction, temporal language, compound actions, ambiguity, secrets and negative controls.
- Keep a held-out tranche separate from prompt/schema tuning examples.
- Report per-family frame/slot accuracy, relation direction/polarity accuracy, entity-link precision/recall/abstention, context recall, operation precision/recall, false persistent changes, secret leakage and latency.
- Require zero critical false persistent changes and zero secret leakage. Set per-family accuracy targets after the baseline is measured; avoid a misleading single aggregate score.

### Later — retrieval/model selection only when measured

Test whether aliases, relation edges, dependency expansion and ranking can satisfy the expanded corpus. Consider embeddings only if a reproducible held-out evaluation demonstrates a material improvement over the deterministic baseline.

## 5. Non-negotiable acceptance rules

- Semantic mentions and relation endpoints are literal evidence, not canonical IDs.
- The model never writes world state or grants permissions.
- Application code performs canonical resolution, visibility checks and domain validation.
- Item definitions and instances remain separate.
- Direction, negation, modality, attribution and temporal evidence are preserved.
- Questions, rumours, hypotheses, quotations and negative claims are not promoted to positive canon.
- Existing v1 durable records recover unchanged.
- No extra provider call, vector store or service is added without measured justification.
