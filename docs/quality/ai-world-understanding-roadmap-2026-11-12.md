# AI world understanding and player-intent quality roadmap

**Status:** active engineering roadmap; PRs #210 and #211 are integrated, PR #212 hardens retrieval and SillyTavern integration.  
**Verified base:** `main` at `01ffcb7f94df105454b241ce142c9694016da741` before PR #212.  
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

The next phase should improve the quality of each boundary without replacing the architecture or introducing a second proposal pipeline.

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

### Active data flow

`TurnResolutionService` orchestrates the existing flow:

1. receive the player's original input;
2. ask `MechanicsAdjudicator` whether a deterministic check/clarification is needed;
3. construct a bounded `WorldContextProjection` through `ContextBuilder` / `ProposalContextSelector`;
4. render the projection and operation contract with `LLMWorldProposalPromptBuilder`;
5. call `LLMWorldExtractor` and parse/validate the structured operations;
6. validate and apply operations through the world application boundary;
7. narrate from the committed resolution through `DMService`.

The dependency direction remains: `services/turns` can orchestrate `services/context`; `services/llm_world` must not import `services/context`.

### Confirmed limitations found during the first Ollama run and source review

- The renderer previously emitted an entity's name and type but omitted its description and notes. A model could be told that a door existed while not being told that it was locked.
- Item descriptions/significance/notes, item-instance condition/notes and resource notes were also available in selected records but not rendered to the proposal prompt.
- The operation manifest truncated operation descriptions to 32 characters and omitted useful field explanations such as `entity_type`, `description`, `notes` and `condition`.
- The initial real-model corpus allowed a vacuous "valid list" pass and used an empty world for the failed-door case, so the model could create a new door entity without contradicting existing state.
- Retrieval is deterministic and largely lexical. It currently has one-hop relation expansion and a stable ranker; matching "the innkeeper" to a known NPC whose record contains only a proper name is not yet a guaranteed contract.
- There is no explicit, typed provenance/epistemic model for confirmed, inferred, rumored, unknown and character-known facts. A boolean secret flag is not a full knowledge model.
- The adjudicator, world proposer and narrator have distinct roles, but their semantic decisions need a shared evaluation corpus to expose disagreements and continuity failures.

PR #210 addresses the renderer/contract gaps and corrects the live-test fixtures.
PR #211 adds explicit alias data and conservative entity resolution. PR #212
hardens multi-signal retrieval and SillyTavern integration. Conversation-level
intent, knowledge perspective and cross-role grounding remain later work.

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

**Design decision to make with evidence:**
- compare the current single-pass prompt with an optional typed intent interpretation object;
- evaluate whether the object improves downstream proposals enough to justify another model call, latency, recovery state and more failure modes;
- if introduced, define a small typed contract (action kind, target references, modality/negation, explicit facts, uncertainty and required clarification) and keep it as untrusted input;
- never allow the interpreter to certify mechanics or state changes.

**Acceptance criteria:**
- confusion matrix / per-class results for intent, attempt, negation, hypothetical and explicit outcome;
- positive and negative controls across several phrasings;
- no false success from a failed or conditional action in the core corpus;
- malformed/ambiguous interpretations fail closed or ask a clarification rather than fabricating a target;
- if a second LLM call is proposed, measured quality/latency trade-off accompanies the design.

### PR #214 — Knowledge provenance, perspective and temporal continuity

**Goal:** represent not just what is true, but how it is known, to whom and when.

**Investigation and delivery:**
- distinguish canonical GM truth, player-character knowledge, public knowledge, rumor, inference, unknown and secret;
- define provenance: explicit observation, NPC statement, discovered document, rules result, GM-authored fact or model inference;
- define source/session/time and confidence only where domain workflows can maintain them reliably;
- distinguish "known to the player" from "known to the character";
- ensure secret information cannot leak through summaries, retrieval, narration or repair prompts;
- represent temporal changes without overwriting history where continuity requires it;
- decide whether these contracts require new domain models and forward-only SQLite migration; avoid stuffing structured meaning into free-form notes/metadata;
- define how contradictions are resolved: canonical committed fact wins; unverified claims remain attributed/uncertain; conflicting evidence prompts clarification or a GM decision.

**Acceptance criteria:**
- tests for perspective isolation and secret leakage at all read/render boundaries;
- tests for rumor vs confirmed fact and for stale facts superseded by later committed state;
- multi-turn tests show the narrator uses current state and retains relevant historical evidence;
- migration tests preserve existing campaign data and default legacy records safely;
- no model can elevate an inference/rumor into canonical truth without an application-authorized workflow.

### PR #215 — Cross-role consistency and narrative grounding

**Goal:** make the adjudicator, proposal generator and narrator agree about the same action and committed reality.

**Investigation and delivery:**
- build shared scenario fixtures for mechanics, proposals, application outcomes and narration evidence;
- ensure mechanics prompts receive the necessary relevant world/character facts while preserving their authority boundary;
- ensure world proposals only use confirmed mechanics results when a check was resolved;
- ensure clarification answers resume the original action without becoming separate world facts or actions;
- ensure the narrator receives committed operations/outcomes and relevant context, not uncommitted proposals as facts;
- add continuity scenarios across NPCs, locations, items, clues, relationships, rewards and changed states;
- test that narration cannot invent a successful opening, transfer, injury, relationship or discovery when the committed outcome says otherwise;
- track role-specific model settings and latency; compare models on the same fixed corpus.

**Acceptance criteria:**
- end-to-end local turn scenarios pass from player input through mechanics, proposal, commit and narration;
- narration claims are traceable to committed operations, mechanics evidence or pre-existing world facts;
- repeated generations do not reapply consequences;
- clarification/manual-roll recovery retains the original request identity and outcome;
- failures are diagnosable from correlation IDs and sanitized error categories.

### PR #216 — Benchmark hardening and model selection (conditional)

**Goal:** establish evidence for a default local model and regression policy.

Only proceed when the corpus is large and stable enough to compare models.

- run the same versioned corpus against candidate Ollama models;
- record model digest/tag, Ollama version, sampling parameters, hardware class, duration, token/character counts and per-scenario outcomes;
- compare operation precision/recall, false-positive severity, abstention, retrieval recall, secret leakage and latency;
- run repeated trials and retain raw per-run outcome metadata without storing prompts, private campaign facts or full model responses in CI;
- choose a model on quality/safety/latency trade-offs, not parameter count or one successful example;
- keep the selected model configurable and do not silently change production defaults.

**Acceptance criteria:** published comparison report with reproducible settings and explicit safety failures; no model change based on anecdotal output alone.

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
