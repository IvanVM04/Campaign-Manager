# Durable turn-resolution persistence (migration 022)

## Scope

Migration 022 introduces `turn_resolutions`, a durable execution envelope linked optionally to the existing historical `turns` row. It does not change how a turn is currently executed. Existing `turns` rows, external versioning, and campaign revision tracking remain intact.

## Why a linked table

The `turns` table is a completed/history-oriented transcript with required narrative and adapter regeneration semantics. Reusing it for in-flight work would either weaken those existing constraints or expose incomplete turns to history consumers. A linked resolution record keeps the execution lifecycle separate while preserving one canonical historical transcript after completion. It is not a second transcript/history.

## Persisted data

- Campaign and optional session / historical turn references.
- Normalized player input, adapter namespace, idempotency key, and request fingerprint.
- Lifecycle state: accepted, planning, awaiting_input, prepared, committed, narration_pending, completed, rejected.
- Context revision and JSON payload slots for proposal, adjudication, mechanics, and operation outcomes.
- Optional narrative, attempt count, lease token/expiry, safe error category, and lifecycle timestamps.

Uniqueness is enforced by `(campaign_id, adapter_namespace, idempotency_key)`. The fingerprint is immutable with the request identity; callers must compare it on duplicate lookup and return a conflict when it differs.

## Transition and concurrency rules

- Application transitions are conditional on the expected current state.
- SQLite triggers reject illegal lifecycle transitions even if a caller bypasses the repository.
- A planning claim increments attempts and is allowed for accepted/awaiting-input rows or planning rows whose lease has expired.
- The lease token identifies the current attempt. The repository requires the expected lease token for every transition out of `planning`, fencing a worker whose lease was reclaimed. The future consequence-commit use case must perform this token check in the same `BEGIN IMMEDIATE` transaction as its domain mutations.
- Identity fields cannot be edited after insert.
- A historical `turn_id`, when supplied, must belong to the same campaign.

## Important limitations

This PR establishes persistence primitives only. It deliberately does not:
- create resolution records from native or SillyTavern requests;
- change current turn application, narrative generation, or retry semantics;
- persist manual-roll payloads or clarification answers yet;
- add a recovery worker or public API;
- claim exactly-once execution before PR30 wires the commit transaction to these records.

The repository's `transition` method expects the caller's transaction connection. The caller must use `BEGIN IMMEDIATE` for claims/transitions that coordinate state mutation. The `turns` transcript should be linked only when its historical record is created in the same transaction as the corresponding committed resolution.

## Follow-up

PR30 will wire native turn execution to accept/prepare/commit/narration-pending/completed boundaries and prove crash recovery with failure-injection tests. PR31 will adapt SillyTavern to the same lifecycle.
