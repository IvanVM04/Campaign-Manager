# SQLite transaction ownership

## Core rules

- The application/use-case layer owns transaction boundaries.
- Repositories accept a caller-provided connection and must use it rather
  than silently opening a second transaction.
- World and character changes belonging to one logical action commit or roll
  back together.
- Provider calls, LLM inference and presentation narration remain outside
  write transactions.
- Migrations are the only path for forward schema/data changes.

## Transaction modes

| Mode | Intended use |
|---|---|
| `IMMEDIATE` | Short write transactions that must acquire the writer reservation before reading mutable state |
| `DEFERRED` | Read-oriented, consistent multi-query snapshots where an immediate writer lock is unnecessary |

## Current owners

- Native durable turn commit: prepared-commit application collaborator using
  the caller-provided connection. Resolution state, campaign revision and
  world/character consequences commit atomically.
- Combat attack: `CombatAttackService` opens one `IMMEDIATE` transaction.
  Encounter state and canonical target HP remain synchronized.
- Encounter create/start/advance/death-save/move/reaction:
  `CombatEncounterService` owns one service-level transaction per use case.
- World operation application: the application caller determines whether it
  owns the connection; `WorldService` delegates mixed turn application to `WorldTurnOperationCoordinator`, passing the same caller-owned connection to appliers/repositories.
- Persistent effect lifecycle: effect application/repository boundary owns
  campaign-scoped writes and keeps derived condition projections consistent.
- Campaign clock reads may use an explicit `DEFERRED` read transaction.

## Removed compatibility transaction

The narrative-first SillyTavern mutation transaction and its optional snapshot
restoration/superseding path have been removed. Migration 029 archives the
historical JSON first and removes the old runtime column; the archive is not
part of any application transaction or read path.

## Review checklist

- Does every participant share the same connection?
- Can a failure after the first write leave canonical projections divergent?
- Are in-memory state and persisted state restored together on rollback?
- Are provider calls kept outside write transactions?
- Do tests cover rollback, stale revision/lease rejection and retry behavior?\n- For each encounter mutation, does a failure after a write restore both the encounter snapshot and every canonical/effect row?
- Does a schema change preserve existing data through a forward migration?
