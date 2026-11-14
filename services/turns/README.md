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
- `intent_interpreter.py` — one coherent, evidence-bound `PlayerIntentAnalysis` v2 response; action steps, frames, relations, discourse and attribution remain one semantic unit.
- `mechanics_adjudicator.py` — consumes only the validated active step and compact mechanical context; returns a `MechanicsDecision` without re-interpreting the utterance. Deterministic rules code rolls dice and applies results.
- `turn_resolution_service.py` — prepares structured proposals from player intent and coordinates retrieval/reference resolution.
- Durable turn collaborators own challenge, clarification, manual-roll, execution, commit, recovery and narration phases.

## Modular language-understanding pipeline

The production runtime composes role-specific providers and follows this sequence:

1. `IntentInterpreter.interpret()` receives exact player evidence, bounded same-chat history and a compact visible world context. It returns one coherent `PlayerIntentAnalysis` v2. It does not return a mechanics decision.
2. Literal evidence, schema and canonical references are validated by the existing model/resolvers and deterministic application code.
3. `MechanicsAdjudicator.adjudicate_analysis()` is called only when `analysis.is_actionable` is true, `analysis.requires_clarification` is false and an active character exists. Its input is the validated active step and compact character/world facts; its output schema contains only `MechanicsDecision`. The mechanics context lookup also uses canonical names and literal mentions from references already resolved for that active step, while excluding unrelated resolved references.
4. `LLMWorldExtractor` receives the exact same analysis object, trusted resolved references, bounded projection and confirmed mechanics results. It must not independently reinterpret the raw utterance.
5. Domain services remain the authority for validation, persistence and world mutation. Narration follows committed results.

A question, hypothesis, negation, completed observation or non-actionable report does not trigger mechanics adjudication. A consequence proposal is made only when `analysis.allows_world_proposal` permits it.

The semantic interpretation is deliberately not split into calls for action extraction, argument roles, relations, attribution or discourse. These are interdependent fields in one response contract. The stage boundaries separate responsibilities, not pieces of one meaning representation.

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

Pending clarifications use `IntentInterpreter.understand_pending()`: the prior
analysis is a non-authoritative draft, replacements must be literal in the
latest player answer, corrections are immutable and bounded, and the
provider's re-analysis must reflect the same edit. Manual-roll continuation
reuses persisted analysis and does not call the interpreter again.

The old combined `MechanicsAdjudicator.understand()` API remains temporarily
as a compatibility path for older callers and deterministic legacy tests. The
application runtime injects `IntentInterpreter` and uses only
`adjudicate_analysis()`; new production code must not use the combined path.

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
