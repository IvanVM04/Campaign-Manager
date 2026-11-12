# Combat services

## Responsibility
Application orchestration for combat encounters, attacks and character equipment. Deterministic mechanics belong in `rules_engine/dnd5e_2014/`.

## Modules
- `combat_encounter_service.py` — campaign-scoped encounter lifecycle, initiative, turn progression and combatant projections.
- `combat_attack_service.py` — attack use-case orchestration and atomic persistence of encounter and canonical HP state.
- `attack_profile_resolver.py` — typed player/equipment and NPC melee/natural attack profile loading and normalization; reads through the attack transaction's connection.
- `rules_engine/dnd5e_2014/combat/hit_points.py` — deterministic HP/death-track transitions invoked by the combat use case.
- `weapon_equipment_service.py` — equipment queries/mutations and derived armor/attack profiles.

Combat state is in `models/`, persistence in `repositories/`, and ruleset mechanics in `rules_engine/dnd5e_2014/`.

## Dependency rules
- Delegate deterministic mechanics to the rules engine; the application resolver selects trusted character/equipment/NPC metadata and the rules engine derives only numeric profile mechanics.
- Do not move repositories, campaign metadata parsing or equipment lookup into `rules_engine`.
- Keep the rules engine independent of FastAPI, SQLite, LLM providers and service orchestration.
- Treat character state as canonical where encounter data is a projection.
- Resolve character/NPC profile selection in `AttackProfileResolver`; derive numerical weapon and natural-attack mechanics in `rules_engine`, never from LLM or API-provided bonuses.
- Parse NPC creature metadata at the trust boundary and fail closed on malformed or ambiguous profiles; preserve the legacy single-melee-profile read during migration.
- Merge encounter-supplied NPC weapons, natural attacks and defenses into one creature-state save within the encounter-creation transaction.
- Keep encounter, character/creature HP and effect updates within one explicit `IMMEDIATE` transaction per use case; `complete()` uses the same transaction helper as other encounter writes.
- Runtime composition and tests import the canonical `services.combat` package; former flat combat shims have been retired.

## Pending work
- [x] Move deterministic HP/death-track transitions out of CombatAttackService and into the rules engine (this PR).
- [x] Extract player/NPC weapon and natural-attack profile resolution into `AttackProfileResolver` with an immutable normalized result.
- [x] Derive NPC natural-attack ability/proficiency bonuses in the pure rules engine.
- [x] Merge encounter-supplied NPC profile and defense metadata in one creature-state save.
- [ ] Audit remaining duplicated mechanics that should be delegated to the rules engine.
- [x] Map and failure-inject encounter creation, death saves, turn/effect progression, completion, movement and reactions; canonical state and snapshots roll back together.
- [ ] Review synchronization of HP, resources, conditions and encounter projections.
- [ ] Surface unsupported 2014 rules rather than silently improvising.
- [ ] Expand coverage for currently partial combat flows as rules are implemented.
- [x] Cover player, NPC melee and NPC natural-attack profile resolution, malformed persisted metadata, active-turn selection, and NPC configuration persistence.

## Migration status
The combat application modules live in this package. The flat `services.combat_encounter_service`, `services.combat_attack_service` and `services.weapon_equipment_service` compatibility shims have been removed after migrating the remaining test consumers.
