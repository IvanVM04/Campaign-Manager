# Semantic-understanding next phase — delivery status and remaining roadmap

**Status (2026-11-14):** PRs #219–#223 are merged into `main`. PR #223 adds bounded discourse understanding. The remaining P0 work is live evaluation, prompt-budget verification and SillyTavern acceptance; see the [independent audit](language-understanding-audit-2026-11-14.md).
**Priority:** P0 closeout — live semantic evaluation, discourse hold-out and SillyTavern acceptance.  
**Baseline:** `main` after PR #223, `7f4f8b10a072665471370fab4493a338835b875c` (2026-11-14).
**Implementation history:** PR #222 (typed world references) and PR #223 (advanced discourse) are integrated; no active implementation branch is implied.

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

### PR #220 — evaluation corpus and quality gate (merged into main)

- Adds 60 held-out scenarios to the 50 existing development cases: 26 utterance/intent, 20 semantic-frame/relation and 14 conversation-reference cases (110 distinct cases total).
- Covers action roles, item definition versus physical instance, transfer, directed relations, polarity/modality, attribution, correction, temporal expressions, compound actions, ambiguity, visibility, narrator/player evidence and negative controls.
- Keeps all hold-out examples in distinct fixture files marked `held_out`; they are not copied into prompts or schema examples.
- Adds a provider-agnostic metrics ledger for per-family case accuracy/slot recall/latency, entity-link precision/recall/abstention, context recall, operation precision/recall, false persistent changes and secret leaks.
- Adds deterministic corpus-integrity and discourse tests, live opt-in Ollama tests for the held-out language/frame cases, and positive/negative operation-quality controls.
- Requires zero critical false persistent changes and zero secret leaks. Per-family quality targets for non-critical cases are set only after the first reproducible baseline; never collapse results into a misleading aggregate score.
- Detailed protocol: [semantic evaluation corpus](semantic-understanding-evaluation-corpus-2026-11-13.md).

### PR #221 — evidence-bound correction lifecycle (merged)

- Adds a correction-only extension of the combined provider schema. The normal turn schema and normal provider-call count stay unchanged.
- Supplies the prior pending analysis and the latest player clarification as separate prompt evidence; the DM's question remains context, never correction evidence.
- Parses at most four typed corrections with target, role-labelled argument and directed relation endpoint slots. Replacements and excerpts must be literal in the latest answer.
- Applies each edit to an immutable copy of the stored analysis only while its durable resolution is pending and uncommitted. The model's full re-analysis must reflect the exact same edit; otherwise the clarification fails closed.
- Preserves the original request, cumulative player evidence, existing lease/revision checks, and a bounded durable correction audit across multi-round clarifications.
- Releases the planning lease back to `awaiting_input` if correction validation fails, allowing a safe retry instead of leaving a stranded claim.
- Adds deterministic tests for strict decoding, ungrounded/extra fields, no-op or mismatched edits, and multi-round durable recovery. Live model/SillyTavern acceptance remains separate.
- No database migration, extra normal-path provider call, embedding or vector store is added.
- The merged implementation is documented in `services/turns/README.md`; the live correction-model probe remains an opt-in acceptance test.

### PR #222 — typed world-reference resolution and semantic precision (merged)

- Adds a separate typed resolver for item definitions, physical item instances, resources and visible events. Entity IDs, item-definition IDs, physical-instance IDs, resource IDs and event string IDs remain separate namespaces.
- Resolves direct typed mentions and conservative cross-turn anaphora from the same bounded six-turn evidence window. Multiple physical copies remain ambiguous; inactive instances and hidden/GM-only events are excluded.
- Keeps entity coreference on `ConversationReferenceResolver`; typed object mentions are deliberately skipped there and routed to `WorldReferenceResolver`.
- Passes trusted typed references to the proposal prompt as evidence, never as write authority. The prompt explicitly forbids swapping ID namespaces.
- Adds semantic argument/relation slot precision, recall and F1 using multiset matching so duplicate or unsupported output counts as a false positive.
- Adds an opt-in real-Ollama test for correcting a pending recipient from the latest player clarification.
- Live Ollama and SillyTavern acceptance remain separate gates.

### PR #223 — advanced discourse understanding (merged)

Use the expanded held-out corpus and the new typed-reference failures to prioritize broad ellipsis, topic shifts, long-distance references, grammar agreement and time-aware relation modelling. Add embedding retrieval only if held-out measurements demonstrate a material precision/recall gain over the typed deterministic baseline.

### Next after PR #223 — measure the integrated system

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


PR #223 is merged with successful deterministic CI. Its discourse index is a bounded hint, not a general parser; the 650-character cap and prompt-budget fallback can omit it. The immediate next phase is to execute the live corpus, extend held-out discourse coverage and run SillyTavern acceptance. The independent [audit](language-understanding-audit-2026-11-14.md) records risks and effort.