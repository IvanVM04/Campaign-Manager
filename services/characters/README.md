# Character services

## Responsibility
Character creation, character state use cases and application of validated character mutations.

## Current modules (still in services/)
- character_creation_service.py
- character_service.py
- character_applier.py

Character state and schemas remain in models/, persistence in repositories/, and typed mutation commands in operations/.

## Dependency rules
- Coordinate use cases through repositories and typed operations.
- CharacterState remains canonical for player-character mechanics; encounter/equipment values are projections.
- Do not depend on API routers or LLM provider adapters.

## Pending work
- [ ] Audit mutation ownership across services, repositories and operations.
- [ ] Test invariants for active-character switching and campaign scoping.
- [ ] Review atomic synchronization of character, equipment and encounter projections.
- [ ] Clarify the boundary between character creation rules and persistence.
- [ ] Add architecture tests against transport/provider dependencies.

## Migration status
This is a documented target boundary only. Source modules and imports remain in services/ until a separate migration preserves compatibility.
