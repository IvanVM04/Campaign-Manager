# SQLite transaction ownership

**Status:** Initial implementation in PR #22  
**Scope:** Explicit transaction boundaries for selected application use cases

## Contract

`database.transaction(mode)` owns exactly one SQLite connection and one transaction. It:

1. Opens a connection using the existing `get_conn()` configuration.
2. Starts an explicit `DEFERRED`, `IMMEDIATE` or `EXCLUSIVE` transaction.
3. Yields the connection to the application use case.
4. Commits when the context exits normally.
5. Rolls back when an exception escapes the context.
6. Closes the connection in all cases.

The connection is valid only inside the context. Every repository participating in the same atomic operation must receive that exact connection via its `conn` argument.

Nested transaction contexts are not supported. Compose multiple repository operations on the connection already owned by the outer use case. Savepoints require a separate, explicit design if a real use case needs partial rollback.

## Mode selection

| Mode | Intended use |
|---|---|
| `DEFERRED` | Read-oriented, consistent multi-query snapshots where an immediate writer lock is unnecessary |
| `IMMEDIATE` | Read/validate/write workflows that must reserve SQLite's writer slot before checking mutable state |
| `EXCLUSIVE` | Reserved for schema/maintenance workflows; not used by current application use cases |

Use the weakest mode that preserves the invariant. Do not hold an `IMMEDIATE` transaction while calling an LLM, making HTTP requests, waiting for user input or doing expensive non-database work.

## Migrated use cases

- `CampaignClockService.get`: explicit `DEFERRED` snapshot for campaign validation and clock retrieval.
- `CampaignClockService.advance`: explicit `IMMEDIATE` transaction covering clock advancement and expiration of due campaign-time effects.
- `services.campaign.PersistentEffectService.create` and `set_status`: explicit `IMMEDIATE` transaction covering ownership checks, clock deadline calculation and effect mutation.
- `CombatAttackService.attack`: explicit `IMMEDIATE` transaction covering encounter turn validation, rules resolution, PC HP synchronization and encounter persistence.
- `SillyTavernIntegrationService._process_turn_locked`: explicit `IMMEDIATE` write transaction covering authoritative idempotency checks, optional snapshot restoration/superseding, world and character operations, and successful turn persistence. Narrative extraction remains outside the transaction. Failed operations roll back this transaction before persisting the failed turn record through its own repository transaction.

These use cases already relied on a caller-supplied shared connection for their atomic writes. This change makes ownership visible and consistent; it does not change their domain rules or transaction scope.

## Compatibility

`get_conn()` remains available for simple one-connection operations, migrations and existing code not yet migrated. Its existing automatic commit/rollback/close behaviour is unchanged.

The transaction helper is intentionally small and SQLite-specific. It is not a generic Unit of Work, does not abstract repositories, and does not imply support for multiple database engines.

## Verification

The database tests verify successful commit, rollback on an escaping exception and rejection of unsupported transaction modes. Existing service tests continue to verify domain-level atomicity, including campaign clock/effect expiry and encounter/character HP synchronization.

The remaining services are migrated incrementally when their transaction boundary is being changed for a concrete reason. A repository-wide mechanical replacement is explicitly out of scope.
