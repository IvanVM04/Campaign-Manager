# P0 — Shared natural-language understanding and intent resolution

**Priority:** P0 / Priority #1 — modular language-understanding pipeline and prompt-budget reliability  
**Integrated foundation:** PRs #215–#223 are merged into `main`. Current baseline: `7f4f8b10a072665471370fab4493a338835b875c` (2026-11-14).
**Next step:** implement [the modular language-understanding pipeline](modular-language-understanding-pipeline-2026-11-14.md). This is the first P0 deliverable and blocks further semantic feature work. After deterministic architecture/regression gates pass, rerun the live Ollama baseline, add #223 held-out coverage and complete SillyTavern acceptance.
**Acceptance:** deterministic CI, live Ollama and real SillyTavern acceptance are separate gates. Neither live gate is inferred from deterministic CI.

## 1. Current integrated turn pipeline

The following describes the current implementation before PR #225, not the target design:

1. Preserve exact player input, durable request identity, active-character perspective and SillyTavern `conversation_id`.
2. Load bounded, same-chat history and character-visible world context.
3. `MechanicsAdjudicator.understand()` currently returns one structured intent analysis and mechanics decision in a combined provider call.
4. Validate the interpretation against player-authored evidence. DM clarification text may provide context but cannot become a player quotation, mention, relation endpoint or attribution.
5. Deterministic entity and conversation resolvers attach canonical identities only after visibility and ambiguity checks.
6. Pass the exact same analysis to `LLMWorldExtractor`; the proposal stage uses it rather than independently reconstructing player intent.
7. Parse proposed typed operations and apply them through deterministic world/domain services. Rules code remains authoritative for mechanics.
8. Persist the validated interpretation and its evidence with the durable resolution. Clarification reinterprets the original request plus player answers; manual rolls reuse the stored interpretation.
9. Narrate only committed consequences. SillyTavern history and continuation remain scoped to one chat.

The combined step 3 is the coupling being removed. The target keeps one authoritative interpretation but moves mechanics adjudication behind its own conditional interface; see [the modular pipeline decision](modular-language-understanding-pipeline-2026-11-14.md).

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

### Discourse and corrections — PRs #219–#223 integrated
PR #219 replaces the old nearest-turn string heuristic with typed evidence for visible candidates: player-authored input is kept separate from narrator prose, turn identity and six-turn recency are retained, semantic object-kind hints filter incompatible candidates where the canonical entity type is sufficiently explicit, and repeated topic mentions contribute a bounded continuity signal. A score threshold and minimum margin force clarification rather than a guess. The resolver deliberately does not infer grammatical gender/number because the canonical entity model does not currently store reliable values; it also does not invent NPC speaker identity from an unstructured narrative paragraph.

The same PR adds an immutable `PendingIntentCorrection` application primitive for one target mention, role-labelled action argument or directed relation endpoint. PR #221 now wires this primitive into the correction-only provider response used when a clarification resumes a still-pending durable resolution. The normal turn schema and provider-call count are unchanged. The previous analysis and latest player answer are supplied separately; correction replacements/excerpts must be literal in that answer, must match exactly one pending slot, and must be reflected in the provider's re-analysis. Correction records are retained in the durable audit across clarification rounds. This is a guarded correction protocol, not free-form autonomous mutation or canonical entity resolution.

PR #223 is merged. It adds a deterministic bounded discourse index for ellipsis cues, explicit topic shifts/callbacks, twelve-turn references, locally evidenced grammatical agreement and unambiguous NPC quote labels. It does not infer gender from names or treat NPC speech as player instructions. Remaining gaps include implicit topic-shift detection, broad semantic paraphrase, unresolved group references, richer dialogue-act graphs and measured live-model quality. The discourse block is bounded (650 characters) and may be compacted or omitted under prompt-budget pressure; the live evaluation must verify whether it reaches the model. V2 relation attribution remains a literal mention, not a resolved speaker identity.

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
- Keep one authoritative shared `PlayerIntentAnalysis` for mechanics and proposal generation, but separate the responsibilities and response contracts. Mechanics is a conditional call that returns only `MechanicsDecision`; it is skipped when no active unresolved attempt requires it. Do not split the semantic interpretation itself into independent calls for actions, roles, relations or discourse.
- Do not add embeddings/vector storage until a held-out evaluation proves deterministic retrieval is insufficient.

## 6. Acceptance gates

**Deterministic CI:** required Python/coverage, JavaScript, Ruff, Pyright and CodeQL checks must pass on the final head. The semantic-frame suite must prove v1 compatibility, v2 schema validation, literal-evidence rejection, directed relation round-trip and durable v2 recovery. Existing migrations 033/034, cross-chat isolation, restart recovery, duplicate delivery, clarification and manual-roll tests must remain green.

**Live Ollama:** run `python -m pytest -m real_llm -v -s` with exact model tag/digest, Ollama version, generation settings, timeout and hardware recorded. Retain per-scenario outcomes, latency, repair use and provider-call count. Do not log prompts, secrets or full responses.

**SillyTavern:** use two real chats to prove neither can read or continue the other's history. Verify same-chat references, ambiguous antecedents, multi-round clarification, corrections, manual rolls after restart, duplicate delivery and regeneration. Record backend SHA, extension revision and model details.

The integrated implementation through PR #223 is not considered accepted until these gates are recorded. Live model and SillyTavern behavior are not inferred from deterministic schema tests.

## 7. Next work after PR #223 — P0 Priority #1

The next implementation is **PR #225 — Modular Language-Understanding Pipeline**. It is an architecture correction, not another capability layer.

1. Extract one coherent `IntentInterpreter` that produces the authoritative `PlayerIntentAnalysis` v2.
2. Move mechanics adjudication to a separate, conditional component that consumes the validated active step and relevant mechanical context and returns only `MechanicsDecision`.
3. Retain the same validated analysis for the world proposal planner; do not reinterpret the utterance.
4. Make the consequence-planning call conditional on a justified persistent change and confirmed prerequisites.
5. Modularize the common safety contract, role-specific policies and response schemas. Avoid copying schema enumerations and full JSON examples into every prompt.
6. Instrument per-role prompt bytes, actual token usage when available, section truncation, provider-call count, duration and classified provider failures.
7. Preserve v1/v2 durable compatibility, pending corrections, chat isolation, manual-roll continuation and domain authority.

A focused Ollama test run on 2026-11-14 showed that the known-NPC Aldric case fails before provider invocation because the combined mechanics prompt exceeds its configured estimated budget. The prompt estimate is UTF-8 bytes, not a model tokenizer count. The architecture tranche must remove this avoidable preflight failure before a new live baseline is trusted.

After the refactor and its deterministic contract tests pass, rerun the existing 110-case corpus and operation-quality controls with the exact same model/settings. Then add held-out tests for #223 discourse behavior and complete the two-chat SillyTavern acceptance. Do not add more semantic feature PRs, embeddings or multi-agent infrastructure ahead of this sequence.

## 8. PR #223 — advanced discourse understanding

Implementation base: `48116ce879df5abb6dae9995ba854dbc44bc538e` (merged PR #222).
The implementation expands the shared bounded history from six to twelve turns.
Explicit topic-shift markers scope ordinary antecedent lookup to the active
segment. An explicit callback (for example, "volviendo a..." or "retomando...")
can reopen the bounded window but does not bypass score and ambiguity checks.

A deterministic discourse index is appended to the existing intent and
proposal prompts; the normal provider-call count remains unchanged. It
highlights likely ellipsis, topic transitions/callbacks, explicit NPC quote
labels and local grammatical agreement. The model still emits only untrusted
semantic evidence; deterministic resolution and domain services remain the
authority.

NPC speaker evidence is created only for uniquely labelled quoted speech from
an active visible NPC. Other names inside the quotation are not attributed to
the speaker. Singular pronoun agreement filters candidates only when an
explicit local article/apposition is present. Plural pronouns do not collapse
to a single character because the domain has no group entity.

Required deterministic tests cover topic segmentation, callbacks, twelve-turn
recency/expiry, NPC label uniqueness and visibility, quoted-speech separation,
grammatical conflict/unknown cases, ambiguous ellipsis and v1/v2 compatibility.
Live Ollama and SillyTavern remain separate acceptance gates.


## 9. Current status after PR #223

PR #223 is merged. Its final deterministic Tests and CodeQL workflows passed. The 1,774 deterministic test result and 85.31% combined coverage do not include the 15 excluded live tests. No live Ollama pass or manual SillyTavern acceptance is claimed. Use the [independent audit](language-understanding-audit-2026-11-14.md) as the current work register.