# Player language understanding — architecture and hardening plan

**Status:** active architecture decision record and implementation plan  
**Verified code baseline:** `main` at `8276450babba6611a172e601d0c76b83ae8e449e` (PR #269 integrated; verified 2026-11-19).  
**Status:** PRs #267–#269 integrated; #270 evaluator work is next.  
**Previous work branch:** `architecture/intent-normalization-boundary-pr267` (historical)  
**Date:** 2026-11-19

This document records the current design for player-language understanding and the sequence of structural changes required before the next full live-model acceptance cycle. It is a source-of-truth design document, not a claim that the target architecture is already fully implemented.

The goal is to make natural-language interpretation more understandable, inspectable, testable and safe without replacing the existing modular monolith or adding unnecessary infrastructure.

## 1. Decision summary

The architecture remains a **single interpretation pipeline with deterministic downstream authority**.

The model returns one structured, versioned interpretation of the player's current message. It can express multiple ordered steps, action frames, directed relation claims, attribution, modality, polarity, reported outcome and literal evidence. The backend validates that interpretation, resolves canonical references conservatively, applies mechanics only to an authorized active step, and remains the only authority for world mutation and persistence.

The following decisions are approved:

1. Preserve one coherent Intent response. Do not split action extraction, actor detection, predicate extraction, relations, argument roles and discourse into separate LLM calls. Their fields depend on one another and must remain jointly interpretable.
2. Keep model output untrusted. Structured output constrains shape; it does not prove semantic truth, evidence grounding, entity identity, permissions or game outcomes.
3. Make every deterministic normalization stage explicit, ordered, independently testable and observable through content-free typed diagnostics.
4. Separate discourse selection, surface mention extraction, speaker signals and conversation-reference resolution into named responsibilities with typed outputs and documented dependency direction.
5. Keep canonical identity, visibility, authorization, mechanics, world consequences and persistence deterministic and server-owned.
6. Prefer abstention and clarification over speculative coreference, guessed group membership, invented attribution or unsupported semantic completion.
7. Do not add more regex rules merely because a live example failed. Each new rule must have a precise linguistic scope, a negative boundary, a deterministic contract test and a held-out case that was not used to tune the rule.
8. Do not introduce microservices, message buses, vector databases, a second semantic memory store, model ensembles or an NLP framework into the production path without measured evidence and an approved dependency decision.
9. Delay the full Ollama/SillyTavern acceptance run until the architecture milestones in this document are integrated. Deterministic contract checks and required CI remain mandatory for every implementation PR; postponing live tests does not mean merging unverified code.
10. Keep old audit documents as immutable historical snapshots. The current documentation hub, current-state map, architecture map, quality roadmap and package guides must point to this document.

## 2. Current implementation baseline

### 2.1 Existing contracts

The current shared contract is `models.player_intent_analysis.PlayerIntentAnalysis`:

- schema version 2 is the current producer target;
- schema version 1 remains supported for historical decoding;
- each v2 step requires an ID-free `SemanticActionFrame`;
- an analysis can contain bounded directed `SemanticRelationClaim` values;
- steps preserve order, actor, modality, polarity, reported outcome and source excerpt;
- the analysis carries a category, active-step pointer and clarification state;
- the model cannot attach canonical entity IDs, authorization grants or world operations.

The v2 semantic object model is deliberately referentially weak. A `SemanticMention` is text plus a coarse kind hint, not an entity lookup result. An argument role such as `recipient`, `source` or `destination` describes the syntax/meaning of the current message; it does not prove that the named object exists or that an operation is allowed.

The model layer is the strict contract boundary. Versioning, field allowlists, bounds, enum validation, evidence grounding, step ordering and cross-field invariants belong there. Do not weaken direct model decoding to make provider output more permissive.

### 2.2 Existing runtime pipeline

The current high-level flow is:

```text
current player message + bounded same-chat transcript + bounded visible context
                                  |
                                  v
                        IntentInterpreter
                                  |
                                  v
                       structured provider output
                                  |
                                  v
                 deterministic normalization boundary
                                  |
                                  v
                    PlayerIntentAnalysis v1/v2
                                  |
                                  v
                deterministic surface-reference extraction
                                  |
                                  v
                  ConversationReferenceResolver
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
             mechanics gate              context/proposal gate
                    |                           |
                    v                           v
          deterministic rules            structured world proposal
                    |                           |
                    +-------------+-------------+
                                  |
                                  v
                  domain validation and atomic commit
                                  |
                                  v
                       post-commit narration
```

This is a conceptual map, not a literal call graph. The actual durable turn coordinator remains the workflow owner. The Intent interpreter must not call mechanics, the world proposal extractor, repositories or world appliers.

### 2.3 Main structural pressure points

The source baseline audited on 2026-11-19 has a set of high-complexity modules:

| Module | Approximate current size | Primary responsibility today |
|---|---:|---|
| `services/turns/intent_interpreter.py` | 1,400 lines before PR #267 | Prompt construction, provider call, response handling, normalization orchestration and correction continuation |
| `services/turns/intent_surface_normalization.py` | 915 lines | Explicit language patterns and payload-level normalization |
| `services/turns/semantic_surface_hints.py` | 1,094 lines | Evidence sanitization and semantic action/relation hints |
| `services/discourse_context.py` | 926 lines | Topic boundaries, callbacks, pronoun/speech cues, history selection and rendering |
| `services/context/conversation_reference_resolver.py` | 955 lines | Candidate extraction, evidence scoring, group resolution, ambiguity and final reference decisions |

The problem is not that a module has crossed an arbitrary line-count threshold. Each file currently owns several different reasons to change. The target is **cohesion and explicit contracts**, not smaller files for their own sake.

There are three distinct kinds of complexity:

- **linguistic interpretation:** what the player said, how clauses relate, what was negated, who performed an action and what the utterance asserts;
- **discourse resolution:** which prior topic or antecedent the current expression refers to, using bounded chat-local history;
- **domain resolution and authority:** which visible canonical entity a mention may refer to, whether the action is allowed and whether mechanics/world state can change.

These must cooperate through typed evidence records, not by sharing mutable dictionaries or letting one stage silently rewrite another stage's authority.

## 3. Trust and authority model

### 3.1 Evidence classes

The pipeline must preserve the distinction between these evidence classes:

| Evidence class | Examples | Permitted use |
|---|---|---|
| Current player-authored text | Current message, literal source excerpts, literal predicates and mentions | Ground the current intention and optional surface references |
| Same-chat prior player text | Recent messages from the same conversation | Resolve bounded discourse references and topic callbacks; never create new current-turn evidence |
| Narrator text | Earlier descriptions or quoted NPC speech | Read-only candidate evidence when the speaker/source is explicitly attributed and visible |
| Visible world projection | Active entities, aliases, current relationships and allowed context facts | Filter and rank canonical candidates within campaign/character visibility |
| Model interpretation | Actor, modality, polarity, predicate, action family, semantic roles and relation claims | Untrusted hypothesis to be validated; never canonical identity or authorization |
| Rules/mechanics results | Server-side rolls, deterministic calculations and validated challenge outcomes | Authoritative mechanical result |
| Committed domain events | Applied world operations and durable turn resolution | Authoritative campaign state and source for narration |

History and narration may help identify a referent; they may not be copied into a current `source_excerpt`, target mention, predicate, attribution or relation claim as if the player had written those words in the latest message.

### 3.2 Non-negotiable invariants

- No LLM output writes to SQLite or calls a repository/world applier.
- No semantic mention or discourse candidate contains a trusted canonical ID unless it is a separately created backend reference result.
- The resolver may only return IDs from the supplied campaign and visibility-filtered world.
- Ambiguous, hidden, inactive or unsupported references abstain.
- A plural pronoun must never collapse to the highest-scoring individual.
- A model-supplied confidence number is not a calibrated probability and must not authorize an action.
- A question, plan, negation, report, observation or unresolved earlier step cannot become mechanically actionable through normalization.
- A failed/uncertain attempt must not become a confirmed world fact.
- Clarification and normalization must not mutate campaign state.
- Mechanics are gated by the validated active step; the LLM does not roll dice or assert the outcome.
- Proposal validation, domain authority, campaign revision checks and atomic commit remain downstream.
- Narration occurs after the commit and cannot replay consequences.

## 4. Responsibilities and module boundaries

### 4.1 Intent orchestration

**Owner:** `services.turns.intent_interpreter.IntentInterpreter`

Responsibilities:

- validate public method arguments;
- assemble bounded prompt sections from typed context;
- call the configured provider once for the coherent intent schema;
- handle provider failures and top-level response envelope errors;
- invoke the deterministic normalization boundary;
- translate typed diagnostics into allowlisted structured logs;
- own the separate pending-correction interaction for the existing durable clarification workflow.

It must not contain the implementation of every linguistic repair rule. It must not resolve canonical references or decide mechanics.

### 4.2 Intent normalization pipeline

**Owner:** `services.turns.intent_normalization_pipeline.IntentNormalizationPipeline`

**Introduced by PR #267.**

This component receives a decoded, untrusted provider payload and exact current player evidence. It returns a `PlayerIntentAnalysis` plus typed, content-free diagnostics.

The stage ordering is explicit and is part of the implementation contract:

1. Canonicalize redundant step indices to their array positions. Do not reorder steps. Invalid structures remain invalid.
2. Sanitize only optional surface fields that are not grounded, using the existing semantic-surface sanitizer.
3. Apply narrowly scoped, literal utterance constructions from `intent_surface_normalization`.
4. Clear optional speaker attribution that is not grounded in current player evidence. Do not infer attribution from prior history.
5. Remove an in-range active-step pointer from non-action categories without changing category, evidence or step content.
6. Decode through the strict, versioned `PlayerIntentAnalysis.from_payload()` boundary.
7. Apply the narrow, directly evidenced NPC speech-act normalization already supported by the discourse signals.
8. Apply typed semantic surface hints for supported action frames and directed relations.

The exact order matters. For example, ungrounded optional attribution is cleared before the strict model decoder, but malformed attribution types remain rejected. The speech-act conversion happens after strict decoding and only for the supported positive NPC speech pattern. Semantic hints are applied after the validated model exists.

The pipeline does not:

- call a provider;
- inspect arbitrary chat history to create current-message evidence;
- resolve or assign canonical entity IDs;
- assign campaign visibility or permissions;
- decide whether a roll is required;
- construct world operations;
- write state or persistence.

The diagnostics are limited to fixed rule IDs, indices, counts and safe categories. They must never contain player text, source excerpts, raw completion values, canonical IDs or secret campaign state.

### 4.3 Payload-level semantic sanitization

**Owner:** `services/turns/semantic_surface_hints.py`

Responsibilities:

- remove optional mentions, action arguments and relation claims that cannot be grounded in the exact current utterance;
- preserve v1/v2 schema meaning and strict model validation;
- apply bounded semantic type/family hints only when a supported literal construction exists;
- keep summary diagnostics independent of raw language.

This module must not become a second entity resolver. Its outputs remain semantic mentions, not `Entity` records.

### 4.4 Explicit utterance normalization

**Owner:** `services/turns/intent_surface_normalization.py`

Responsibilities:

- recognize high-precision, literal surface patterns such as explicit negation, refusal, correction, conditional construction or stated outcome where the current corpus demonstrates a stable pattern;
- preserve clause order and avoid treating quoted text as the player's own action;
- identify its own named rule IDs and expose a content-free summary.

Each rule must have:

- a narrow positive pattern;
- a negative/near-miss example;
- a clear scope boundary (quote, negation, condition, attribution, independent clause);
- a deterministic unit test;
- a labelled held-out evaluation case when it is expected to improve model behaviour;
- a documented security effect, especially whether it can affect active-step selection or proposal eligibility.

Do not add broad catch-all rules or use a normalization to force an expected benchmark result.

### 4.5 Discourse selection and surface cues

**Current owner:** `services.discourse_context.DiscourseContextBuilder`

The current class handles several distinct responsibilities:

- explicit topic-shift detection;
- callback reactivation and anchor selection;
- history segmentation and bounded selection;
- pronoun/demonstrative surface spans;
- speech predicate and visible speaker cues;
- attributed NPC utterance extraction;
- prompt-hint rendering.

Its typed output records (`DiscourseSelection`, `SurfacePronounMention`, `SpeechPredicateSignal`, `AttributedNpcUtterance`) are a useful foundation. The next architecture increment should make those records the public seams between cohesive collaborators without changing caller semantics.

Target responsibilities after the follow-up extraction:

| Collaborator | Responsibility | Must not do |
|---|---|---|
| Topic/history selector | Segment and select bounded same-chat turns; expose reason, anchors and ambiguity | Resolve entity IDs or rewrite current evidence |
| Surface mention extractor | Find literal current-message pronoun/clitic/demonstrative spans and grammatical hints | Select a referent |
| Speech/speaker signal extractor | Detect literal unquoted speech predicates and narrowly attributable visible speaker cues | Turn a hint into canonical identity or permission |
| Discourse hint renderer | Render bounded, privacy-safe, explicitly labelled context hints | Add evidence words or entity facts to the player's message |

Keep `DiscourseContextBuilder` temporarily as a compatibility facade during extraction. Do not duplicate the same logic in two independent production paths. Each extracted component needs a single owner and direct contract tests.

### 4.6 Conversation reference resolution

**Owner:** `services.context.conversation_reference_resolver.ConversationReferenceResolver`

This is an application/context resolver, not a linguistic parser. Its job is to map backend-generated surface mentions to visible candidate entities using typed evidence.

Responsibilities:

- accept a validated `PlayerIntentAnalysis`, current input and history already scoped to the current conversation;
- gather independent literal current-turn mentions in addition to model-emitted mentions/arguments/relations;
- preserve whether a candidate originated in player input or narrator prose;
- filter candidates by active status, campaign, entity kind and visibility;
- score only evidence produced by trusted application code;
- apply explicit score/margin thresholds and group-resolution rules;
- return an auditable reference result or a typed abstention/clarification.

Independent mention extraction already exists for a bounded subset of subject pronouns and dative clitics. The remaining gap is coverage and contract breadth, not complete absence of independent extraction. Other mention types still depend partly on model-emitted semantic fields.

The resolver must not:
- change actor, modality, polarity or predicate;
- create evidence that is not present;
- infer a unique group from individually plausible members;
- treat narrator prose as player intent;
- resolve a hidden or inactive entity;
- return a singular reference when two candidates remain within the ambiguity margin.

### 4.7 Canonical model and authority layers

| Layer | Owner | What it owns |
|---|---|---|
| Semantic model | `models/player_intent_analysis.py`, `models/semantic_frames.py` | Versioned, ID-free interpretation contract and invariants |
| Discourse evidence | `models/discourse_evidence.py` | Provenance, source kind, turn scope, candidate signal evidence |
| Resolved references | `models/resolved_conversation_reference.py` and world reference records | Canonical, visibility-checked IDs produced by deterministic code |
| Mechanics | `MechanicsAdjudicator` and `rules_engine/dnd5e_2014` | Whether a validated action requires mechanics and deterministic roll/result |
| Consequence planning | `services.llm_world` | Untrusted structured proposal from validated evidence and bounded world projection |
| Domain validation/application | `services.world` and domain services | Permissions, operation schema, current state, revision and resource constraints |
| Durable turn lifecycle | `services.turns` durable collaborators | Idempotency, clarification, manual roll, commit, retry and narration recovery |

## 5. Data contracts between stages

### 5.1 Model interpretation is not resolution

The provider returns one structured envelope with `intent_analysis`. Keep the schema exact and bounded. The structured-output provider contract is already implemented for Ollama. Do not add another wrapper or "JSON repair" layer without a demonstrated failure mode.

The v2 step is an ordered proposition about the current utterance, not necessarily a world operation. It can be a player attempt, dialogue, observation, report, question, plan, correction, negation or other supported modality.

The model response does not establish truth. `reported_outcome` is player-reported status, not a dice result. A report attributed to an NPC does not become current world state until the existing world/proposal/application contract permits a separately validated consequence.

### 5.2 Surface mentions and canonical references

A surface mention should carry only the minimum evidence needed for later resolution:

- literal text;
- exact start/end character offsets when available;
- grammatical gender/number only when supported by local syntax;
- semantic kind hint if available;
- source class (current player text, prior player text or narrator text);
- originating turn ID where applicable.

A resolved reference is a different type. It should retain the original mention/evidence and record:

- chosen entity ID or group members;
- source evidence IDs/turns;
- candidate count;
- resolution status and match kind;
- bounded score/margin diagnostics;
- an explicit reason when resolution abstains.

Do not merge the two contracts into one object that can be populated by an LLM.

### 5.3 Normalization summaries

Normalization diagnostics should be stable machine-readable values, not strings scraped from logs. A summary may contain:

- ordered rule identifiers;
- changed field paths or step indexes;
- dropped optional candidate counts;
- cleared attribution indexes;
- category-safe normalization events.

It must not contain full input/output payloads or text fragments. A future evaluation ledger may consume these diagnostics without logging them as user data.

### 5.4 Versioning policy

- Do not reinterpret schema v1.
- Keep historical v1 decoding tests.
- Evolve v2 additively only where the semantics remain unambiguous; otherwise introduce a new schema version.
- Every new enum value, field, role, relation family or modality needs a compatibility decision.
- A provider output that exceeds bounds or violates the versioned contract is rejected or subjected to a specifically documented conservative normalization; never silently coerce arbitrary values.
- Durable turn records store the schema version they were created with. Replaying a turn must decode using the supported historical contract, not reinterpret against current prompt text.

## 6. Complexity and maintainability policy

### 6.1 What justifies extraction

Extract a collaborator when at least one of these is true:

- it has a distinct input/output contract;
- it changes for a different reason than its current parent;
- it has a meaningful deterministic test surface;
- it owns a policy decision that must be auditable;
- it makes dependency direction difficult to inspect.

Do not extract a collaborator just to split a long file into many tiny files, move a private helper without ownership change, or introduce generic frameworks for hypothetical reuse.

### 6.2 What counts as complexity evidence

Track more than line count:

- public and private method count;
- imports and dependency direction;
- number of unrelated responsibilities;
- number of regex/pattern families and their negative tests;
- mutable shared state and dictionary-based contracts;
- duplicate normalization paths;
- number of callers and compatibility shims;
- branch coverage on authorization-sensitive decisions;
- evaluation misses/false positives by linguistic family;
- prompt bytes, provider latency and normalization rule frequency where safe.

Line count is a warning signal only. A 900-line module with one cohesive responsibility can be healthier than five 100-line files that call each other cyclically.

### 6.3 Pattern-rule governance

Regex remains an acceptable tool for explicit surface forms. It is not a complete syntax parser, general coreference engine or discourse model.

Before a new production rule is added, record:

1. rule ID and linguistic phenomenon;
2. locale/variety and exact grammatical scope;
3. positive cases;
4. nearby negative cases;
5. quote/negation/condition/attribution/topic boundary behaviour;
6. which contract fields it may modify;
7. why it is deterministic enough to repair model output;
8. unit tests and held-out evaluation coverage;
9. expected false-positive cost and abstention behaviour.

Prefer a parser or model feature over expanding hand-maintained morphology indefinitely, but require a measured pilot before making an NLP library a production dependency.

## 7. Evaluation architecture (fix before tuning)

The evaluation system is part of the language architecture. A weak scorer can make the model appear better than it is and lead to harmful rules. Therefore #270 (evaluation contract) precedes #271 (optional NLP pilot); do not compare parser/model variants with incomplete scoring.

### 7.1 Required scoring dimensions

For each scenario, the scorer must compare the complete result against independent gold:

- global category;
- exact step count (missing steps and extra steps are separate errors);
- active-step index and clarification state;
- actor, modality, polarity and reported outcome for every step;
- predicate and action family where gold is specified;
- argument-role/mention pairs;
- relation claim count, direction, family, polarity, modality, attribution and temporal field;
- attribution and source evidence grounding;
- resolved reference identity, precision/recall and abstention reason;
- unauthorized or false persistent world proposals;
- secret/hidden entity leakage.

For a field with no gold, the evaluator should not imply that the field is correct. It should still measure grounded extra predictions where the contract defines enough structure to do so.

### 7.2 Known evaluator gap from the 2026-11-19 audit

The general language holdout scorer currently checks selected fields of the first/later step but does not consistently enforce exact step count or account for all extra semantic claims. The compound sidecar has independent per-step actor/modality/polarity gold, but does not yet cover full predicates, frame families, role-labelled arguments, outcomes and attribution. Predicate/frame scoring exists in separate evaluation paths and must be consolidated or cross-referenced with explicit denominator definitions.

This is a tooling weakness, not evidence that the language model passed. It must be fixed before using full live results to guide prompt/rule tuning.

### 7.3 Metric definitions

Use explicit denominators and publish both micro and per-family measures:

- exact case accuracy;
- step-count accuracy;
- per-step slot accuracy and recall;
- slot precision/recall/F1 (TP/FP/FN);
- predicate exact match and normalized match, kept separate;
- argument-role precision/recall/F1;
- relation direction accuracy and relation-family F1;
- reference resolution precision/recall and ambiguity abstention rate;
- critical false-positive rate;
- false persistent change and secret leak counts;
- parse/validation failure rate;
- latency P50/P95 and calls per turn.

Do not collapse all of these into one score. Zero critical false writes and zero secret leaks are hard safety gates, not tradeable parts of a weighted metric.

### 7.4 Dataset separation

- Development examples may guide prompt wording and rule design.
- Held-out examples must not appear in prompts, few-shot examples or rule-specific tuning.
- Critical cases should be repeated in live diagnostics to expose nondeterminism.
- Keep exact input text out of telemetry and aggregate reports unless local-only artefacts have an explicit privacy decision.
- A model/configuration comparison requires pinned model digest, Ollama version, sampling/generation settings, system prompt revision, timeout, context budget and hardware notes.

## 8. NLP library decision

No Stanza/spaCy dependency is introduced by PR #267.

The candidate architecture for a future NLP adapter is:

```text
surface text
    |
    v
optional NLP adapter (token spans, POS, lemma, dependency arcs)
    |
    v
typed linguistic hints with source offsets
    |
    v
existing intent/discourse contracts
    |
    v
deterministic validation and reference/authority layers
```

If piloted, NLP output remains a hint. It cannot assign canonical IDs, decide permission or override literal source spans.

A pilot must compare at least:

- current deterministic extraction baseline;
- parser-only output;
- current model interpretation;
- model plus parser hints.

Measure Spanish-first D&D examples, quoted speech, clitics, negation, conditionals, ellipsis, names, aliases, invented fantasy vocabulary, latency and memory. Include English only to the extent it is in the product-supported corpus. Assess licensing, packaging, offline installation size and CPU cost. Promote no library into the production dependency set until it demonstrates a measurable net benefit and its model/runtime implications are accepted.

## 9. Sequenced implementation roadmap

The PR order is dependency-driven. Each PR should be substantial and focused, with approximately 1,000+ changed lines when that scope warrants it; do not pad a PR with unrelated changes merely to reach a line count. Keep one active branch/PR at a time, always from the latest integrated `main`.

| PR | Objective | Main architectural output | Depends on |
|---|---|---|---|
| #267 | Establish the intent-normalization boundary | `IntentNormalizationPipeline`, typed diagnostics, deterministic boundary tests and this architecture decision | Existing #266 baseline |
| #268 | Decompose discourse responsibilities | Topic/history selector, surface mention extractor, speaker signal extractor and renderer behind the existing facade | #267 (integrated) |
| #269 | Formalize conversation-reference evidence | Typed extraction bundle, candidate ranking/abstention contracts, clearer provenance and bounded group rules | #268 |
| #270 | Complete semantic evaluation contracts | Full per-step gold, exact step-count and extra-step/extra-slot FP counting, frame/argument/relation/attribution scoring and stable metric schema | #267–#269 |
| #271 | Run optional NLP-library pilot | Offline adapter spike and comparison using the corrected scorer; decide from measured Spanish-corpus quality, latency, CPU, packaging and licensing whether any production dependency is justified | #270 |
| #272 | Introduce calibrated uncertainty/checkpoints | Evidence-quality features, calibrated abstention policy and durable dependent-slot checkpoints; no self-reported confidence shortcut | #271 |
| #273 | Perform the consolidated live-model and client acceptance cycle | Pinned Ollama/model benchmark, repeated critical holdouts and manual SillyTavern workflow acceptance | #267–#272 |

PR #267 deliberately starts by making the existing normalization sequence explicit. It does not rewrite the semantic grammar or claim live improvement.

## 10. Acceptance gates before the next full live run

The full Ollama holdout suite is deferred until PRs #267–#272 have been integrated and their deterministic contracts are stable.

Required before that live run:

- normalizer stages are explicit, independently callable and covered by tests;
- discourse collaborators have typed input/output contracts and the existing public facade remains compatible;
- reference candidate evidence is auditable and provenance-preserving;
- no stage grants canonical identity, visibility or world-write authority to model output;
- the evaluator counts missing and extra steps/slots and publishes explicit TP/FP/FN denominators;
- development and held-out corpora remain separated;
- prompt revision, model digest, Ollama version and generation settings can be recorded;
- full deterministic CI passes on the integrated architecture.

Required live acceptance once the gate opens:

- repeat every critical scenario three times;
- all critical cases meet the agreed per-step gold exactly;
- non-critical step/slot precision and recall meet the roadmap targets;
- zero false persistent changes and zero secret leaks;
- reference precision and ambiguity abstention meet their hard thresholds;
- semantic frame and relation metrics meet the target separately by family;
- failures and latency are reported by model role and family;
- manual SillyTavern checks cover chat isolation, topic/callback changes, clarification, manual rolls, retries, restart/recovery and narration replay safety.

A live run that does not pass is diagnostic evidence, not an acceptance pass. Do not weaken gold or alter denominators to turn red results green.

## 11. PR #267 scope and explicit non-goals

### Included

- New `IntentNormalizationPipeline` boundary.
- Immutable normalization result/diagnostic records.
- Extraction of existing normalization logic without intentionally changing its rules.
- Integration from `IntentInterpreter`.
- Deterministic tests for ordered normalization, category gating, invalid index handling, evidence rejection and content-free diagnostics.
- Current documentation and roadmap alignment.
- No model call count or schema change.

### Not included

- New linguistic regex rules or prompt tuning.
- Model/provider replacement or model benchmark.
- Stanza/spaCy production dependency.
- General coreference or unrestricted semantic parsing.
- New database schema or migration.
- Changes to mechanics, operation proposals, permissions, visibility, world writes or durable turn sequencing.
- Live Ollama execution or manual SillyTavern acceptance.

## 12. Change checklist for future NLU PRs

Before implementation:

- [ ] Read this design and the current quality roadmap.
- [ ] Identify the exact semantic/discourse phenomenon and the owning layer.
- [ ] State the before/after contract and dependency direction.
- [ ] Check existing fixtures and holdouts to avoid duplicates.
- [ ] Record positive, negative and ambiguity/abstention cases.
- [ ] Identify all consumers and persisted schema implications.

During implementation:

- [ ] Keep raw provider payload separate from validated domain models.
- [ ] Preserve exact current-message evidence boundaries.
- [ ] Prefer frozen typed result records over shared mutable dictionaries.
- [ ] Keep model-derived hints separate from backend-derived evidence.
- [ ] Keep canonical IDs out of model schemas and prompt instructions.
- [ ] Emit safe diagnostics with fixed keys only.
- [ ] Preserve v1 decoding and durable replay semantics.
- [ ] Do not weaken mechanics or world-proposal gates.

Before PR creation:

- [ ] Add focused deterministic contract tests.
- [ ] Run the applicable deterministic test selection locally when available.
- [ ] Let required repository CI validate the complete non-live suite.
- [ ] Run Ruff and required Pyright scopes.
- [ ] Inspect imports and package dependency direction.
- [ ] Update package guides and current architecture maps.
- [ ] State clearly that live provider/client tests were not run when they were not run.

## 13. Decision history

- 2026-11-19: formalized the staged architecture and deferred the next full Ollama/SillyTavern validation cycle until the structural and evaluator milestones are integrated.
- 2026-11-19: extracted the first deterministic normalization boundary in PR #267 while preserving one structured Intent call and the existing versioned semantic contract.
- Historical work: PRs #255, #263, #265 and #266 strengthened discourse continuity, semantic frames, compound actions, polarity/attribution and action gating. Their implementation records remain historical delivery evidence; they do not replace the architecture and acceptance gates in this document.


### PR #268 delivery note — discourse ownership split

PR #268 extracts four typed collaborators behind the existing
`DiscourseContextBuilder` facade:

- `DiscourseTopicHistorySelector` owns topic segmentation, explicit shifts,
  callback anchors, candidate scores, tie/abstention diagnostics and the
  twelve-turn history bound.
- `SurfaceMentionExtractor` owns literal pronoun/dative-clitic spans and
  local grammatical agreement features.
- `SpeakerSignalExtractor` owns speech-predicate cues, visible/active NPC
  alias eligibility, quote attribution and ambiguity-safe speaker hints.
- `DiscourseContextRenderer` composes those outputs into the existing bounded
  prompt hints; it has no authority to create evidence or canonical identity.

Immutable records live in `services/discourse/contracts.py`, and the
facade's existing import path and methods remain available to current callers.
No regex vocabulary, prompt instruction, model schema, resolver score,
visibility rule, mechanics gate or write authority is changed by this split.


### PR #269 delivery note — conversation-reference evidence boundary

PR #269 extracts the conversation resolver's evidence and ranking policies
behind two deterministic collaborators:

- `ConversationReferenceEvidenceExtractor` produces a bounded immutable
  `DiscourseEvidenceBundle`. Current-step mentions retain extraction origin,
  semantic kind hint and available source offsets; antecedent occurrences retain
  turn ID, player/narrator/NPC speaker, source and literal offsets. Only entities
  in the caller-supplied active/visible world projection can receive evidence.
- `ConversationReferenceCandidateRanker` owns semantic-kind filtering, evidence
  scoring, stable ordering, the existing minimum score/margin thresholds and a
  typed decision (`resolved`, `no_candidates`, `below_minimum_score` or
  `ambiguous_margin`). Same-turn plural groups remain capped at 2–8 members
  and require co-mention with matching source and speaker provenance.
- `ConversationReferenceResolver` remains the orchestration facade and the
  only component in this path that emits canonical resolved references. Its
  result now exposes ranking diagnostics without granting write authority.

The PR preserves the existing score weights and threshold values; it makes the
inputs, provenance and final abstention decision inspectable. The typed bundle
is ephemeral application output, not persisted campaign state. It does not add
general coreference, prompt-side identity claims, a new provider call, or a
bypass around entity visibility, mechanics validation or write authorization.

The same PR adds `scripts/run-ollama-tests.ps1` for repeatable Windows local
validation. It refuses dirty worktrees, fast-forwards `main`, supports local
`.env.ollama` configuration, checks Ollama/model availability, executes the
existing `real_llm` marker and writes JUnit plus content-free Markdown/JSON
statistics. This is a convenience runner, not evidence that Ollama tests have
already been run or that the full #273 acceptance gate has passed.
