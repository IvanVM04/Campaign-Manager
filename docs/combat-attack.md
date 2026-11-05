# Weapon attack use case

The `POST /encounters/{encounter_id}/attack` endpoint resolves one weapon attack for the active persisted player character.

## Request

The client supplies only the target combatant, expected round/turn position, dice mode and tactical choices (finesse ability, versatile grip and whether the target is within 5 feet). It cannot supply attack bonus, damage bonus, weapon statistics, target AC or current HP.

Manual dice mode requires explicit d20 and damage dice results. For a miss, send an empty `manual_damage_rolls` list. Automatic mode uses the injected server dice roller.

## Resolution and persistence

The service loads the character's current ability scores and proficiencies, the equipped inventory instance and its SRD definition, and the encounter combatants. It derives the attack profile, resolves advantage/disadvantage from the stored conditions and delegates hit/critical/damage rules to the existing `resolve_attack()` engine.

A successful hit updates the encounter snapshot and the target's authoritative mechanical record in the same SQLite transaction: `character_states.current_hp` for a PC or `creature_states.current_hp` for an NPC. A failure to write either side rolls back both. SQLite's immediate write transaction and expected round/turn check reject stale concurrent actions. A failure to write either side rolls back both. SQLite's immediate write transaction and expected round/turn check reject stale concurrent actions.

One attack action is consumed on either a hit or a miss. The next combatant's action is reset when their turn begins.

## Scope and known limitations

- Only persisted player characters can attack in this release. NPCs are now campaign entities with durable `CreatureState` records; manually supplied encounter participants create them, and later encounters can reuse them through `creature_id`. NPCs can be targets and their HP persists across encounters, but they cannot attack through this use case yet.
- One attack action per turn is enforced. Extra Attack / multiattack and bonus-action attacks are not yet modelled.
- Weapon special attacks (including nets and lances), ammunition consumption, off-hand attacks and complete hand-occupancy rules are not implemented. Ammunition weapons and special weapons are rejected rather than incorrectly resolved.
- The encounter model has no positions or distances yet. The caller supplies the within-5-feet tactical flag; weapon normal/long range cannot yet be validated.
- NPC damage resistances, vulnerabilities and immunities are stored in creature metadata and applied to weapon/natural attacks. Player-character damage defenses and spell/save damage are not yet integrated into this attack use case.
- Death saves, concentration and condition application caused by attacks are outside this increment.


## NPC damage defenses

When creating a manually supplied NPC participant, optionally provide `damage_resistances`, `damage_vulnerabilities`, and/or `damage_immunities` as lists of damage-type keys (for example `["fire", "cold"]`). The lists are validated, persisted with the campaign creature, and reused when that creature appears in later encounters. For an existing `creature_id`, supplying one of these fields updates only that defense list; omitted lists preserve the creature's saved value.

The normal and opportunity attack resolvers apply the target NPC's defenses to the attack's damage type. Immunity reduces damage to zero; resistance halves it (rounding down); vulnerability doubles it. If resistance and vulnerability both apply to the same damage type, they cancel. Immunity takes precedence. The response reports the three defense flags used for the damage instance. This increment does not yet apply these defenses to player characters, spells, or saving-throw damage.
