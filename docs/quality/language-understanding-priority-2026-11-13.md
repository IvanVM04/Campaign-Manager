# P0 — Shared natural-language understanding and intent resolution

**Priority:** P0 — highest active language-quality priority  
**Integrated foundation:** PRs #215 and #216 are merged into `main`.  
**Next implementation:** PR #218 introduces the versioned semantic-frame v2 contract on `feat/218-semantic-frames-v2`; this branch is not yet merged.  
**Baseline:** `main` at `14070b007246d7a58243c58eadc66b9f54781472` (2026-11-13, after documentation PR #217).  
**Acceptance:** deterministic CI, live Ollama and real SillyTavern acceptance are distinct gates. This branch does not claim the live gates passed.

## 1. Integrated turn pipeline

1. Preserve exact player input, durable request identity, active-character perspective and SillyTavern `conversation_id`.
2. Load bounded, same-chat history and character-visible world context.
3. `MechanicsAdjudicator.understand()` returns one structured intent analysis and mechanics decision. The intended normal path remains one combined provider call; Ollama receives a native JSON Schema.
4. Validate the interpretation against player-authored evidence. DM clarification text may provide context but cannot become a player quotation, mention, relation endpoint or attribution.
5. Deterministic entity and conversation resolvers attach canonical identities only after visibility and ambiguity checks.
6. Pass the exact same analysis to `LLMWorldExtractor`; the proposal stage uses it rather than independently reconstructing player intent.
7. Parse proposed typed operations and apply them through deterministic world/domain services. Rules code remains authoritative for mechanics.
8. Persist the validated interpretation and its evidence with the durable resolution. Clarification reinterprets the original request plus player answers; manual rolls reuse the stored interpretation.
9. Narrate only committed consequences. SillyTavern history and continuation remain scoped to one chat.

## 2. Semantic contract v1 — persisted compatibility

Schema v1 stores utterance category, ordered steps, active step, clarification state and, per step, actor, free-text action, modality, polarity, player-reported outcome, literal target mentions and literal attribution.

The strict v1 decoder remains supported. Its serialized field shape is retained when a v1 record is read and written again. Existing `turn_resolutions.intent_json` envelopes are still fingerprinted and validated by the durable codec; v2 is a nested analysis schema, not a reinterpretation of an old v1 payload.

## 3. Semantic contract v2 — implemented on the PR #218 branch

### 3.1 Action frames

Each step now has a required `action_frame` containing:

- a literal `predicate` copied from the player's evidence;
- a bounded `family` hint such as movement, communication, perception, transfer, item use, combat, social interaction or state change;
- typed arguments with a semantic `role` and a `mention`.

Supported roles include agent, patient, theme, recipient, source, destination, instrument, location, path, beneficiary, companion, experiencer, owner, holder, container, cause and result.

Each mention contains exact surface text and an untrusted `kind_hint`: character, creature, location, item definition, item instance, event, faction, resource, world entity or unknown. These hints are not IDs. The application still resolves the mention against the visible canonical world.

Example interpretation of “Entrego la llave de hierro a Mara”:

- predicate: “Entrego”;
- theme: “la llave de hierro” (hint: item instance);
- recipient: “Mara” (hint: character).

The frame makes those roles explicit; it does not prove that the transfer succeeded or authorize an inventory write.

### 3.2 Directed relation claims

V2 adds bounded `relation_claims`. Each claim contains:

- existing intent step index;
- literal subject, predicate and object;
- a relation-family hint (kinship, ownership, possession, membership, employment, allegiance, friendship, hostility, spatial, containment, part-of, knowledge, obligation, protection, service, other or unknown);
- polarity and modality;
- a grounded source excerpt;
- optional literal attribution and temporal expression.

Direction is preserved. “Aldric is Mara's brother” and “Mara is Aldric's sister” must not be silently reversed. A reported statement remains reported; a question remains a question; a negative claim remains negative; a conditional is not a confirmed edge. The relation family is a semantic hint, not an authorization list or a replacement for the domain's supported relation types.

### 3.3 Strict trust boundary

V2 parsing rejects unknown fields, invalid enums, oversized arrays/text, non-literal predicates, endpoints, argument mentions, attribution or temporal expressions, and relation claims pointing to nonexistent steps. It accepts no model-supplied canonical IDs.

The action frames and relation claims are untrusted evidence. They do not grant permissions, visibility, provenance, mechanical outcomes or write authority. No relation operation is created solely because a model emitted a claim. The proposal and world application layers must still compare the claim with the snapshot, supported operations, evidence, campaign scope and domain rules.

### 3.4 Retrieval hand-off

The turn service now includes action-frame argument mentions and relation subject/object/attribution mentions among supplemental context-retrieval signals. They add candidates to deterministic retrieval; they do not become canonical identities. The existing bounded selector, dependency expansion, active-character perspective and context budgets remain authoritative.

### 3.5 Durable compatibility

The intent codec persists the nested analysis through the existing durable envelope. V1 records continue to decode as v1; v2 records round-trip their action frames and relation claims. No database migration is introduced for this semantic-schema upgrade because the existing JSON envelope already stores the versioned payload.

## 4. Remaining semantic gaps

### Discourse and corrections
The PR #216 resolver remains deliberately narrow: six recent turns from the same chat, a curated set of Spanish/English pronouns/demonstratives, same-object and other-role patterns, and unique visible candidates. It does not yet provide robust grammatical agreement, semantic-type-aware coreference, speaker/salience modelling, broad ellipsis, distant references, paraphrase resolution or correction chains. V2 relation attribution is still a literal mention, not a resolved speaker identity.

### Time and causality
V2 can carry a literal temporal expression on a relation claim, but it does not yet model a full temporal interval, causal graph, counterfactual state or dependency graph between arbitrary actions. A temporal expression is evidence, not proof of when an event occurred.

### World relation ontology
The current `Relation` domain model stores a directed `relation_type` string and endpoints. The v2 relation-family enum is a language hint. A future domain mapping must explicitly validate which predicates are supported; do not infer support from a matching family name.

### Evaluation depth
The 34-case utterance corpus and six deterministic conversation-reference cases remain small. Existing live intent tests continue to check category/step fields while v2 parsing validates the presence and grounding of frames; they do not yet score semantic-role or relation extraction accuracy comprehensively. A larger held-out frame/relation corpus is planned for PR #220.

## 5. Safety boundaries that must remain

- Model output is evidence, never a canonical ID, permission, visibility grant, provenance assignment, dice result or write authorization.
- Every action argument, relation endpoint and predicate must be grounded in player-authored evidence.
- Context can resolve an antecedent but cannot be represented as text the player wrote.
- Entity identity is attached only by deterministic application code after campaign, active-state, visibility and semantic-type checks.
- Item definition and physical instance are separate domain records.
- Unknown, hidden or ambiguous references remain unresolved.
- Questions, hypotheticals, negations, rumours and reports cannot be promoted to positive confirmed relationships.
- Keep one shared interpretation between mechanics and proposal generation. Do not add a third normal-path model call without measured evidence.
- Do not add embeddings/vector storage until a held-out evaluation proves deterministic retrieval is insufficient.

## 6. Acceptance gates

**Deterministic CI:** required Python/coverage, JavaScript, Ruff, Pyright and CodeQL checks must pass on the final head. The semantic-frame suite must prove v1 compatibility, v2 schema validation, literal-evidence rejection, directed relation round-trip and durable v2 recovery. Existing migrations 033/034, cross-chat isolation, restart recovery, duplicate delivery, clarification and manual-roll tests must remain green.

**Live Ollama:** run `python -m pytest -m real_llm -v -s` with exact model tag/digest, Ollama version, generation settings, timeout and hardware recorded. Retain per-scenario outcomes, latency, repair use and provider-call count. Do not log prompts, secrets or full responses.

**SillyTavern:** use two real chats to prove neither can read or continue the other's history. Verify same-chat references, ambiguous antecedents, multi-round clarification, corrections, manual rolls after restart, duplicate delivery and regeneration. Record backend SHA, extension revision and model details.

The implementation work in PR #218 is not considered accepted until these gates are recorded. Live model and SillyTavern behavior are not inferred from deterministic schema tests.

## 7. Next work after PR #218

PR #219 should focus on discourse resolution and correction chains: typed antecedent evidence, speaker roles, semantic-type/grammatical constraints, topic continuity, pending-intent corrections and safe correction scope.

PR #220 should expand the corpus to at least 100 balanced labelled scenarios with a held-out tranche, and separately score frame slots, relation direction/polarity, entity linking, abstention, false persistent changes, secret leakage and latency.

Do not return to broad gameplay expansion while the live P0 acceptance gates remain unrecorded.
