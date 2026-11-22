# V3 world facts in the durable turn commit — 2026-11-22

## Status and safety boundary

PR #298 connects the existing deterministic `world_fact_policy` to the durable
turn preparation/commit lifecycle. It does not make the v3 interpreter or the
v3 action selector authoritative for player-facing actions.

Two separate flags are required:

- `CAMPAIGN_MANAGER_PLAYER_TURN_V3_ACTION_SHADOW_ENABLED=true`
  constructs the opt-in v3 preview service.
- `CAMPAIGN_MANAGER_PLAYER_TURN_V3_WORLD_FACTS_ENABLED=true`
  enables fact evaluation and persistence. It is rejected unless the action
  shadow flag is also true.

Both flags default to false. Enabling action shadow alone continues to create
only an action checkpoint; it cannot produce world-fact operations.

The v2 plan remains authoritative for mechanics, narration, and the existing
world-proposal route. V3 facts are an additive, independently gated source of
typed world operations. They do not execute a candidate action, adjudicate a
roll, infer a successful outcome, create entities, or write outside the normal
durable turn commit boundary.

## Evaluation pipeline

1. The opt-in preview obtains one holistic v3 interpretation using the shared
   prompt, schema and evidence-span aligner. It does not make a separate LLM
   call per fact.
2. Fact subject/object mentions are added to the bounded context projection
   queries. Resolution is performed against that projection only, using the
   deterministic entity resolver. An endpoint is trusted only when the resolver
   returns exactly one active visible entity; unresolved and ambiguous
   endpoints remain unresolved. The model never supplies canonical IDs.
3. `evaluate_world_facts()` evaluates every candidate independently and in
   source order. Its existing policy rejects non-player assertions, quoted or
   attributed claims, non-persistent epistemic states, negative/uncertain
   polarity, temporary/unknown scope, invalid endpoints, unsupported relation
   families and ownership inferred from a transfer.
4. Each decision becomes a `FactValidationReceipt` bound to the canonical
   candidate JSON and its SHA-256 digest. The receipt states PENDING,
   VALIDATED or REJECTED; VALIDATED means the policy accepted/already
   represented the candidate, not that a database write has committed.
5. Only ACCEPTED decisions contribute typed `WorldOperation` instances.
   ALREADY_PRESENT, NEEDS_CLARIFICATION and REJECTED decisions never emit a
   write operation. The receipts for all decisions remain attached to the
   action checkpoint, including pending and rejected cases.

## Durable write boundary

The durable planning service prepares the existing v2 plan first. On the
normal prepared path, and only when both flags are enabled, it then builds
the optional v3 preview and appends accepted fact operations to the v2
operation list. It does not use action-node selection or a mechanics result as
a condition for evaluating an independently evidenced fact.

The prepared proposal and the v3 checkpoint (including fact receipts) are
persisted in one `IMMEDIATE` SQLite transaction:

- save the checkpoint through `TurnResolutionRepository.save_action_checkpoint`
  under the current planning lease;
- compare-and-swap the expected lifecycle state, lease token, context
  revision and previous checkpoint;
- transition the same resolution from planning to prepared with the proposal
  containing the exact operations that will later be applied.

There can be no committed v3 fact operation without its corresponding durable
receipt. If the optional checkpoint/receipt CAS or storage step fails, the
transaction is rolled back and the service falls back to preparing the
authoritative v2-only proposal. The optional preview failure therefore does
not create a partial checkpoint or an unreceipted fact write.

Accepted fact operations go through the existing
`DurableTurnPreparedCommitService` → `TurnResolutionService.apply_plan()` →
`WorldService.apply_turn_operations()` path. Existing campaign revision,
context snapshot, atomic operation batch, and transaction checks remain in
force. A failed world-operation application still rolls back the complete
prepared operation batch; fact eligibility is independent of mechanics
outcomes, not independent of the commit's atomicity guarantees.

## Mechanics independence

With the world-facts flag enabled, a `MechanicsAdjudicatorError` is treated as
a failed mechanics stage for this preparation: it produces a content-free
diagnostic and a NONE mechanics decision, allowing the independent v3 fact
policy to run. A deterministic failed roll is not rewritten or treated as
evidence against a separate fact; its original mechanics result remains on
the plan while fact operations are appended independently.

This exception is opt-in and does not change the default v2 path. It does not
turn provider failure into a successful check and never gives the LLM authority
to decide success, failure, damage, or other mechanical outcomes.

## Idempotency and recovery

The checkpoint, its receipts and the prepared proposal are committed
atomically. Once the resolution reaches prepared, retries use the persisted
proposal through `TurnResolutionCodec.plan_from_record()`; they do not call
the v3 preview again or regenerate fact IDs/operations. The normal prepared
commit boundary checks the stored context revision and current context before
applying the stored operation batch.

An action-only checkpoint already persisted by an earlier PR #297 worker is
not regenerated. Such a checkpoint has no fact receipts, so the new code
abstains from adding facts on that retry rather than creating a different
interpretation or graph identity.

## Deliberate non-goals

- No change to v1/v2 historical intent codecs or durable replay behavior.
- No v3 action execution, callbacks, successor selection or compound turn
  continuation; these remain PR #299.
- No fact processing while the existing preparation path returns early for a
  manual-roll or clarification challenge; resumable mixed fact/action
  continuations belong to PR #299.
- No new database column or migration; the existing
  `action_checkpoint_json` field carries the versioned receipt collection.
- No live Ollama or manual SillyTavern acceptance claim. PR #300 owns the
  end-to-end acceptance run and the v2/v3 rollout decision.

## Deterministic verification

The PR adds coverage for:
- independent feature-flag defaults, validation and runtime composition;
- uniquely resolved fact endpoints producing one typed operation and a
  VALIDATED receipt;
- unresolved endpoints producing a PENDING receipt and no operation;
- action-shadow-only mode leaving fact persistence disabled;
- fact operations remaining in the plan when its mechanics result records a
  failed check;
- prepared proposal reconstruction preserving typed v3 fact operations
  without invoking the v3 model again.

CI results are pending until the PR head has completed all required workflows.
