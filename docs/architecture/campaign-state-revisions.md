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

The internal DM turn flow reads its initial revision and complete context within one DEFERRED transaction. LLM planning occurs after that connection is released. Before applying the plan, the service starts an IMMEDIATE transaction and compares the current revision with the captured revision. A mismatch rejects the stale plan without applying any operations.

SillyTavern integration follows the same pattern: it captures a consistent campaign context and revision before extraction, then checks the revision inside the authoritative IMMEDIATE transaction before snapshot restoration or operation application.

Manual-roll requests retain the revision captured when the roll was requested. If campaign state changes while the player is rolling, submission is rejected and the action must be retried against fresh context.

## Boundaries

This protects database-backed campaign state across service instances and processes. It does not replace the in-process `TurnExecutionLock`, provide distributed locking, or make arbitrary in-memory mutations safe. Callers must continue to reload authoritative state when opening a new processing snapshot and restore in-memory objects after rollback.

The revision is intentionally conservative: any campaign-scoped row mutation invalidates a plan, even if the changed row would not have affected that plan. This favors correctness over avoiding occasional retries.

## Future migration requirement

Any future migration that adds a campaign-owned table with a `campaign_id` column must also install INSERT, UPDATE and DELETE revision triggers for that table. Migration 021 discovers the campaign-owned tables present when it runs; it cannot automatically discover tables added by later migrations.
