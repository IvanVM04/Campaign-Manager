# Combat services

## Responsibility
Application orchestration for combat encounters, attacks and character equipment. Deterministic mechanics belong in `rules_engine/dnd5e_2014/`.

## Modules
- `combat_encounter_service.py` — campaign-scoped encounter lifecycle, initiative, turn progression and combatant projections.
- `combat_attack_service.py` — attack use-case orchestration and atomic persistence of encounter and canonical HP state.
- `rules_engine/dnd5e_2014/combat/hit_points.py` — deterministic HP/death-track transitions invoked by the combat use case.
- `weapon_equipment_service.py` — equipment queries/mutations and derived armor/attack profiles.

Combat state is in `models/`, persistence in `repositories/`, and ruleset mechanics in `rules_engine/dnd5e_2014/`.

## Dependency rules
- Delegate deterministic mechanics to the rules engine.
- Keep the rules engine independent of FastAPI, SQLite, LLM providers and service orchestration.
- Treat character state as canonical where encounter data is a projection.
- Keep encounter, character/creature HP and effect updates within their existing transaction boundaries.
- Runtime composition and tests import the canonical `services.combat` package; former flat combat shims have been retired.

## Pending work
- [x] Move deterministic HP/death-track transitions out of CombatAttackService and into the rules engine (this PR).
- [ ] Extract player/NPC weapon and natural-attack profile resolution from CombatAttackService into a focused application collaborator.
- [ ] Audit remaining duplicated mechanics that should be delegated to the rules engine.
- [ ] Map transaction ownership for multi-entity combat updates; preserve the current single IMMEDIATE transaction for attack and HP synchronization.
- [ ] Review synchronization of HP, resources, conditions and encounter projections.
- [ ] Surface unsupported 2014 rules rather than silently improvising.
- [ ] Expand coverage for currently partial combat flows as rules are implemented.

## Migration status
The three service modules live in this package. The flat `services.combat_encounter_service`, `services.combat_attack_service` and `services.weapon_equipment_service` compatibility shims have been removed after migrating the remaining test consumers.
