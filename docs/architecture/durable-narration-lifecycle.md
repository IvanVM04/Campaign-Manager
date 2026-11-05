# Durable narration lifecycle boundary

## Responsibility

`DurableTurnNarrationService` owns the two narration completion paths:

- native narration generation after a durable consequence commit;
- external SillyTavern narration persistence and transcript versioning.

The collaborator does not prepare or commit gameplay consequences. It only operates
on a resolution that has already crossed the durable prepared/commit boundary, or on
an existing legacy transcript projection where compatibility requires it.

## Invariants preserved

- Narration generation reads a fresh context and recent-turn history.
- Native narration completion transitions `committed` to `narration_pending`
  before generating prose, then persists the transcript and marks the resolution
  `completed`.
- External narration never applies gameplay consequences.
- External turn identity, player input, transcript version ordering, and duplicate
  version content remain validated.
- External transcript writes re-check the active version inside the write transaction.
- The public `DurableNativeTurnService.complete_external_narration()` API remains
  unchanged.
- Database schema, persisted JSON, and endpoint payloads remain unchanged.

The service receives repositories, the resolver, the campaign scope, the shared
execution lock, and a context-loading callback explicitly. It does not retain the
native turn facade as an owner dependency.
