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
- `mechanics_adjudicator.py` — proposes and validates mechanics decisions; deterministic rules code rolls dice and applies results.
- `turn_resolution_service.py` — prepares structured proposals from player intent, and exposes application/narration phases for non-durable callers.
- `durable_turn_challenge_state_service.py` — read-only challenge-state projections.
- `durable_turn_clarification_submission_service.py` — clarification submission and recovery.
- `durable_turn_manual_roll_submission_service.py` — manual-roll submission and recovery.
- `durable_turn_execution_service.py` — request idempotency, planning leases, preparation and recovery before the atomic commit.
- `durable_turn_errors.py` — stable error codes for durable lifecycle and commit failures.
- `durable_turn_prepared_commit_service.py` — atomic prepared-resolution commit boundary.
- `durable_turn_preparation_mapper.py` — adapter-facing preparation projection.
- `durable_turn_result_mapper.py` — durable record to public result mapping.
- `durable_turn_narration_service.py` — native and external narration completion.
- `durable_native_turn_service.py` — public durable turn coordinator and lifecycle façade.

## SillyTavern adapter

`integrations/adapters/silly_tavern/context_adapter.py` provides active
context/history and external transcript-state reads. The integration façade
does not own player-turn mutation; the extension uses the same durable
resolve/complete lifecycle as the native API.

## Test and evaluation map

- `tests/test_durable_native_turn.py` and `tests/test_durable_silly_tavern_turn.py` protect the durable turn state machine.
- `tests/test_manual_roll_submission_service.py` protects the manual d20 challenge submission/replay boundary, including the provider-independent integration path.
- `tests/test_silly_tavern_context_adapter.py` protects adapter query validation, context rendering, history filtering and external transcript-state reads.
- Live prompt behavior is evaluated separately by `python -m pytest -m real_llm -v -s`; see [the prompt evaluation guide](../../docs/quality/prompt-evaluation-2026-11-12.md).

## Dependency and lifecycle rules

- Preserve idempotency, lease fencing, campaign revision checks and atomic commit.
- Build proposal context at the turn/application boundary; pass a typed `WorldContextProjection` into `services/llm_world`.
- Keep provider calls and narration outside write transactions.
- Narration consumes committed evidence and never applies consequences.
- Clarifications and manual rolls resume the original durable resolution.
- Routers remain transport adapters, not lifecycle authorities.
- Do not reintroduce the removed narrative-first mutation endpoint or snapshot restoration.

## Pending work

- [x] Replace exception-message matching for lifecycle/error codes with typed error codes and explicit transition reasons.
- [x] Extract request acceptance/planning/execution, challenge projections/submissions, prepared commit, narration and result mapping while preserving `DurableNativeTurnService` as the public coordinator.
- [x] Add focused recovery tests for expired planning leases, late-worker fencing and retry after unexpected planning failure across a fresh runtime.
- [ ] Keep the documented single-process constraint while locks/runtime are process-local.
- [ ] Revisit remaining continuation orchestration only where a separate lifecycle boundary reduces coupling without duplicating ownership.
