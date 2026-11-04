# Durable turn-resolution persistence (migration 022)

## Scope

Migration 022 introduces `turn_resolutions`, a durable execution envelope linked optionally to the existing historical `turns` row. Migration 023 adds the resulting campaign revision. Native automatic turns now use this lifecycle; the existing `turns` rows, external versioning, and campaign revision tracking remain intact.

## Why a linked table

The `turns` table is a completed/history-oriented transcript with required narrative and adapter regeneration semantics. Reusing it for in-flight work would either weaken those existing constraints or expose incomplete turns to history consumers. A linked resolution record keeps the execution lifecycle separate while preserving one canonical historical transcript after completion. It is not a second transcript/history.

## Persisted data

- Campaign and optional session / historical turn references.
- Normalized player input, adapter namespace, idempotency key, and request fingerprint.
- Lifecycle state: accepted, planning, awaiting_input, prepared, committed, narration_pending, completed, rejected.
- Context revision and resulting revision, plus JSON payload slots for proposal, adjudication, mechanics, and operation outcomes.
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

Migration 023 adds `resulting_revision`; native automatic turns now populate it in the same transaction as consequence commit and lifecycle transition. Narration is generated after that transaction and completion stores the transcript and final narrative atomically.

For reliable client retries after a response may have been lost, native `/turn` accepts an `Idempotency-Key` HTTP header. When supplied, the same key and request fingerprint resolve to the existing lifecycle record. Without a client key, a best-effort native key is derived from the current transcript position; clients should send the header when retrying requests.

The current native integration deliberately does not:
- provide durable continuation for manual-roll and clarification waits; these remain follow-ups;
- persist manual-roll payloads or clarification answers; manual dice mode remains on the compatibility path;
- add a background recovery worker; a retry of `/turn` with the same `Idempotency-Key` resumes a committed resolution's narration;
- promise exactly-once execution across external providers; database idempotency and atomic consequence commit prevent duplicate domain application, while narration is safely retryable.

The repository's `transition` method expects the caller's transaction connection. The caller must use `BEGIN IMMEDIATE` for claims/transitions that coordinate state mutation. The `turns` transcript should be linked only when its historical record is created in the same transaction as the corresponding committed resolution.

## Follow-up

PR30 wires native automatic turns to the durable lifecycle. PR31 wires SillyTavern to the same coordinator: the adapter claims a stable external-turn identity, commits consequences before external generation, and completes the narration projection afterward. Regeneration updates only the narrative version and never reapplies domain operations.
