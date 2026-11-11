# Legacy SillyTavern turn boundary

## Responsibility

`services/turns/legacy_silly_tavern_turn_service.py` (`LegacySillyTavernTurnService`) owns only the deprecated `POST /integration/turn`
narrative-first workflow. It preserves the compatibility behavior required by
pre-durable clients:

- external-turn idempotency and transcript version checks;
- narrative extraction into typed world/character operations;
- snapshot-based regeneration reconciliation using a JSON snapshot stored in `turns.snapshot` (not separate snapshot tables);
- atomic world mutation and turn persistence;
- restoration of the shared in-memory world after rollback.

It is not an alternate implementation of the active turn-resolution contract.
New gameplay behavior, challenge handling, or narration completion must not be
added here.

## Adapter boundary

`SillyTavernIntegrationService` remains the active integration adapter for
context/history construction and external transcript-state reads. Its public
`process_turn()` method delegates to `LegacySillyTavernTurnService` to preserve
the existing route and in-process API while isolating the deprecated mutation
workflow. Private transaction and rollback helpers remain encapsulated by the
legacy collaborator and are not re-exported through the adapter.

The legacy collaborator is located in `services/turns` because it owns a turn-execution lifecycle, but it remains quarantined from the active durable coordinator. It receives the campaign scope, state/context service,
extractor, world service, turn repository, shared campaign lock, revision
repository, snapshot repository, and the existing error types explicitly. It
does not receive the adapter or the durable turn service.

## Invariants preserved

- The public `SillyTavernIntegrationService.process_turn()` signature remains
  unchanged.
- The route continues to use the same compatibility error hierarchy and result
  type.
- LLM extraction remains outside the `IMMEDIATE` write transaction.
- The authoritative idempotency and campaign-revision checks remain inside the
  write transaction.
- Regeneration restores the previous snapshot and supersedes the old turn in
  the same transaction as applying and persisting the new version.
- Failed operation batches roll back world mutations and preserve the failed
  turn record behavior.
- Rollback restores the original shared `WorldState` object's collections,
  preserving object identity for existing context references.
- No endpoint payload, persisted JSON shape, database schema, or active durable
  lifecycle behavior changes.

## Retirement policy

This extraction is quarantine, not deletion. Keep the deprecated route and its
snapshot dependencies until downstream clients have been checked and structured
usage telemetry shows zero use for an agreed migration window. Snapshot data is
stored inline as JSON in the nullable `turns.snapshot` column; `WorldSnapshotRepository`
reads/writes the campaign's world tables to create or restore that payload, but
there are no dedicated snapshot tables. Retire the route, collaborator, snapshot
repository usage and legacy tests in a separate change after explicit compatibility
sign-off. Handle the `turns.snapshot` column and existing payloads in a separate,
explicit data-retention migration.
