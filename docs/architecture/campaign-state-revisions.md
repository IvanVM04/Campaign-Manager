# Campaign state revisions

**Status:** Introduced in schema migration 021.

## Purpose

A turn plan is prepared from a read snapshot and may spend significant time in an LLM provider. Comparing only the visible `TurnContext` is insufficient: persistent effects, combat encounters, campaign clock state, turn history, and other campaign-scoped records may change without appearing in that context.

The `campaign_state_versions` table provides a monotonic revision per campaign. SQLite triggers increment it after every INSERT, UPDATE, or DELETE on the campaign row and on every table containing a `campaign_id` column. The revision change participates in the same transaction as the underlying mutation and therefore rolls back with it.

## Contract

- Each campaign starts at revision 1.
- Revisions are scoped by campaign.
- The revision is a mutation counter, not a count of committed business operations. A single transaction may increment it multiple times.
- Failed/rolled-back transactions do not advance the visible revision.
- The repository requires the caller's connection, so the read participates in the caller's snapshot or write transaction.
- Existing rows are not rewritten during migration; all existing campaigns receive revision 1.
- New campaigns receive a revision row automatically.

## Turn processing

The internal DM turn flow acquires the process-local campaign cache lock briefly, then reads its initial revision and complete context/history within one DEFERRED transaction. The loader refreshes the shared cache and returns a deep-detached `TurnContext`/history snapshot. The lock and read connection are released before intent, mechanics, proposal or narration provider calls. Before applying a plan, the prepared-commit service reacquires the same lock **before** starting an IMMEDIATE transaction, compares the current revision and context/history with the captured snapshot, and applies consequences only if they still match. A mismatch rejects the stale plan without applying any operations.

SillyTavern integration, clarification and manual-roll continuation follow the same detached-snapshot/short-commit-lock pattern. API routes do not wrap provider preparation in a campaign lock; they acquire it only for cache-backed context rendering after the durable service has returned.

Manual-roll requests retain the revision captured when the roll was requested. If campaign state changes while the player is rolling, submission is rejected and the action must be retried against fresh context.

## Boundaries

This protects database-backed campaign state across service instances and processes. The in-process `TurnExecutionLock` protects short reads/publications of the shared runtime cache and the prepared-commit critical section; it is deliberately not held across provider calls. Always acquire it before opening a SQLite transaction when both are needed. It does not provide distributed locking or make arbitrary in-memory mutations safe. Callers must continue to reload authoritative state when opening a new processing snapshot and restore in-memory objects after rollback.

The revision is intentionally conservative: any campaign-scoped row mutation invalidates a plan, even if the changed row would not have affected that plan. This favors correctness over avoiding occasional retries.

## Future migration requirement

Any future migration that adds a campaign-owned table with a `campaign_id` column must also install INSERT, UPDATE and DELETE revision triggers for that table. Migration 021 discovers the campaign-owned tables present when it runs; it cannot automatically discover tables added by later migrations.
