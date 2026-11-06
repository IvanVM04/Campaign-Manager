# Turn services

## Responsibility
Coordinate the turn lifecycle: preparation, adjudication orchestration, durable commit, challenge continuation, narration and legacy compatibility.

The durable resolution record is authoritative for in-flight state. Narrative/transcript versions are a separate projection and must never replay committed consequences.

## Package modules
- turn_execution_lock.py — canonical process-local lock shared by turn coordinators.
- turn_resolution_codec.py — canonical JSON codec for durable turn-resolution records.
- durable_turn_challenge_state_service.py — read-only challenge-state projections.
- durable_turn_clarification_submission_service.py — clarification submission and recovery.
- durable_turn_manual_roll_submission_service.py — manual-roll submission and recovery.
- durable_turn_prepared_commit_service.py — atomic prepared-resolution commit boundary.
- durable_turn_preparation_mapper.py — adapter-facing preparation projection.
- durable_turn_result_mapper.py — durable record to public result mapping.
- durable_turn_narration_service.py — native and external narration completion.

## Remaining modules (still in services/)
- durable_native_turn_service.py — durable coordinator/facade.
- turn_resolution_service.py — non-persistent turn planning and plan application.
- campaign_turn_service.py — compatibility surface.
- legacy_silly_tavern_turn_service.py and silly_tavern_integration_service.py — legacy workflow.

## Dependency rules
- Preserve idempotency, lease fencing, campaign revision checks and atomic commit.
- Keep write transactions short; provider calls/narration remain outside them.
- Narration consumes committed evidence and never applies consequences.
- Isolate legacy snapshot reconciliation from the active durable workflow.
- Routers remain transport adapters, not lifecycle authorities.

## Pending work
- [x] Extract challenge projections/submissions, prepared commit, narration and result mapping while preserving DurableNativeTurnService as the public coordinator.
- [ ] Replace exception-message matching for lifecycle/error codes with typed errors and explicit transition reasons.
- [ ] Add focused recovery tests for expired planning leases and restart/concurrency boundaries.
- [ ] Split the large SillyTavern integration tests by durable API, adapter behavior and legacy compatibility without reducing coverage.
- [ ] Keep the deprecated narrative-first route and CampaignTurnService gated by observed usage and downstream compatibility checks.
- [ ] Retain the documented single-process constraint while locks/runtime are process-local.

## Migration status
The turns boundary has been decomposed internally. `services.turns` owns the execution lock, durable resolution codec, challenge projections/submissions, prepared commit, preparation/result mapping, and narration lifecycle. Their former `services.durable_turn_*` module paths remain compatibility re-exports. `DurableNativeTurnService` remains the public coordinator, while `TurnResolutionService` remains responsible for non-persistent planning and plan application. The old CampaignTurnService is compatibility-only; the legacy SillyTavern turn service is used by the deprecated POST /integration/turn route. SillyTavernIntegrationService itself remains active for context and external transcript-state reads.
