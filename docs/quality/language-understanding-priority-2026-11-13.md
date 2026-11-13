# P0 — Shared natural-language understanding and intent resolution

**Priority:** P0 — highest active language-quality priority  
**Integrated foundation:** PRs #215–#221 are merged into `main`, including the durable evidence-bound correction lifecycle. Current base: `fd3e90039cc2f3409bec3917f5a34cc7bdaca696` (2026-11-13).  
**Next implementation:** PR #222 adds typed non-entity world references and false-positive-aware semantic evaluation on `feat/222-typed-world-reference-evaluation`.  
**Acceptance:** deterministic CI, live Ollama and real SillyTavern remain separate gates; the latter two are not inferred from CI.  
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

### Discourse and corrections — PR #219 implementation boundary
PR #219 replaces the old nearest-turn string heuristic with typed evidence for visible candidates: player-authored input is kept separate from narrator prose, turn identity and six-turn recency are retained, semantic object-kind hints filter incompatible candidates where the canonical entity type is sufficiently explicit, and repeated topic mentions contribute a bounded continuity signal. A score threshold and minimum margin force clarification rather than a guess. The resolver deliberately does not infer grammatical gender/number because the canonical entity model does not currently store reliable values; it also does not invent NPC speaker identity from an unstructured narrative paragraph.

The same PR adds an immutable `PendingIntentCorrection` application primitive for one target mention, role-labelled action argument or directed relation endpoint. PR #221 now wires this primitive into the correction-only provider response used when a clarification resumes a still-pending durable resolution. The normal turn schema and provider-call count are unchanged. The previous analysis and latest player answer are supplied separately; correction replacements/excerpts must be literal in that answer, must match exactly one pending slot, and must be reflected in the provider's re-analysis. Correction records are retained in the durable audit across clarification rounds. This is a guarded correction protocol, not free-form autonomous mutation or canonical entity resolution.

Remaining gaps include broad ellipsis, long-distance references, semantic paraphrase, topic-shift modelling, real grammatical agreement, explicit NPC-speaker attribution, and reliable model-emitted correction chains. V2 relation attribution remains a literal mention, not a resolved speaker identity.

### Time and causality
V2 can carry a literal temporal expression on a relation claim, but it does not yet model a full temporal interval, causal graph, counterfactual state or dependency graph between arbitrary actions. A temporal expression is evidence, not proof of when an event occurred.

### World relation ontology
The current `Relation` domain model stores a directed `relation_type` string and endpoints. The v2 relation-family enum is a language hint. A future domain mapping must explicitly validate which predicates are supported; do not infer support from a matching family name.

### Evaluation depth
PR #220 expanded the integrated evaluation set to 110 scenarios: 50 development and 60 held-out across utterance/intent, semantic frames/relations and conversation references. The held-out cases remain separate from prompt examples. They measure per-family accuracy, slot recall, entity linking/abstention, context recall, operation precision/recall, critical false persistent changes, secret leakage and latency. This is a first controlled baseline, not comprehensive language coverage; live results must be recorded per family and model version.

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

## 7. Next work after PR #219

PR #219 integrated typed discourse evidence and an immutable correction primitive. PR #221 has since connected model-emitted, evidence-bound corrections to pending durable clarifications, including re-analysis consistency and an audit trail.

PR #220 has merged the 110-scenario evaluation tranche (50 development + 60 held-out). PR #221 now implements the correction hand-off through a correction-only response contract, immutable edit application, re-analysis consistency checks and durable audit. Its acceptance requires tests for ungrounded values, wrong slots, multi-round clarification, lease recovery, stale/committed resolutions and SillyTavern replay.

PR #222 is the next implementation tranche: close the non-entity reference namespace gap (item definition vs physical instance, resources and visible events), penalize extra semantic arguments/relations, and evaluate a real pending-recipient correction with Ollama. After that, use recorded per-family live failures to prioritize ellipsis, topic shifts, relation ontology and temporal modelling. Do not add embeddings or extra normal-path provider calls without measured benefit. Keep broad gameplay expansion behind the live P0 and SillyTavern acceptance gates.
