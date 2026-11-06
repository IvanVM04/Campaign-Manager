# Turn services

## Responsibility
Coordinate the turn lifecycle: preparation, adjudication orchestration, durable commit, challenge continuation, narration and legacy compatibility.

The durable resolution record is authoritative for in-flight state. Narrative/transcript versions are a separate projection and must never replay committed consequences.

## Current modules (still in services/)
- durable_native_turn_service.py — durable coordinator/facade.
- turn_resolution_service.py and turn_resolution_codec.py — preparation and serialization.
- durable_turn_challenge_state_service.py
- durable_turn_clarification_submission_service.py
- durable_turn_manual_roll_submission_service.py
- durable_turn_prepared_commit_service.py
- durable_turn_preparation_mapper.py and durable_turn_result_mapper.py
- durable_turn_narration_service.py
- campaign_turn_service.py — compatibility surface.
- legacy_silly_tavern_turn_service.py and silly_tavern_integration_service.py — legacy workflow.
- turn_execution_lock.py

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
The turns boundary has already been decomposed internally, but its source modules remain under services/ and this directory is still a target guide. Move them as a package migration only after imports are mapped. The old CampaignTurnService is compatibility-only; the legacy SillyTavern turn service is used by the deprecated POST /integration/turn route. SillyTavernIntegrationService itself remains active for context and external transcript-state reads.
