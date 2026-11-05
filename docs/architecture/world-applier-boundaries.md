# World applier boundaries

## Current ownership

- `WorldApplier` remains the compatibility facade used by `WorldService`.
- `WorldRelationApplier` owns create, update, and remove relation validation and in-memory mutation.
- `WorldItemApplier` owns item definitions and inventory-instance operations: create item, create instance, transfer instance, and update instance.
- `WorldResourceApplier` owns resource definitions and balance operations: create resource, gain, spend, and transfer.
- All collaborators operate only on `WorldState`; none owns persistence, repositories, API concerns, or transaction boundaries.
- The facade delegates operation families and retains private delegates for compatibility with existing internal callers and tests.

## Preserved invariants

- Item and instance IDs continue to be allocated from the current in-memory collections.
- Item equipment, weapon, and armor validation remains in the item application boundary.
- Item owner/location reference checks, duplicate instance checks, partial-update `_UNSET` semantics, and inactive-state behavior remain unchanged.
- Resource and balance IDs continue to be allocated from their current in-memory collections.
- Resource operations retain finite-positive amount validation, resource/owner reference checks, insufficient-balance protection, and existing balance lookup semantics.
- Resource transfers validate both entities and the source balance before changing either balance; target balance creation remains an in-memory application concern.
- `WorldService` remains responsible for persistence after successful application.

## Follow-up

Extract another operation family only after auditing shared helpers and tests. Do not move persistence into operation appliers or turn the facade into a second domain implementation.
