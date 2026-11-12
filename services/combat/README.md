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

## Verified state ownership and effect projection

- `CharacterState` and `CreatureState` are canonical for player/NPC HP;
  encounter combatant HP is a projection synchronized inside the same
  `IMMEDIATE` transaction as canonical state.
- `PersistentEffect` owns persisted duration/status.
  `EffectiveConditionService` derives the live `ConditionSet`; it does not
  persist another copy.
- Attacks already use the live effect projection. PR #204 also applies that
  projection to movement speed/incapacitation and reaction eligibility using
  the same caller-owned combat transaction connection. A persistent effect
  can therefore constrain movement/reactions even when it was applied after
  the encounter snapshot was created.
- Campaign-clock advances and short/long rests expire campaign-time effects in
  the same write transaction as their clock/state changes.
- Equipment/creature metadata selects an immutable attack profile; numeric
  weapon/natural-attack mechanics remain in the pure rules engine.

## Remaining combat scope

The recommended order and indicative effort for expanding combat as part of a playable character/adventure slice are tracked in the [engineering readiness and gameplay roadmap](../../docs/architecture/engineering-readiness-and-gameplay-roadmap-2026-11-12.md).

- [ ] Add class-specific action/resource consumption only after class features
  and resources have typed canonical models.
- [ ] Add spell slots, ammunition and other expendable resources with explicit
  transactional owners before exposing them to combat.
- [ ] Surface unsupported 2014 rules rather than silently improvising.
- [ ] Add attacks/features only with deterministic rules-engine derivation and
  regression coverage.

Do not split `CombatEncounterService` only to reduce line count; preserve its
lifecycle until a distinct independently-owned transaction boundary exists.
## Migration status
The combat application modules live in this package. The flat `services.combat_encounter_service`, `services.combat_attack_service` and `services.weapon_equipment_service` compatibility shims have been removed after migrating the remaining test consumers.
