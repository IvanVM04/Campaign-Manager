# Combat services

## Responsibility
Application orchestration for combat encounters, attacks and character equipment. Deterministic mechanics belong in `rules_engine/dnd5e_2014/`.

## Modules
- `combat_encounter_service.py` — campaign-scoped encounter lifecycle, initiative, turn progression and combatant projections.
- `combat_attack_service.py` — attack validation/resolution and atomic persistence of encounter and canonical HP state.
- `weapon_equipment_service.py` — equipment queries/mutations and derived armor/attack profiles.

Combat state is in `models/`, persistence in `repositories/`, and ruleset mechanics in `rules_engine/dnd5e_2014/`.

## Dependency rules
- Delegate deterministic mechanics to the rules engine.
- Keep the rules engine independent of FastAPI, SQLite, LLM providers and service orchestration.
- Treat character state as canonical where encounter data is a projection.
- Keep encounter, character/creature HP and effect updates within their existing transaction boundaries.
- Runtime composition imports the canonical `services.combat` package; legacy module paths remain compatibility shims.

## Pending work
- [ ] Audit duplicated mechanics that should be delegated to the rules engine.
- [ ] Map transaction ownership for multi-entity combat updates.
- [ ] Review synchronization of HP, resources, conditions and encounter projections.
- [ ] Surface unsupported 2014 rules rather than silently improvising.
- [ ] Expand coverage for currently partial combat flows as rules are implemented.
- [ ] Retire compatibility shims only after external and test consumers have migrated.

## Migration status
The three service modules now live in this package. The old `services.combat_*_service` and `services.weapon_equipment_service` paths re-export the canonical implementations.
