# Semantic-understanding next phase — delivery status and remaining roadmap

**Status:** PR #218 is integrated on `main` and its required CodeQL and Tests workflow runs completed successfully. Live Ollama and manual SillyTavern acceptance remain unrecorded. PR #219 is being prepared on `feat/219-discourse-resolution-corrections`.  
**Priority:** P0.2 — discourse resolution and pending corrections.  
**Baseline:** `main` at `184126110c713cff4c9bd1da96786f2c49fc5145` (2026-11-13).  
**Implementation branch:** `feat/219-discourse-resolution-corrections`.

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

## 3. PR #218 acceptance status

The merge commit is `184126110c713cff4c9bd1da96786f2c49fc5145`. Its required GitHub Actions `Tests` and `CodeQL` workflow runs both completed successfully. The live Ollama suites have not been demonstrated by those checks and remain required with pinned model/version/settings. The SillyTavern multi-chat/recovery smoke test is also a separate gate.

The 34 utterance scenarios validate category/step interpretation and v2 structural constraints; the ten-case semantic-frame corpus evaluates selected argument roles and relation direction/polarity/modality/attribution (four critical cases repeated three times). Neither is a comprehensive benchmark. Preserve all live failures.

## 4. Remaining PR roadmap

### PR #219 — evidence-backed discourse and pending corrections (current implementation)

- Replace the nearest-string antecedent heuristic with typed candidates, bounded evidence excerpts, explicit player-input versus narrator source, recency, repeat/topic continuity and semantic-kind compatibility.
- Preserve visible-world and same-chat scoping; return ranked candidate evidence and an explicit abstention reason when the score or candidate margin is insufficient.
- Add a guarded, immutable correction primitive for target mentions, action-frame argument roles and directed relation endpoints. It requires literal player-authored correction evidence and refuses non-pending or committed resolutions.
- Do not infer grammatical gender/number: the current canonical entity model has no reliable fields for these attributes. Do not label narration as NPC speech without explicit speaker metadata.
- The correction primitive is not yet emitted by the provider schema or wired as an automatic model-driven correction chain. That integration remains a separately evaluated follow-up rather than being claimed complete here.
- Add deterministic regressions for ambiguity, speaker/source preference, kind filtering, evidence provenance, six-turn limits and correction immutability.

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
