# Turn services

## Responsibility

Coordinate the single supported turn lifecycle: player-intent preparation,
mechanics adjudication, durable consequence commit, challenge continuation,
narration completion and recovery.

The durable resolution record is authoritative for in-flight state. Narrative
and transcript versions are a separate presentation projection and must never
replay committed consequences.

## Package modules

- `dm_service.py` — generates presentation prose from committed evidence.
- `turn_execution_lock.py` — canonical process-local lock shared by turn coordinators.
- `turn_resolution_codec.py` — canonical JSON codec for durable resolution records.
- `mechanics_adjudicator.py` — returns shared language analysis and proposed mechanics decisions; deterministic rules code rolls dice and applies results.
- `turn_resolution_service.py` — prepares structured proposals from player intent and coordinates retrieval/reference resolution.
- Durable turn collaborators own challenge, clarification, manual-roll, execution, commit, recovery and narration phases.

## Shared language-understanding contract

`MechanicsAdjudicator.understand()` returns a `PlayerIntentAnalysis` and a
mechanics decision from one structured provider response. The exact validated
analysis object is reused by `LLMWorldExtractor`; the proposal stage must not
independently reconstruct the same raw utterance.

V1 durable analyses remain decodable. V2 adds:

- an `action_frame` per intent step, with literal predicate, family and
  role-labelled mentions (agent, patient/theme, recipient, source, destination,
  instrument, location/path, owner/holder/container and other supported roles);
- directed `relation_claims` with subject, object, literal predicate, relation
  family hint, polarity, modality, attribution and temporal expression.

All mentions remain untrusted, ID-free evidence. The turn service adds frame
arguments and relation endpoints as supplemental retrieval signals. The
resolver still owns canonical identity; ambiguity and hidden references require
clarification. The model never decides campaign IDs, visibility or permission.

Questions, plans, quotations, negations and resolved outcomes do not trigger
unsupported checks. Compound actions may not skip an earlier unresolved step.
Relation claims preserve reported/question/negative/conditional status and do
not themselves authorize relation writes.

The last twelve visible turns are bounded and scoped to the current
`conversation_id`. PR #223 adds deterministic discourse hints for explicit topic
changes/callbacks, ellipsis, explicit NPC quote labels and local grammatical
agreement. Entity and typed-world reference resolvers share the same topic-scoped
history. Explicit callbacks may inspect the bounded older window but still
require a unique candidate.

PR #219 enriches `ConversationReferenceResolver` with typed candidate evidence,
a distinction between player-authored input and narrator prose, semantic-kind
compatibility and explicit ambiguity margins. PR #223 does not infer
gender/number from proper names; it uses only explicit local article/apposition
(for example, `la guardia Mara`). NPC dialogue is attributed only when the
transcript explicitly labels a unique visible active speaker. Unlabelled
narration remains narrator evidence, and quoted speech is never a player
instruction.

PR #221 connects the guarded `PendingIntentCorrection` primitive to clarification
resumption. Only a still-pending durable resolution with a validated stored
analysis enters correction mode. That mode reuses the clarification's existing
provider call with a correction-only schema; it does not add a provider call to
normal turns. The model must emit an explicit bounded correction record whose
replacement and excerpt are literal in the latest player answer. Application
code checks the previous value, target step, role or directed relation endpoint,
applies the immutable correction against the stored interpretation, and requires
the provider's re-analysis to reflect the same edit. Corrections are recorded in
the durable adjudication history across clarification rounds. They remain
untrusted language evidence and do not resolve canonical IDs, bypass visibility,
or authorize world writes.

Durable resolutions store the conversation and player-authored evidence with
independent SHA-256 fingerprints in `turn_resolutions.intent_json` (migration
033). Conversation identity is persisted on turns/resolutions through
migration 034. The codec supports nested intent schema v1 and v2 without
silently converting old records. Clarification questions remain context only;
manual-roll continuations reuse the saved interpretation.

## Test and evaluation map

- `tests/test_semantic_frames.py` protects v2 frames, relations, evidence and durable recovery.
- `tests/test_player_intent_analysis.py` protects the v1 compatibility contract.
- `tests/test_mechanics_adjudicator.py` protects the combined provider/schema boundary.
- `tests/test_pending_intent_correction_flow.py` protects correction parsing, evidence grounding and multi-round durable clarification recovery.
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
