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

The encounter API exposes `POST /encounters/{encounter_id}/death-save`. It resolves one save for the active persisted player character when that character has 0 HP. The request must include the expected round and turn index; callers may use automatic dice or provide one manual d20 result.

Successes, failures, stabilization, and death are stored in the encounter's existing combatant snapshot JSON, so no schema migration is needed. A natural 20 restores 1 HP in both the character record and encounter snapshot in one transaction, and clears the saved death-save counters. Stable and dead combatants cannot make further saves through this endpoint.

This increment does not yet automate the save at turn start or handle damage dealt to a combatant already at 0 HP. NPC/monster death-at-zero behaviour remains unchanged.
