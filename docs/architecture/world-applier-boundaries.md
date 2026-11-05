# World applier boundaries

## Current ownership

- `WorldApplier` remains the compatibility facade used by `WorldService`.
- `WorldRelationApplier` owns create, update, and remove relation validation and in-memory mutation.
- `WorldItemApplier` owns item definitions and inventory-instance operations: create item, create instance, transfer instance, and update instance.
- Both collaborators operate only on `WorldState`; neither owns persistence, repositories, API concerns, or transaction boundaries.
- The facade delegates operation families and retains private delegates for compatibility with existing internal callers and tests.

## Item-specific invariants

- Item and instance IDs continue to be allocated from the current in-memory collections.
- Item equipment, weapon, and armor validation remains in the item application boundary.
- Owner/location reference checks, duplicate instance checks, partial-update `_UNSET` semantics, and inactive-state behavior remain unchanged.
- `WorldService` remains responsible for persistence after successful application.

## Follow-up

Extract another operation family only after auditing shared helpers and tests. Do not move persistence into operation appliers or turn the facade into a second domain implementation.
