# World applier boundaries

## Current ownership

- `WorldApplier` remains the compatibility facade used by `WorldService`.
- `WorldRelationApplier` owns validation and in-memory mutation for create, update, and remove relation operations.
- The relation collaborator has no repository, SQLite, provider, or API dependencies.
- `WorldApplier` delegates relation operations and retains its private relation methods as compatibility delegates while callers migrate.

## Preserved contract

The extraction does not change operation types, result statuses/messages, relation identifiers, active/inactive semantics, world-state ownership, or persistence. `WorldService` continues to decide when the in-memory world is persisted. Existing facade-level relation tests remain the integration contract; focused collaborator tests cover its direct behavior.

## Follow-up

Extract another operation family only after auditing its shared helpers and tests. Do not turn the facade into a second domain implementation, and do not move persistence into operation appliers.
