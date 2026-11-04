# Death saving throws — D&D 5e (2014)

The rules engine exposes `resolve_death_saving_throw()` as a deterministic primitive for a creature making one death saving throw while at 0 hit points.

## Rules implemented

- The save is an unmodified d20 roll: no ability modifier or proficiency bonus.
- A result of 10 or higher adds one success.
- A result below 10 adds one failure.
- A natural 1 adds two failures.
- A natural 20 restores 1 hit point; it does not add a death-save success.
- Three successes stabilize the creature.
- Three failures mean the creature dies.

The resolver accepts an injected `DiceRoller`, so production code can use automatic dice while tests and manual workflows can provide reproducible d20 results.

## Encounter integration

The encounter API resolves one death save automatically when initiative advances to the turn of an unstable player character at 0 HP. The advance response includes the roll and resulting track under `turn_start_death_save`. The explicit `POST /encounters/{encounter_id}/death-save` endpoint remains available for manual workflows, and the same turn-position guard prevents a second save in that turn.

Successes, failures, stabilization, and death are stored in the encounter's existing combatant snapshot JSON, so no schema migration is needed. A natural 20 restores 1 HP in both the character record and encounter snapshot in one transaction, and clears the saved death-save counters. Stable and dead combatants cannot make further saves through this endpoint.

Automatic turn-start saves apply to persisted player characters only. NPC/monster death-save automation remains outside this increment.


## Damage while at 0 hit points

Weapon damage can now target an unconscious combatant at 0 HP. Each damaging hit causes one failed death save; a critical hit causes two. The failure track is capped at three, which marks the combatant dead. Damage also ends stabilization; the saved success track is cleared so death saves can begin again.

When damage reduces a combatant from positive HP to 0, the combatant becomes unconscious and its death-save track starts at zero. Massive damage kills outright when the damage remaining after reducing the target to 0 HP equals or exceeds its hit point maximum.

These transitions are persisted with the encounter snapshot and the underlying character/creature HP in the same transaction. NPC death-save automation and automatic saves at the start of a turn remain separate follow-up work.


## Automatic turn-start resolution

When initiative advances to an unstable player character at 0 HP, the encounter service rolls one unmodified d20 and persists the result in the same transaction as the turn change. A natural 20 restores 1 HP in both the character record and encounter snapshot. A stable or dead combatant does not roll. The response includes the roll details so the client can present the result without issuing a second request.
