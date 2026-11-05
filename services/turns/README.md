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
- [ ] Continue auditing DurableNativeTurnService; extract only distinct responsibilities while preserving its facade.
- [ ] Define legacy SillyTavern compatibility contract and removal criteria.
- [ ] Review lease expiry/recovery and stale-plan behavior under concurrency and process restart.
- [ ] Strengthen idempotency, duplicate-delivery, narrative-version and narration-retry tests.
- [ ] Document transaction ownership and lifecycle transitions.
- [ ] Retain and document the single-process constraint while locks/runtime are process-local.

## Migration status
This is a documented target boundary only. Source modules and imports remain in services/ until a separate migration preserves compatibility.
