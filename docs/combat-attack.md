# Weapon attack use case

The `POST /encounters/{encounter_id}/attack` endpoint resolves one weapon attack for the active persisted player character.

## Request

The client supplies only the target combatant, expected round/turn position, dice mode and tactical choices (finesse ability, versatile grip and whether the target is within 5 feet). It cannot supply attack bonus, damage bonus, weapon statistics, target AC or current HP.

Manual dice mode requires explicit d20 and damage dice results. For a miss, send an empty `manual_damage_rolls` list. Automatic mode uses the injected server dice roller.

## Resolution and persistence

The service loads the character's current ability scores and proficiencies, the equipped inventory instance and its SRD definition, and the encounter combatants. It derives the attack profile, resolves advantage/disadvantage from the stored conditions and delegates hit/critical/damage rules to the existing `resolve_attack()` engine.

A successful hit updates the encounter snapshot and, for a player-character target, the authoritative `character_states.current_hp` in the same SQLite transaction. A failure to write either side rolls back both. SQLite's immediate write transaction and expected round/turn check reject stale concurrent actions.

One attack action is consumed on either a hit or a miss. The next combatant's action is reset when their turn begins.

## Scope and known limitations

- Only persisted player characters can attack in this release. Manually entered NPCs can be targets, but cannot attack through this use case because they have no campaign entity/inventory association.
- One attack action per turn is enforced. Extra Attack / multiattack and bonus-action attacks are not yet modelled.
- Weapon special attacks (including nets and lances), ammunition consumption, off-hand attacks and complete hand-occupancy rules are not implemented. Ammunition weapons and special weapons are rejected rather than incorrectly resolved.
- The encounter model has no positions or distances yet. The caller supplies the within-5-feet tactical flag; weapon normal/long range cannot yet be validated.
- Target damage resistances, vulnerabilities and immunities are not persisted on combatants yet. The shared resolver remains responsible for applying a supplied `DamageAdjustment`, but this use case currently uses its neutral default.
- Death saves, concentration and condition application caused by attacks are outside this increment.
