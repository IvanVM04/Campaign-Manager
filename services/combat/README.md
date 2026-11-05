# Combat services

## Responsibility
Application orchestration for combat encounters and attacks. Deterministic mechanics belong in rules_engine/dnd5e_2014/.

## Current modules (still in services/)
- combat_attack_service.py
- combat_encounter_service.py
- weapon_equipment_service.py

Combat state is in models/, persistence in repositories/, and ruleset mechanics in rules_engine/dnd5e_2014/.

## Dependency rules
- Delegate deterministic mechanics to the rules engine.
- Keep the rules engine independent of FastAPI, SQLite, LLM providers and service orchestration.
- Treat character state as canonical where encounter data is a projection.

## Pending work
- [ ] Audit duplicated mechanics that should be delegated to the rules engine.
- [ ] Map transaction ownership for multi-entity combat updates.
- [ ] Review synchronization of HP, resources, conditions and encounter projections.
- [ ] Surface unsupported 2014 rules rather than silently improvising.
- [ ] Expand coverage for currently partial combat flows as rules are implemented.

## Migration status
This is a documented target boundary only. Source modules and imports remain in services/ until a separate migration preserves compatibility.
