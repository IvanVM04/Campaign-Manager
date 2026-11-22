# Player action selection and partial checkpoint — 2026-11-20

## Status and boundary

PR #287 implements the backend action-selection and durable partial-progress
building blocks from the [2026-11-20 semantic redesign audit](player-intent-semantic-redesign-audit-2026-11-20.md).
It follows the additive v3 DTO/decoder in PR #285 and the isolated shadow prompt
in PR #286.

**PR #287 did not activate v3.** PR #297 adds an explicitly opt-in,
non-authoritative preview caller in the durable planning route. With the flag
disabled, the v1/v2 path is unchanged. With it enabled, v3 can build one action
focus and persist the backend checkpoint under the existing lease/CAS boundary;
the v2 plan still controls mechanics, proposals and commit. The checkpoint
column remains nullable for existing/historical resolutions.

## Backend authority model

The selector in `services/turns/player_action_selector.py` consumes a strict
`TurnInterpretationV3` and trusted reference-resolution results. It does not
call a model, resolve names to IDs, make dice decisions or write world state.

The model-provided fields remain evidence only. The backend:

- requires an event's source act to be player-authored and refuses quoted
  instructions/reports as action authority;
- requires exactly one agent mention and a canonical entity reference supplied
  by the existing trusted resolver that matches the current controlled
  character ID;
- resolves all explicit target mentions or pauses for clarification;
- rejects negation, non-asserted/unproven attempts and unsupported action
  families; only attempted events enter normal action selection;
- permits a planned event only when a `condition_on_success` discourse link
  explicitly identifies its prerequisite.

For `condition_on_success`, the link's source is the dependent event and its
target is the prerequisite event. The prerequisite must precede the dependent
event and both must exist in the derived graph. Missing, forward, duplicate or
otherwise inconsistent dependencies fail closed. A conditional successor is
eligible only after every prerequisite is authoritatively resolved as
`SUCCESS`. A rules-engine `FAILURE` skips the dependent branch; an
infrastructure failure does not count as a gameplay failure and therefore
does not unlock or skip successors. The next independent action may then be
selected.

At most one action is returned from `select_next_action`. Later independent
events stay pending until the caller completes or pauses the selected node.
This is a selector/checkpoint contract, not a multi-action commit transaction.

## Checkpoint contract

`models/player_action_checkpoint.py` defines schema version 1. A checkpoint
is bounded to 12 action nodes and 128 KiB and is bound to:

- a durable `resolution_id`;
- the campaign `context_revision`;
- SHA-256 of the exact durable player input;
- SHA-256 of the canonical v3 interpretation JSON.

Each node stores the backend-derived `GameplayActionCandidate`, source order,
state, deterministic execution key, attempt count, optional authoritative
outcome and bounded clarification slot names. The codec rejects unknown
fields, unsupported versions, invalid enums, duplicate IDs, missing/forward
dependencies, cycles and invalid state/outcome combinations.

The checkpoint also carries backend-only `FactValidationReceipt` records:
fact local ID, source act ID, canonical candidate JSON snapshot, SHA-256 of the
exact `WorldFactCandidate`, and a `PENDING`, `VALIDATED` or `REJECTED`
status. The selector validates each receipt against the same interpretation
and exact candidate snapshot/digest, so the fact evidence can be recovered
without relying on a regenerated model response.
`record_fact_validation_receipts` can advance these receipts without
rebuilding/resetting action progress; final decisions cannot be silently
reversed. Receipts are progress metadata only: they do not authorize or persist
a world write. PR #288 owns fact eligibility policy and domain persistence.

Execution keys are stable for a durable resolution + source digest + event ID.
Recovering an in-progress or technically failed action reuses that key; a
mechanics outcome is recorded separately as SUCCESS or FAILURE. Model output
cannot provide an outcome or mark a node complete.

Clarification updates only the node that was awaiting input, preserves its
execution identity and dependency topology, and returns the transitive
descendant event IDs whose gates may need reevaluation. All unrelated nodes,
including already resolved nodes, remain unchanged.

## Durable persistence

Migration 035 adds nullable `turn_resolutions.action_checkpoint_json` and a
trigger that prevents changing checkpoint evidence after the resolution has
entered `committed`, `narration_pending` or `completed`.

`TurnResolutionRepository.save_action_checkpoint` validates the strict codec,
resolution identity, player-input digest, context revision and checkpoint
size. It writes only while the caller owns the current planning lease and uses
compare-and-swap on the expected context revision and prior checkpoint value.
A stale lease, stale revision or stale expected checkpoint is rejected. When a
checkpoint already exists, its resolution/context/source/interpretation identity,
node set, action identities, dependency edges and execution keys are preserved.
Per-action states and attempt counts move only along an explicit forward
transition graph; resolved/skipped nodes are terminal. Fact-validation receipts
cannot be removed or rebound, and final receipt states cannot be reversed. The
repository enforces this monotonic-progress rule before compare-and-swap.
The existing intent JSON remains unchanged; no v3 payload is silently
substituted into historical intent records.

## Tests and acceptance

Deterministic tests cover:
- NPC/cited/quoted and negated evidence, plans without a success dependency,
  controlled actor and target resolution;
- one-at-a-time action selection, success-only conditional unlock, dependency
  skipping after a gameplay failure, and continuation to later independent
  work;
- stable idempotency keys across technical retry, checkpoint round-trip and
  strict decoding, and selective clarification resume;
- migration idempotency, durable repository CAS/lease fencing, monotonic
  checkpoint progress and post-commit immutability.

The next milestones remain separate: PR #288 owns world-fact policy and
persistence; PR #289 owns end-to-end acceptance, live Ollama evaluation,
SillyTavern exercise and any decision to move production prompting/runtime
from v2 to v3. A green deterministic suite does not prove live model quality.


## Runtime preview integration — PR #297

The production-reusable prompt/schema/strict span aligner now live in
`services/turns/player_turn_v3_prompt.py`; the test shadow runner imports the
same definitions so the production prompt cannot silently drift from the
acceptance harness.

`V3ActionPreviewService` runs only when
`CAMPAIGN_MANAGER_PLAYER_TURN_V3_ACTION_SHADOW_ENABLED=true`. It reuses the
v2 intent prompt's bounded context/history/evidence sections, makes one
structured v3 call and validates the response against the strict v3 DTO.
It then selects a bounded visible-world projection, resolves exact actor/target
mentions with `EntityReferenceResolver`, and passes only those trusted
reference results to `build_action_checkpoint` and `select_next_action`.

The durable execution service saves the checkpoint only while the original
planning lease is active and uses the repository's compare-and-swap conditions
on resolution, lease, context revision and prior checkpoint. A checkpoint
already present on retry is retained; v3 is not called again to regenerate its
graph. The preview result does not enter the v2 `TurnResolutionPlan` and never
reaches mechanics, dice, proposal generation, operation application or
narration. It can identify a next candidate or a clarification inside the
checkpoint without changing the result shown to the player.

The flag defaults off. The extra model call receives a longer lease calculated
from the two intent calls plus configured mechanics/extraction timeouts.
Preview and optional checkpoint-storage failures are content-free and
non-blocking for the v2 result. Typed item/resource/event resolution, world-fact
persistence, action execution and live SillyTavern acceptance remain future
work in PRs #298–#300.
