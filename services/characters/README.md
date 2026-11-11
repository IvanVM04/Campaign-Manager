# Character services

## Responsibility
Character creation, character state use cases and application of validated character mutations.

## Modules
- `character_creation_service.py` — creates the entity and CharacterState and optionally activates the character.
- `character_service.py` — character-state use cases, currently HP changes.
- `character_sheet_query_service.py` — builds a detached D&D 5e sheet projection from campaign-scoped repositories.
- `character_applier.py` — translates typed character operations into service calls and OperationResult values.
- `__init__.py` — public package exports.

Character state and schemas remain in `models/`, persistence in `repositories/`, and typed mutation commands in `operations/`.

## Dependency rules
- Read projections expose only player-facing fields; never return entity notes or raw character metadata.
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
- [ ] Extend the sheet only when corresponding character data is persisted (race, background, spellcasting, features, resources).
- [ ] Add equipment-derived AC and attack summaries to the read model with explicit rules-engine projections.
- [ ] Audit mutation ownership across services, repositories and operations.
- [ ] Test invariants for active-character switching and campaign scoping.
- [ ] Review atomic synchronization of character, equipment and encounter projections.
- [ ] Clarify the boundary between character creation rules and persistence.
- [x] Enforce transport/provider/service dependency boundaries in `tests/test_architecture_boundaries.py` and `docs/architecture/package-dependency-matrix.md`.
- [ ] Revisit CharacterCreationService transaction ownership separately, with explicit caller-connection support and tests if needed.

## Migration status
The character application modules live in this canonical package. The former flat `services.character_*` compatibility modules have been removed; consumers should import from `services.characters`.
