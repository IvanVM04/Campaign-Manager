# Character services

## Responsibility
Character creation, character state use cases and application of validated character mutations.

## Modules
- `character_creation_service.py` — creates the entity and CharacterState and optionally activates the character.
- `character_service.py` — character-state use cases, currently HP changes.
- `character_applier.py` — translates typed character operations into service calls and OperationResult values.
- `__init__.py` — public package exports.

Character state and schemas remain in `models/`, persistence in `repositories/`, and typed mutation commands in `operations/`.

## Dependency rules
- Coordinate use cases through repositories and typed operations.
- CharacterState remains canonical for player-character mechanics; encounter/equipment values are projections.
- Do not depend on API routers or LLM provider adapters.
- Keep rules-engine mechanics out of these application services.

## Transaction and ownership notes
- CharacterCreationService currently owns its connection via `get_conn()`; this migration deliberately preserves that behavior.
- CharacterService.change_hp accepts an optional connection so turn/world workflows can participate in their caller-owned transaction.
- CharacterApplier remains an adapter from CharacterOperation to CharacterService; it does not own persistence or transactions.
- WorldService currently composes CharacterApplier, so its existing wiring and shared repository identity must remain intact.

## Pending work
- [ ] Audit mutation ownership across services, repositories and operations.
- [ ] Test invariants for active-character switching and campaign scoping.
- [ ] Review atomic synchronization of character, equipment and encounter projections.
- [ ] Clarify the boundary between character creation rules and persistence.
- [ ] Add architecture tests against transport/provider dependencies.
- [ ] Revisit CharacterCreationService transaction ownership separately, with explicit caller-connection support and tests if needed.

## Compatibility
The former `services.character_*` module paths remain as backward-compatible shims. Consumers can migrate to `services.characters.*` incrementally; do not remove the shims until repository-wide import and test audits show no remaining callers.

## Migration status
The three character application modules now live in this package. No business logic, transaction behavior or runtime composition was intentionally changed.
