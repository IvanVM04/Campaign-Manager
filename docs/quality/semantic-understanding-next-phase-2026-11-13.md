# Semantic-understanding next phase — delivery status and remaining roadmap

**Status:** PR #219 is merged into `main` at `cd701d11eb36666ab5ad33603095a2d95289882b`. PR #220 is under implementation on `feat/220-semantic-evaluation-corpus`. Live Ollama and manual SillyTavern acceptance remain separate gates and are not implied by deterministic CI.  
**Priority:** P0.3 — semantic evaluation corpus and quality gate.  
**Baseline:** `main` at `cd701d11eb36666ab5ad33603095a2d95289882b` (2026-11-13).  
**Implementation branch:** `feat/220-semantic-evaluation-corpus`.

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

### PR #219 — evidence-backed discourse and pending corrections (merged in `main`)

- Replaced nearest-string antecedent selection with typed candidates, bounded evidence excerpts, player-input versus narrator source, recency, topic continuity and semantic-kind compatibility.
- Preserved visible-world and same-chat scoping; uncertain scores and narrow margins abstain with explicit reasons.
- Added an immutable, evidence-backed correction primitive for target mentions, action arguments and directed relation endpoints; it rejects stale, ambiguous, ungrounded and committed corrections.
- Kept grammar inference conservative because the canonical entity model has no reliable gender/number fields; narration is not relabelled as NPC speech without speaker metadata.
- **Remaining boundary:** the correction primitive is not emitted by the provider schema or connected to an automatic correction loop. Do not describe autonomous model-driven correction as implemented.
- Added deterministic regressions for ambiguity, source preference, kind filtering, evidence provenance, six-turn limits and correction immutability.

### PR #220 — evaluation corpus and quality gate (current implementation)

- Adds 60 held-out scenarios to the 50 existing development cases: 26 utterance/intent, 20 semantic-frame/relation and 14 conversation-reference cases (110 distinct cases total).
- Covers action roles, item definition versus physical instance, transfer, directed relations, polarity/modality, attribution, correction, temporal expressions, compound actions, ambiguity, visibility, narrator/player evidence and negative controls.
- Keeps all hold-out examples in distinct fixture files marked `held_out`; they are not copied into prompts or schema examples.
- Adds a provider-agnostic metrics ledger for per-family case accuracy/slot recall/latency, entity-link precision/recall/abstention, context recall, operation precision/recall, false persistent changes and secret leaks.
- Adds deterministic corpus-integrity and discourse tests, live opt-in Ollama tests for the held-out language/frame cases, and positive/negative operation-quality controls.
- Requires zero critical false persistent changes and zero secret leaks. Per-family quality targets for non-critical cases are set only after the first reproducible baseline; never collapse results into a misleading aggregate score.
- Detailed protocol: [semantic evaluation corpus](semantic-understanding-evaluation-corpus-2026-11-13.md).

### Next after PR #220 — close the correction loop with evidence

Once the held-out baseline is recorded, design the provider/lifecycle integration for player-issued corrections. The follow-up must represent correction intent explicitly, bind it only to an uncommitted pending resolution, preserve the original request and appended player evidence, revalidate canonical references/visibility and avoid a normal-path extra provider call unless measurements justify one. It must test correction target/role/relation endpoint, explicit rejection of already-committed correction, multi-round clarification and SillyTavern restart/replay.

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
