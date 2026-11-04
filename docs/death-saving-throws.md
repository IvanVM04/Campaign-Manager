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

## Integration boundary

This increment implements and tests the rules calculation only. Encounter persistence, death-save counters, automatic saves at the start of a turn, damage received while at 0 hit points, and stabilization/revival workflows are not yet connected to the combat API. Callers must not treat this primitive alone as a complete death-and-dying workflow.
