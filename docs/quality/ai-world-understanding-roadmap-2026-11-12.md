# AI world understanding and player-intent quality roadmap

**Status:** PRs #210–#216 are integrated. PRs #215–#216 deliver the shared typed intent contract, durable evidence and bounded chat-scoped reference resolution.  
**Verified base:** `main` at `868ae7ae29c6c1c0cfb5b3aaf181b630a0039ff6` (2026-11-13; PR #216 merged).  
**Priority override (2026-11-13): P0 — shared natural-language understanding and intent resolution.** This is the highest active priority and blocks the Character Builder/gameplay expansion until its live-model and SillyTavern gates are recorded. See [the P0 implementation specification](language-understanding-priority-2026-11-13.md).  
**Initial local model:** `gemma4:26b` through Ollama (user-run acceptance; not a CI dependency)  
**Primary objective:** make Campaign Manager reliably understand campaign state, retrieve facts relevant to a player's words, distinguish intent from outcome, propose only justified persistent changes, and narrate from committed evidence.

This roadmap is intentionally broader than prompt wording. Model quality depends on what the application retrieves, how evidence is represented, how player language is interpreted, the operation contract, deterministic validation, and the evidence supplied to narration.

## 1. Executive direction

The project already has a strong modular foundation:

- canonical `WorldState` and typed campaign/character/session models;
- deterministic memory search, relation expansion, relevance ranking and dependency-aware context selection;
- a detached, bounded `WorldContextProjection`;
- a registry-derived typed operation contract and parser trust gate;
- deterministic mechanics adjudication and application;
- a separate narrative service;
- durable turn idempotency, revision checks, recovery and transaction boundaries;
- deterministic CI and opt-in live Ollama probes.

The P0 shared interpretation and conversation-scope implementation is now integrated. The blocking work is to record its live Ollama and real SillyTavern acceptance evidence. Do not begin the Character Builder or broad gameplay expansion until those gates are passed. The next language implementation after that baseline is structured semantic frames and grounded relation/object understanding; see the [next-phase plan](semantic-understanding-next-phase-2026-11-13.md).

This is a focused correctness/quality priority, not a return to broad architecture decomposition.

**Do not solve comprehension by creating one enormous prompt.** Keep static rules, world facts, player intent, confirmed mechanics, operation schemas and narration evidence as separate, explicit inputs. Give each model role the smallest context sufficient for its responsibility.

The target is not that the model "knows everything". The target is that it:
1. knows which facts were supplied;
2. retrieves the facts relevant to this action;
3. recognizes which facts are missing or uncertain;
4. does not convert wishes, hypotheses, attempts or failures into confirmed outcomes;
5. proposes valid, minimal changes only when evidence supports them;
6. preserves continuity without exposing secrets or inventing canon.

## 2. Non-negotiable invariants

### Canonical state and authority

- `WorldState` remains the canonical in-memory domain state hydrated from persistence.
- The LLM may propose typed operations; it never writes to persistence, authorizes itself, rolls dice or bypasses the world application layer.
- Deterministic mechanics own checks, attack results, damage, HP, conditions and other rules-governed outcomes.
- `WorldService` / appliers remain authoritative for existence, campaign scope, permissions, referential integrity and mutation.
- The durable turn workflow retains idempotency, revision fencing, lease fencing, short atomic commits and recovery.
- Narration is generated from committed consequences, not used as the source for world mutations.

### Epistemic safety

- A confirmed fact is not the same as an inference, rumor, hypothesis, player wish or attempted action.
- A character's knowledge is not automatically the same as GM/canonical campaign truth.
- A secret event must remain absent from player-facing context unless an explicit future authorization/visibility contract allows it.
- Unknown information stays unknown. The model must not fill blank fields with plausible fantasy details.
- An action's intended result is not proof that the result occurred.
- A failed action cannot be narrated or persisted as a success.
- Existing records must be reused when the referent is already known; new records must not be created merely because the player used a synonym or role description.

### Evaluation discipline

- Deterministic invariants belong in normal CI and must not depend on model wording.
- Real-model tests remain opt-in and report model/version/settings.
- Live failures are evidence, not a reason to weaken assertions.
- Repeatability, positive controls and negative controls matter more than raw test count.
- Record false positives, omissions, ambiguity handling and repair behavior separately.
- A green model smoke test is not proof of complete comprehension or SillyTavern acceptance.

## 3. Current architecture and observed gaps

### Active data flow — PRs #215 and #216 integrated

`TurnResolutionService` now orchestrates a shared semantic interpretation:

1. receive and validate the player's original input, with bounded recent visible turns;
2. call `MechanicsAdjudicator.understand()` once; the structured response contains both a versioned `PlayerIntentAnalysis` and a mechanics decision;
3. validate literal source excerpts/target mentions and the active step; skip mechanics adjudication for questions, plans, dialogue, negations and already-reported outcomes;
4. build a bounded `WorldContextProjection` only when the analysis permits a world proposal, using literal target mentions and recent turns as supplemental retrieval signals;
5. pass the exact same analysis object and bounded visible history to `LLMWorldExtractor`; the proposal prompt must not independently reinterpret the raw utterance or execute future steps;
6. parse/validate typed operations and apply them through the existing world application boundary;
7. narrate from the committed resolution through `DMService`.

The durable resolution stores the analysis and exact source text in `intent_json`, with a SHA-256 source fingerprint. Manual-roll continuation reuses the saved analysis; clarification continuation appends its answer to the original source and produces a new analysis. Migration 033 adds the column and protects committed evidence.

The dependency direction remains: `services/turns` can orchestrate `services/context`; `services/llm_world` must not import `services/context`.

### Confirmed limitations found during the first Ollama run and source review

- The renderer previously emitted an entity's name and type but omitted its description and notes. A model could be told that a door existed while not being told that it was locked.
- Item descriptions/significance/notes, item-instance condition/notes and resource notes were also available in selected records but not rendered to the proposal prompt.
- The operation manifest truncated operation descriptions to 32 characters and omitted useful field explanations such as `entity_type`, `description`, `notes` and `condition`.
- The initial real-model corpus allowed a vacuous "valid list" pass and used an empty world for the failed-door case, so the model could create a new door entity without contradicting existing state.
- Retrieval is deterministic and largely lexical. It currently has one-hop relation expansion and a stable ranker; matching "the innkeeper" to a known NPC whose record contains only a proper name is not yet a guaranteed contract.
- There is no explicit, typed provenance/epistemic model for confirmed, inferred, rumored, unknown and character-known facts. A boolean secret flag is not a full knowledge model.
- The adjudicator and proposal stages now share the same typed interpretation. Narration remains a separate post-commit responsibility; the semantic contract is not a fact or write authority.
- PR #216 adds a deterministic conversation resolver over at most six recent turns in the same chat. It handles a narrow set of Spanish/English pronouns, demonstratives, same-object and curated other-role patterns, and resolves only one visible candidate. Grammatical agreement, semantic-type constraints, speaker-aware discourse, broad ellipsis, arbitrary paraphrase and correction-chain reasoning remain open.
- The live model has not yet been shown to follow the new combined JSON contract repeatably. Deterministic schema tests do not measure live semantic accuracy or latency.

PR #210 addresses renderer/operation-manifest gaps; PRs #211–#213 add alias resolution, multi-signal retrieval and single-pass semantic prompt rules; PR #214 adds event provenance/perspective and narrative grounding; PR #215 delivers shared typed intent and durable evidence; PR #216 delivers chat isolation, bounded reference resolution and Ollama schema-constrained generation. Live Ollama and manual SillyTavern acceptance remain mandatory and are not inferred from merged code.

## 4. Target architecture: shared evidence, specialized responsibilities

The intended shape is:

1. **Canonical campaign state** — typed world, character, campaign, session and durable resolution data.
2. **Context retrieval** — deterministic candidate retrieval, relation/dependency expansion, ranking, mandatory facts, visibility filtering and bounded projection.
3. **Semantic interpretation** — identify the action, target, references, modality, negation, explicit outcome and uncertainties. This stage is a proposal, never an authority.
4. **Mechanics adjudication** — determine whether a check or clarification is required; deterministic rules resolve the actual result.
5. **World proposal** — produce the smallest set of typed, grounded operations, or an empty list.
6. **Domain validation and commit** — validate against current state/revision and apply atomically.
7. **Narration** — present committed facts and mechanics without adding uncommitted consequences.

This does not require seven model calls. Several stages may share one call where evidence demonstrates that quality remains acceptable. The boundaries describe ownership and evaluation, not a mandated number of providers.

## 5. PR roadmap

### PR #210 — Semantic prompt contract and evaluation baseline

**Goal:** make the current one-pass proposal flow understand the evidence it already receives and give us a meaningful quality baseline.

**Included work:**
- render entity descriptions and notes;
- render selected item descriptions/significance/notes, instance condition/notes and resource notes;
- make the operation manifest more informative without sending full verbose JSON Schema for every operation;
- add precise field guidance for NPC/entity type, grounded description, existing identity, relationship evidence and durable events;
- distinguish wishes/plans, attempts, failure/negation, hypotheses and explicitly established facts;
- explicitly require reuse of known IDs and discourage duplicate entities;
- require new NPC creation only for an explicitly introduced, persistent, distinguishable person;
- correct live tests so positive and negative controls test actual semantic contracts;
- ensure the known-door failure scenario includes a pre-existing locked door;
- retain bounded prompts, a single bounded repair and the existing trust boundary;
- record the new roadmap and the observed test baseline.

**Acceptance criteria:**
- deterministic tests prove the renderer exposes facts already charged to the projection budget;
- prompt tests prove the interpretation/persistence rules and registry field guidance are present;
- registry tests prove NPC examples are typed and contract size remains bounded;
- four live Ollama scenarios include two useful positive controls (new fact on an existing NPC; creation of a newly introduced NPC) and two negative controls (ephemeral observation; failed attempt on a known locked door);
- no test passes merely because an empty list has the right Python type;
- deterministic CI, lint, typing and CodeQL are green;
- local Ollama results are recorded separately; no claim of pass before the user runs them.

**Non-goals:** vector search, new database schema, generic memory framework, separate intent LLM call, changes to mechanics authority, narrative-first mutation, weakening domain validation.

### PR #211 — Context retrieval and reference resolution

**Implementation branch:** `feat/entity-reference-resolution`. This tranche adds typed entity aliases, conservative deterministic matching, ambiguity abstention, detached resolution diagnostics and a forward-only SQLite migration (031), threaded through the API/domain/LLM contracts.


**Goal:** retrieve the right canonical records when the player refers to them indirectly.

**Investigation and delivery:**
- [x] Cover canonical names, explicit aliases, role descriptions, case/diacritic normalization, multiple explicitly named entities and ambiguous collisions with deterministic contract tests;
- [x] Require all significant query terms to match a single role description/notes field; canonical names and explicit aliases outrank descriptive fallbacks;
- [x] Add bounded, typed alias data through domain, bootstrap API, read models, structured operations and migration 031; never infer aliases from free-form notes;
- resolve role references ("el tabernero"), location references ("la mujer de la posada") and multi-entity references without selecting a similarly named NPC;
- review one-hop graph expansion against actual campaign queries; add bounded multi-hop expansion only with evidence and cycle/size controls;
- preserve dependency bundles, active character/current location, secret exclusion, stable ordering, detachment and fail-closed mandatory budgets;
- [x] Add detached projection diagnostics for reference status, match kind and candidate count without recording raw player text;
- [ ] Extend retrieval measurement to multi-turn pronouns, paraphrases and inflections once conversation history and speaker/visibility semantics are explicit;
- evaluate whether a provider-native embedding endpoint or a local embedding model adds enough recall to justify an optional semantic retrieval collaborator.

**Acceptance criteria:**
- a labelled corpus reports precision/recall for direct and indirect references;
- known entities resolve to the correct canonical ID;
- ambiguous references abstain or request clarification rather than selecting arbitrarily;
- no secret fact enters player-facing projection;
- large-campaign tests remain deterministic and bounded;
- no vector database or cache is added without a measured need.

### PR #212 — Retrieval and SillyTavern integration hardening

**Goal:** make the current player action the primary retrieval signal and keep
broad campaign-scope wording independent, so it supplements rather than dilutes
the specific action being processed.

**Implementation:**
- [x] Add an optional `additional_query` to SillyTavern context, resolve,
  clarification and manual-roll requests. Existing clients may continue sending
  a single `query`.
- [x] Submit the current player action in `query` and the configured
  campaign-scope text independently in `additional_query`.
- [x] Merge independent searches in stable order, deduplicate records by their
  category-local IDs and retain the primary query as the ranking signal.
- [x] Add optional supplemental queries to narrative and proposal context
  builders without changing existing default call sites.
- [x] Improve descriptive entity matching inside complete natural-language
  actions using shared, rarity-weighted terms. Explicit names and aliases retain
  precedence.
- [x] Keep identity resolution conservative when multiple descriptive
  candidates remain similarly plausible. The resolver returns an ambiguous
  status and no singular entity ID; retrieval may still surface evidence-backed
  descriptive candidates as context, without claiming one is the resolved target.
- [x] Expose privacy-safe adapter diagnostics (query and included-record counts,
  never the query strings themselves).
- [x] Add deterministic tests for long role references, tie/ambiguity handling,
  supplemental-query union, duplicate suppression, API schemas and the
  SillyTavern request builder.

**Limits deliberately retained:**
- Retrieval remains deterministic and lexical. A paraphrase with no shared
  words still needs an explicit alias or a future semantic retrieval mechanism.
- No pronoun/ellipsis resolution across turns is claimed. That requires a
  speaker, recency, visibility and dialogue-state contract.
- The supplemental campaign-scope query is not allowed to replace the player's
  action as the primary query or ranker input.
- No embeddings, vector database, persistent cache, extra provider call or new
  migration is introduced.

**Acceptance:** deterministic checks protect the contract. Live Ollama quality
and the complete manual SillyTavern smoke test remain separate acceptance
gates and must not be marked passed until actually run.

### PR #213 — Player-intent semantics

**Goal:** interpret what the player means, not just match words in the input.

**Scenarios and semantics:**
- intention vs action vs outcome;
- successful, failed, interrupted and impossible attempts;
- negation scope ("no abro la puerta", "no consigo abrirla");
- conditional/hypothetical statements ("si consigo la llave...");
- plans/future tense vs completed observation;
- questions, dialogue and reported speech;
- quoted speech vs instructions embedded in untrusted campaign text;
- pronouns, ellipsis and multiple possible referents;
- player correction ("no, me refería al guardia de la puerta");
- compound actions with ordered targets;
- ambiguous intent requiring a concise clarification.

**Design decision for this tranche:**
- retain the existing single-pass proposal flow and strengthen its bounded semantic contract;
- do not add a separate typed interpretation object or another model call yet: the current corpus has not demonstrated that the additional latency, recovery state and failure modes buy measurable quality improvements;
- evaluate modality and action-state handling across positive/negative live controls before revisiting a typed intermediate contract;
- if later evidence justifies one, keep action kind, references, modality/negation, explicit facts, uncertainty and clarification as untrusted input;
- never allow an interpreter to certify mechanics or state changes.

**Acceptance criteria:**
- a versioned live corpus contains positive and negative controls for intention, active attempt, explicit outcome, negation, failure, hypothesis, question, dialogue/quoted speech and compound actions;
- deterministic prompt-contract tests protect the modality and ordering rules without depending on model wording;
- no false success from a failed, negated or conditional action in the core corpus;
- ambiguous targets fail closed or ask a clarification rather than fabricating an identity;
- every live case reports its own outcome; do not claim a confusion matrix or model-quality pass until the local model has actually been run;
- a separate typed interpretation call remains deferred unless measured quality/latency results justify it.

**PR #213 delivery boundary:** prompt rules and opt-in live cases are implemented as an application-level contract. The real Ollama corpus and SillyTavern acceptance still require local execution and are not inferred from deterministic CI.

### PR #214 — Knowledge provenance, character perspective and committed narrative grounding

**Goal:** represent how campaign events are known, which player-character can access them, when they occurred, and ensure adjudication/proposals/narration share the same evidence.

**Implementation:** this larger tranche deliberately combines the original #214 and #215 work so privacy and narrative grounding are verified across the complete read/turn boundary rather than split across partial PRs.

- [x] Add typed event epistemic status (`confirmed`, `rumor`, `inference`) and provenance source (`gm_authored`, `direct_observation`, `npc_statement`, `discovered_document`, `rules_result`, `model_inference`, `imported`).
- [x] Add event visibility scopes (`public`, `character`, `gm_only`), explicit known-by character IDs, source entity, campaign elapsed time and a supersession link.
- [x] Keep the legacy `secret` flag as a compatibility alias for GM-only visibility; migration 032 preserves old public records and backfills old secret records as GM-only.
- [x] Enforce visibility using the active character resolved by trusted application state across memory search/context, proposal selection, mechanics adjudication, native narration, SillyTavern context, world/event collection reads and public export.
- [x] Keep character-audience IDs internal: player-facing event projections expose the event's epistemic/provenance/temporal labels but not the complete set of other characters who know it.
- [x] Preserve superseded facts as history, mark them non-current in retrieval/read projections, and persist supersession chains in dependency order; reject cycles.
- [x] Allow model-originated event proposals only as `inference/model_inference`; the parser strips untrusted provenance fields and the world applier assigns the non-canonical status. Trusted workflows can author confirmed facts.
- [x] Feed the narrator only operations whose application result explicitly says both `success=true` and `changed=true`; omit failed, rejected, no-op, malformed and result-less proposal entries.
- [x] Distinguish confirmed facts, attributed rumors and non-canonical inferences in narrative instructions; use the active character's knowledge projection.
- [x] Add deterministic tests for migration/backfill/idempotency, campaign-scoped provenance references, per-character visibility, expansion leak prevention, history supersession, API/SillyTavern perspective, repository ordering and committed-only narration evidence.

**Explicit limits retained:**

- The typed provenance/epistemic contract currently applies to campaign events. Entity descriptions/notes, item descriptions and other free-text fields do not yet have per-assertion provenance.
- `known_by_entity_ids` represents character knowledge, not a separate player's out-of-character knowledge ledger.
- Confidence scores, document/page citations, source text snapshots, and full event sourcing are not added. Keep provenance limited to data the application can maintain reliably.
- Unknown remains the absence of a supplied fact; it is not stored as a fabricated event.
- The active character perspective is fail-closed for character-scoped events when no character is active.
- Existing turns keep their durable identity/recovery contract. Narration regeneration does not reapply operations.
- Deterministic CI does not prove local Ollama semantics or a complete SillyTavern user session; those remain separate acceptance gates.

**Acceptance boundary:** deterministic tests and CI protect application privacy/authority invariants. Run and record the expanded local Ollama and manual SillyTavern acceptance separately; do not claim either passed before execution.

**Consolidation note:** PRs #215 and #216 are integrated. The next understanding step is not another prompt-only pass; it is the evidence-bound semantic-frame work in the [next-phase plan](semantic-understanding-next-phase-2026-11-13.md). Model benchmarking remains conditional on a stable corpus and recorded baseline.

### Deferred follow-up — Benchmark hardening and model selection (after P0)

**Priority:** P2 / conditional. This work is intentionally behind the shared language-understanding P0 implementation and acceptance gate.

**Goal:** establish evidence for a default local model and regression policy.

Only proceed when the expanded corpus is stable enough to compare models. Do not let model selection distract from fixing the shared interpretation contract.

- run the same versioned corpus against candidate Ollama models;
- record model digest/tag, Ollama version, sampling parameters, hardware class, duration, token/character counts and per-scenario outcomes;
- compare operation precision/recall, false-positive severity, abstention, retrieval recall, secret leakage and latency;
- run repeated trials and retain raw per-run outcome metadata without storing prompts, private campaign facts or full model responses in CI;
- choose a model on quality/safety/latency trade-offs, not parameter count or one successful example;
- keep the selected model configurable and do not silently change production defaults.

**Acceptance criteria:** published comparison report with reproducible settings and explicit safety failures; no model change based on anecdotal output alone.

### Next implementation after P0 acceptance — semantic frames and grounded relations

The current v1 contract stores the action as free text and targets as an untyped list. It cannot directly express recipient/source/destination/instrument roles, typed object identity or a directed relation claim with modality, polarity, attribution and time. Add a versioned evidence-bound semantic frame, then improve speaker-aware discourse and correction resolution. See the [detailed next-phase plan](semantic-understanding-next-phase-2026-11-13.md). Do not add embeddings or another normal-path model call before measurement.

## 6. Evaluation corpus design

Use versioned scenario fixtures with:
- world state (known entities, descriptions, aliases if supported, relationships, locations, items, resources and events);
- player input in natural Spanish first, with English and multilingual cases added deliberately rather than mixed randomly;
- expected retrieved facts and forbidden facts;
- expected operation constraints (required, forbidden, allowed alternatives);
- expected clarification/abstention behavior;
- scenario tags: identity, reference, negation, modality, mechanics, secrecy, temporal, persistence, dialogue, ambiguity and scale.

The corpus should include these families:

| Family | Positive cases | Negative/abstention cases |
|---|---|---|
| Entity identity | create a named, newly introduced NPC; update a known NPC with a new observed fact | do not duplicate a known NPC; do not create every anonymous passer-by |
| Indirect references | "el tabernero" resolves to the innkeeper; pronoun resolves to the previous speaker | two guards fit the phrase; no unique target, so abstain/clarify |
| Relations | explicit alliance, ownership or membership is established | proximity or one conversation does not invent friendship/loyalty |
| State transitions | confirmed door opening, item transfer or clue discovery | failed attempt, hypothetical, negation or unresolved roll changes nothing |
| Events | durable public event with explicit evidence | ephemeral dialogue/observation is not a campaign event |
| Knowledge | character finds a public clue and can recall it later | GM secret and unknown motive remain unavailable |
| Temporal | update a changed location/status without duplicating history | stale summary does not overwrite newer canonical state |
| Compound intent | ordered actions with resolvable references | partial failure does not imply later steps succeeded |
| Prompt injection | ordinary names/notes containing hostile-looking text remain data | embedded instructions do not override system contract |
| Scale | high-signal facts survive a larger world and bounded context | irrelevant candidates do not crowd out mandatory facts |

A scenario's oracle should describe semantic constraints, not one exact JSON string. Several operation sequences may be valid if they preserve the same world invariants. Keep assertions strict about forbidden changes and required facts.

The P0 implementation adds `tests/fixtures/language_understanding_corpus_v1.json` with 34 labelled Spanish/English scenarios (12 critical, repeated three times by the opt-in corpus test). PR #216 adds `tests/fixtures/conversation_understanding_corpus_v2.json` with six deterministic resolver scenarios. These validate application resolution, not live model coreference accuracy. Run and record both layers separately; neither corpus proves acceptance until executed.

## 7. Metrics and reporting

Report each metric by scenario family and model:

- **Context precision:** selected facts that are genuinely relevant / all selected facts.
- **Context recall:** required relevant facts included / all required relevant facts.
- **Dependency completeness:** selected records whose required ID/owner/location/resource dependencies are all present.
- **Operation precision:** justified proposed operations / all proposed operations.
- **Operation recall:** required semantic changes represented / all required semantic changes.
- **False-positive rate:** unsupported persistent changes, especially successful outcomes from failed/conditional actions.
- **Abstention quality:** correctly empty/clarify cases vs incorrect empty/guess cases.
- **Identity resolution:** correct canonical entity ID selected vs duplicate/misresolved entity.
- **Secret leakage:** count of forbidden secret facts in model-facing context or player-facing output; acceptance is zero.
- **Continuity:** committed facts correctly retained/updated across multi-turn sequences.
- **Repair rate:** fraction of first responses requiring repair; track repair success separately.
- **Latency:** provider duration and end-to-end duration, reported as distributions rather than one average.

Never collapse false positives and omissions into one score: their severity differs. A false persistent success may corrupt the campaign; an omission may be recoverable by asking the player or GM.

## 8. Execution and quality gates

### Every PR

- start from current integrated `main`, one focused objective;
- update package docs, roadmap and current architecture index where needed;
- preserve modular dependency direction and typed authority boundaries;
- add deterministic tests for all newly introduced invariants;
- run Ruff, deterministic Python tests with the 85% combined coverage gate, JavaScript tests, both Pyright scopes and CodeQL;
- keep CI independent of Ollama, SillyTavern and internet availability;
- don't merge while required checks are pending or failed.

### Live Ollama evaluation

- run locally using explicit model/base URL/timeout;
- record the exact model tag and Ollama version;
- repeat unstable scenarios at least three times while debugging;
- do not log full prompts, raw responses, secrets or campaign state;
- do not change the application's default model to make a probe pass;
- preserve every failed run in the evaluation notes.

### SillyTavern

Do not begin the complete manual checklist until the current proposal corpus has no unresolved critical false-positive behavior. After model-level checks pass, run the separate [SillyTavern smoke test](../sillytavern-smoke-test.md), recording backend and extension revisions.

## 9. Explicit non-goals and deferred infrastructure

Do not introduce the following merely because they sound like AI best practices:

- vector database or embedding service before retrieval measurements justify it;
- Redis, distributed cache, message bus, microservices or multi-agent framework;
- a giant static prompt or prompt snapshots brittle to harmless wording changes;
- an LLM-controlled permission system;
- model-written canonical facts without domain validation;
- another narrative-first extraction path;
- automatic model switching or retries hidden from the evaluation report;
- new migrations for provenance until typed semantics and migration defaults are designed; aliases now have a typed contract and migration 031.
- arbitrary prompt/context budgets based on unverified tokenizer assumptions.

## 10. Exit criteria for the AI-understanding phase

The phase is mature enough to return focus to gameplay when:

1. retrieval tests reliably find the intended entity/facts and abstain on ambiguous references;
2. player intent, attempt, failure, negation and hypothesis are distinguished across paraphrases;
3. persistent facts are proposed only when explicitly grounded, with correct existing IDs and no duplicates;
4. character/GM perspective and secret visibility are protected end-to-end;
5. mechanics remain deterministic and authoritative;
6. narration follows committed state across multiple turns;
7. false positives and omissions are measured separately, with no unresolved critical false-success behavior in the acceptance corpus;
8. the target local model demonstrates repeatable results on the versioned corpus;
9. SillyTavern's full durable integration smoke test passes on recorded revisions.

**Guiding rule:** improve the evidence and the contracts first; add model complexity or infrastructure only when measured failures show that the simpler architecture is insufficient.
