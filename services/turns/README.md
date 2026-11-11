# Turn services

## Responsibility
Coordinate the turn lifecycle: preparation, adjudication orchestration, durable commit, challenge continuation, narration and legacy compatibility.

The turn package owns the mechanics adjudicator and narrative-generation service used by turn planning. Their provider and context collaborators are injected by the composition root.

The durable resolution record is authoritative for in-flight state. Narrative/transcript versions are a separate projection and must never replay committed consequences.

## Package modules
- `dm_service.py` — narrative generation for a turn; builds campaign/world context and delegates prose generation to the injected provider without mutating world state.
- `turn_execution_lock.py` — canonical process-local lock shared by turn coordinators.
- `turn_resolution_codec.py` — canonical JSON codec for durable turn-resolution records.
- `mechanics_adjudicator.py` — structured mechanics proposals with strict response validation; it never rolls dice or applies consequences.
- `turn_resolution_service.py` — non-persistent turn planning, mechanics orchestration and plan application.
- `durable_turn_challenge_state_service.py` — read-only challenge-state projections.
- `durable_turn_clarification_submission_service.py` — clarification submission and recovery.
- `durable_turn_manual_roll_submission_service.py` — manual-roll submission and recovery.
- `durable_turn_prepared_commit_service.py` — atomic prepared-resolution commit boundary.
- `durable_turn_preparation_mapper.py` — adapter-facing preparation projection.
- `durable_turn_result_mapper.py` — durable record to public result mapping.
- `durable_turn_narration_service.py` — native and external narration completion.
- `durable_native_turn_service.py` — public durable turn coordinator and lifecycle facade.
- `legacy_silly_tavern_turn_service.py` — quarantined narrative-first snapshot reconciliation for the deprecated `POST /integration/turn` compatibility route; no new gameplay behavior belongs here.

## Integration adapter outside this package
- `services/silly_tavern_integration_service.py` — active context and external transcript-state adapter; delegates the deprecated route to the isolated legacy collaborator in this package.

## Dependency rules
- Preserve idempotency, lease fencing, campaign revision checks and atomic commit.
- Keep write transactions short; provider calls/narration remain outside them.
- Narration consumes committed evidence and never applies consequences.
- Isolate legacy snapshot reconciliation from the active durable workflow.
- Routers remain transport adapters, not lifecycle authorities.

## Pending work
- [x] Extract challenge projections/submissions, prepared commit, narration and result mapping while preserving DurableNativeTurnService as the public coordinator.
- [x] Move non-persistent turn planning and plan application into the canonical turns package, retaining the legacy import path only where a verified caller remains.
- [ ] Replace exception-message matching for lifecycle/error codes with typed errors and explicit transition reasons.
- [x] Add focused recovery tests for expired planning leases, late-worker fencing, and retry after an unexpected planning failure across a fresh runtime.
- [x] Split the former monolithic SillyTavern integration test module into schema, API, service, lifecycle and regeneration-failure modules without reducing assertions (PR #186). The remaining lifecycle module is still large; its next split is tracked in the test-suite audit.
- [x] Remove CampaignTurnService from runtime composition and delete the isolated compatibility implementation after confirming no production consumers remain.
- [ ] Keep the deprecated narrative-first route gated by observed usage and downstream compatibility checks.
- [ ] Retain the documented single-process constraint while locks/runtime are process-local.

## Migration status
The turns boundary has been decomposed internally. The canonical package owns narrative generation, the mechanics adjudicator, the execution lock, non-persistent planner, durable resolution codec and coordinator, challenge projections/submissions, prepared commit, preparation/result mapping and narration lifecycle. The old `CampaignTurnService` compatibility implementation and its dedicated tests have been removed; the legacy SillyTavern turn service remains active only through the deprecated `POST /integration/turn` route. `SillyTavernIntegrationService` remains active for context and external transcript-state reads.
