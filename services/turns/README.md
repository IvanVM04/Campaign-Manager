# Turn services

## Responsibility

Coordinate the single supported turn lifecycle: player-intent preparation,
mechanics adjudication, durable consequence commit, challenge continuation,
narration completion and recovery.

The durable resolution record is authoritative for in-flight state. Narrative
and transcript versions are a separate presentation projection and must never
replay committed consequences.

**Current implementation boundary:** mechanics adjudication and proposal context
currently use one trusted active-character focus. Product requirements v0.2
aim to support a set of player-controlled characters and explicit NPC control
delegation; those permissions/control-set workflows are future capabilities,
not existing behavior of this package.

## Package modules

- `dm_service.py` — generates presentation prose from committed evidence.
- `turn_execution_lock.py` — canonical process-local lock for short cache snapshot, read-projection and commit critical sections; it must not be held during provider planning or narration.
- `turn_resolution_codec.py` — canonical JSON codec for durable resolution records.
- `intent_interpreter.py` — prompt/provider orchestration and pending-correction interaction for one coherent, evidence-bound `PlayerIntentAnalysis` response; action steps, frames, relations, discourse and attribution remain one semantic unit.
- `intent_normalization_pipeline.py` — deterministic provider-payload normalization, strict versioned model decoding and content-free stage diagnostics. It does not call the provider, resolve canonical IDs or authorize writes.
- `mechanics_adjudicator.py` — consumes only the validated active step and compact mechanical context; returns a `MechanicsDecision` without re-interpreting the utterance. Deterministic rules code rolls dice and applies results.
- `turn_resolution_service.py` — prepares structured proposals from player intent and coordinates retrieval/reference resolution.
- Durable turn collaborators own challenge, clarification, manual-roll, execution, commit, recovery and narration phases.

## Active NLU design decision — 2026-11-20

The production route described below remains the implemented v2 pipeline. The PR #281 live evaluation exposed a gap between field-level scores and complete semantic scenarios, particularly compound-step modality, callbacks, relation direction and the separation of NPC facts from action outcomes. The current architecture target and migration proposal are documented in [the player-intent semantic redesign audit](../../docs/architecture/player-intent-semantic-redesign-audit-2026-11-20.md).

That audit proposes a future versioned contract separating communicative acts, event/proposition frames, discourse links and persistent-fact candidates. Gameplay-action candidates and the active focus would then be derived by backend policy. **This proposal is not implemented by this package yet**: PlayerIntentAnalysis v2, its durable compatibility and the current mechanics/proposal gates remain the runtime contract until the migration is delivered and accepted. Do not describe v3 as an available capability or weaken the existing v1/v2 decoders.

PR #284 hardens the existing v2 boundary without changing its durable schema:
a callback-only first clause is removed only when it is a separately emitted,
literal, anchored preamble; later steps, active-step indices and relation-claim
indices are remapped together. The callback remains discourse context, not an
event. For transfer/creation frames, an ownership/possession/unknown relation
claim that shadows the same action clause is discarded with a content-free
diagnostic. Explicitly recognized relation constructions still take
precedence and preserve their directed endpoints. Relation predicates use
the lexical relation head (for example, `hermana`, not the copular sequence
`es hermana`) to match the semantic-frame gold contract.

Speech predicate morphology is centralized in
`services/discourse/speech_predicates.py`; the intent surface normalizer,
semantic action normalizer and discourse signal extractor consume the same
inventory, including forms such as `advierte/advirtió` and clitic-bearing
constructions. This inventory detects evidence only: it does not assign NPC
identity or grant action authority.

## Modular language-understanding pipeline

The production runtime composes role-specific providers and follows this sequence:

1. `IntentInterpreter.interpret()` receives exact player evidence, bounded same-chat history and a compact visible world context. It returns one coherent `PlayerIntentAnalysis` v2. It does not return a mechanics decision.
2. Literal evidence, schema and canonical references are validated by the existing model/resolvers and deterministic application code.
3. `MechanicsAdjudicator.adjudicate_analysis()` is called only when `analysis.is_actionable` is true, `analysis.requires_clarification` is false and an active character exists. Its input is the validated active step and compact character/world facts; its output schema contains only `MechanicsDecision`. The mechanics context lookup also uses canonical names and literal mentions from references already resolved for that active step, while excluding unrelated resolved references.
4. `LLMWorldExtractor` receives the exact same analysis object, trusted resolved references, bounded projection and confirmed mechanics results. It must not independently reinterpret the raw utterance.
5. Domain services remain the authority for validation, persistence and world mutation. Narration follows committed results.

A question, hypothesis, negation, completed observation or non-actionable report does not trigger mechanics adjudication. A consequence proposal is made only when `analysis.allows_world_proposal` permits it.

At the provider boundary, a structurally valid but contradictory non-action
category with an in-range active-step pointer is normalized conservatively:
the pointer is cleared and a safe warning is emitted. The utterance category,
step content, modality, polarity and evidence are never rewritten. Invalid
indices and invalid categories still fail validation, and direct
`PlayerIntentAnalysis.from_payload()` decoding remains strict. This ensures
a question, plan, dialogue or report cannot accidentally authorize mechanics.

The provider boundary also canonicalizes integer step `index` fields to their
zero-based positions in the existing ordered `steps` array. Array order is
authoritative: step objects are never reordered and no step content is
changed. Non-integer indexes and malformed step structures remain subject to
strict validation. Direct `PlayerIntentAnalysis.from_payload()` decoding
continues to enforce contiguous ordered indexes without normalization.

Step attribution is also grounded only in the current player evidence. An
attribution found solely in history or discourse context is cleared to null at
the provider boundary; the actor, category, action, step order and evidence are
not rewritten. For v2, the attribution must also occur in that step's
source_excerpt. Malformed attribution values and all other evidence fields
remain subject to strict validation. A cleared attribution cannot authorize an
NPC/other world proposal.

The semantic interpretation is deliberately not split into calls for action extraction, argument roles, relations, attribution or discourse. These are interdependent fields in one response contract. The stage boundaries separate responsibilities, not pieces of one meaning representation.

The modular pipeline was introduced/hardened through PRs #225–#226. Subsequent
work added discourse/reference evaluation and correction reliability (#246–#250),
semantic predicate hardening (#253) and the latest compound-intent/discourse
changes (#255). The current delivery record is [player-message comprehension
phase — PR #255](../../docs/quality/player-message-comprehension-phase-2026-11-18.md), with the subsequent live failure baseline in [PR #281](../../docs/quality/live-ollama-evaluation-2026-11-20.md);
older PR documents remain implementation snapshots, not a list of pending work.

### Current state after PR #255 and product v0.2 boundary

PRs #246–#255 extend the discourse/semantic pipeline with visible NPC speaker
signals, topic/callback anchoring, conservative reference coalescing,
explicit-negation handling and per-step compound-intent guidance. PR #255 adds
14 Spanish-first compound held-out cases with gold by step. See the
[current quality roadmap](../../docs/quality/quality-roadmap-2026-11-18.md)
for the live evaluation work still required.

The runtime already has durable clarification and pending-intent correction
continuation. A clarification answer edits the stored pending analysis using
literal evidence and preserves untouched fields. Manual-roll continuation
reuses the persisted analysis. This does not yet implement the broader
product-v0.2 requirement for a user-configurable/calibrated confidence
threshold and a generalized checkpoint that records arbitrary resolved and
unresolved parts of a compound turn. Do not describe that future feature as
implemented.

The durable turn contract is documented in
[turn-resolution-lifecycle.md](../../docs/architecture/turn-resolution-lifecycle.md).

Follow-up hardening and its resumable implementation checkpoint are tracked in [`PR #226 — integrated LLM pipeline hardening`](../../docs/quality/pr-226-integrated-llm-pipeline-hardening.md).

## Semantic compatibility and corrections

V1 durable analyses remain decodable. V2 adds:

- an `action_frame` per intent step, with literal predicate, family and
  role-labelled mentions (agent, patient/theme, recipient, source, destination,
  instrument, location/path, owner/holder/container and other supported roles);
- directed `relation_claims` with subject, object, literal predicate, relation
  family hint, polarity, modality, attribution and temporal expression.

All mentions remain untrusted, ID-free evidence. Canonical identity is resolved
only after campaign, visibility, active-state and ambiguity checks.

The Intent provider is instructed to preserve surface evidence exactly:
predicates retain their written conjugation, mentions retain pronouns and
demonstratives, and each v2 `source_excerpt` is a contiguous player-authored
substring containing the fields it supports. Context may clarify the semantic
`action` description for a unique ellipsis, but history-derived words must not
be copied into literal evidence fields. Strict model validation remains the
enforcement boundary; prompt/schema guidance does not repair an invalid payload.
The prompt/schema rationale and live evaluation evidence are recorded in
[PR #235 — Intent surface evidence prompting](../../docs/quality/pr-235-intent-surface-evidence-prompting.md). The actor-aware distinction between in-world dialogue, questions to the DM and NPC event reports, together with communication-versus-interaction frame guidance, is documented in [PR #236 — Intent speech-act categories](../../docs/quality/pr-236-intent-speech-act-categories.md).

Pending clarifications use `IntentInterpreter.understand_pending()`:
the provider returns only a bounded status and typed slot edits (or a
clarification question), not a reconstructed `intent_analysis`. The backend
applies edits to the stored pending analysis through
`PendingIntentCorrection.apply()`; replacements and excerpts must be literal
in the latest player answer, and every untouched field is preserved. The
application verifies the returned state against deterministic edits before
accepting it. Manual-roll continuation reuses persisted analysis and does not
call the interpreter again.

The old combined `MechanicsAdjudicator.understand()`,
`understand_pending()` and `adjudicate()` APIs remain only as deprecated
compatibility shims for older integrations and compatibility tests.
`TurnResolutionService` exposes the explicit
`allow_legacy_combined_understanding` switch, which defaults to `False`; callers
must opt in to use the fallback. The application composition root also sets it
to `False`, injects a distinct `IntentInterpreter` provider, and routes
mechanics through `adjudicate_analysis()`. New production services must not
enable the combined path. The remaining combined prompt/schema are retained
only until external compatibility consumers have migrated; compatibility
tests opt in explicitly and do not establish the production architecture.

## Prompt budgets and diagnostics

The intent, mechanics and consequence-planner prompts have independent UTF-8
byte budgets: `intent_prompt_max_bytes` / `intent_context_max_bytes`,
`mechanics_prompt_max_bytes` / `mechanics_context_max_bytes`, and
`extraction_prompt_max_bytes` / `extraction_context_max_bytes` /
`extraction_repair_max_bytes`. The shared
`estimate_tokens()` helper counts UTF-8 bytes and is not an exact model
tokenizer. Role logs record prompt bytes, per-section sizes where available,
duration, model and stable error type; they never record the prompt, raw
completion, secrets or full campaign context. Required player evidence is not
silently truncated to fit a prompt.


## Test and evaluation map

- `tests/test_intent_normalization_pipeline.py` protects the deterministic provider-payload boundary, step-index canonicalization, category gating, evidence rejection and safe diagnostics.
- `tests/test_semantic_frames.py` protects v2 frames, relations, evidence and durable recovery.
- `tests/test_player_intent_analysis.py` protects the v1 compatibility contract.
- `tests/test_modular_language_pipeline.py` protects independent schemas, prompt separation, conditional mechanics calls and shared-analysis hand-off.
- `tests/test_mechanics_adjudicator.py` protects the mechanics decision parser and the temporary combined compatibility API.
- `tests/test_pending_intent_correction_flow.py` protects correction parsing, evidence grounding and multi-round durable clarification recovery.
- Live intent evaluation uses `IntentInterpreter`; mechanics and proposal quality are evaluated with their own role-specific probes.
- `tests/test_durable_native_turn.py` and `tests/test_durable_silly_tavern_turn.py` protect the durable lifecycle.
- `tests/test_silly_tavern_context_adapter.py` protects history filtering and adapter behavior.
- `tests/test_discourse_context_builder.py`, `tests/test_conversation_reference_resolver.py` and `tests/test_world_reference_resolver.py` protect topic scope, callbacks, ellipsis cues, NPC attribution, agreement and abstention.
- Live model behavior is evaluated separately by `python -m pytest -m real_llm -v -s`; see the [prompt evaluation guide](../../docs/quality/prompt-evaluation-2026-11-12.md).

## Dependency and lifecycle rules

- Preserve idempotency, lease fencing, campaign revision checks and atomic commit.
- Build proposal context at the turn/application boundary; pass a typed
  `WorldContextProjection` into `services/llm_world`.
- Keep provider calls and narration outside write transactions.
- Narration consumes committed evidence and never applies consequences.
- Clarifications and manual rolls resume the original durable resolution.
- Routers remain transport adapters, not lifecycle authorities.
- Do not reintroduce the removed narrative-first mutation endpoint or snapshot restoration.


## Snapshot isolation and lock scope

Durable execution captures campaign context, recent history and revision under
one DEFERRED read transaction while briefly holding the campaign cache lock.
The returned `TurnContext` and history are deep-detached from the mutable
`WorldService` runtime cache. Intent interpretation, mechanics adjudication,
structured proposals and narration run after the lock and read transaction
have been released.

The prepared-commit boundary reacquires the campaign lock **before** opening
its IMMEDIATE SQLite transaction. It reloads the authoritative context,
rechecks the campaign revision and history, and only then applies operations
and publishes the cache changes. A stale snapshot is rejected rather than
merged. Clarification and manual-roll continuation use the same snapshot and
commit boundaries. Keep the lock-before-SQLite ordering consistent for every
writer to avoid lock inversion.


### Deterministic Intent normalization boundary (PR #267)

`IntentInterpreter` now delegates the provider payload normalization to
`IntentNormalizationPipeline`. The pipeline exposes a typed
`IntentNormalizationResult` (`PlayerIntentAnalysis` plus
`IntentNormalizationDiagnostics`) and keeps the existing normalization order
explicit:

1. canonicalize redundant step array indexes without reordering;
2. sanitize ungrounded optional surface fields;
3. apply bounded, literal player-text normalization;
4. clear attribution that is not grounded in current player text;
5. clear a contradictory active-step pointer for non-action categories;
6. decode the strict v1/v2 semantic contract;
7. apply the narrow explicit NPC speech correction;
8. apply typed semantic surface hints.

The interpreter owns provider lifecycle, correction requests, log events and
workflow orchestration. The pipeline owns deterministic transformation and
returns safe diagnostics; it never logs raw text, prompt/completion content,
secrets or canonical identifiers. The direct model decoder remains strict.
No prompt, provider schema, model-call count, mechanics gate, resolver policy
or world mutation authority is changed by this extraction.

The current architectural target and the next discourse/reference/evaluation
steps are documented in
[Player-language understanding architecture — 2026-11-19](../../docs/architecture/player-language-understanding-architecture-2026-11-19.md).
The full live Ollama/SillyTavern acceptance run is deferred until the listed
structural milestones are integrated; deterministic CI remains mandatory.


### Discourse collaborators (PR #268)

`DiscourseContextBuilder` remains the stable facade consumed by intent
interpretation and reference resolution. Its implementation is decomposed into
`services/discourse/topic_history_selector.py`,
`surface_mention_extractor.py`, `speaker_signal_extractor.py` and
`renderer.py`, with immutable records in `contracts.py`. The split preserves
the existing bounded twelve-turn selection, quote masking, literal source
offsets, NPC visibility/alias checks, ambiguity abstention and byte-bounded
rendered hints. These collaborators do not resolve canonical IDs or authorize
world changes.
