# Combat attack-profile boundary

## Purpose

Keep the attack use case responsible for validation, dice resolution and one atomic write, while isolating the data-dependent choice of the attacker's weapon or natural attack. The resolver is application code; numerical 2014 mechanics remain in the pure rules engine.

## Resolution flow

```text
CombatAttackService (owns IMMEDIATE transaction)
  -> AttackProfileResolver
      -> Player: CharacterState + equipped main-hand weapon
      -> NPC: campaign CreatureState + configured melee/natural profiles
      -> ResolvedCombatAttackProfile (immutable normalized value)
  -> rules_engine weapon/natural derivation
  -> conditions, target defenses and dice
  -> HP/death transition
  -> canonical character/creature HP + encounter snapshot save
```

The resolver receives the caller-owned SQLite connection and never opens a transaction, writes a repository, rolls dice or mutates an encounter. The attack service remains the transaction coordinator.

## Selection and compatibility rules

- Player characters must have a persisted CharacterState and equipped main-hand weapon. Their attack ability/proficiency is derived from that canonical state and the weapon definition.
- Player requests cannot select NPC-only weapon or natural-attack keys.
- NPC melee profiles are read from `metadata.npc_melee_attacks`; the first profile remains the default, while `npc_attack_weapon_key` selects a configured alternative.
- The former `metadata.npc_melee_attack` object remains a read fallback when the list is missing or empty. New encounter writes store the list and continue to populate the first-profile field during the compatibility window.
- NPC natural profiles are read from `metadata.npc_natural_attacks`. Explicit natural keys take precedence when supplied; otherwise the first natural profile is the default only when no melee weapon profile is configured.
- A malformed list, duplicate key, unsupported damage expression/type, invalid reach, or invalid proficiency flag fails closed. Persisted metadata is validated at runtime rather than trusted merely because a previous API request may once have validated it.
- Weapon-only options (finesse choice and versatile two-handed damage) are not accepted for natural attacks.

## Persistence boundary

Encounter creation combines supplied NPC melee profiles, natural profiles and damage defenses into one creature-state save inside its existing `IMMEDIATE` transaction. For an already-persisted creature, omitted configuration preserves existing metadata. For a newly created manual NPC, entity creation and the single creature-state insert/save remain part of the same transaction; a failure rolls back the encounter and campaign creature together.

Attack resolution updates the target's canonical character/creature HP and the encounter combatant snapshot in the same attack transaction. The resolver does not participate in these writes.

## Regression coverage

- Resolver unit tests cover player equipment, finesse/versatile derivation, NPC weapon selection, legacy metadata, natural-attack selection, proficiency, malformed profiles and HP snapshot drift.
- Rules-engine tests cover deterministic natural-attack ability/proficiency calculations.
- API tests cover NPC active-turn attacks with selected melee and natural profiles, HP synchronization, fail-closed metadata and single-write NPC configuration persistence.
- Existing attack/opportunity-attack tests continue to guard reaction use, expected turn position, damage defenses, downed/dead targets and transaction rollback.
