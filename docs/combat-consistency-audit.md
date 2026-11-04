# Combat consistency audit

**Baseline:** merge commit `1ed47b1fd71323a9e06d641aca052cca24e4337e` (PR #48).

**Scope reviewed:** encounter lifecycle and initiative progression, combatant snapshots, weapon attack resolution, hit-point/death-save transitions, encounter persistence, and the public combat API.

## Findings

### High — the first active turn does not trigger its automatic death save

The turn-start death-save hook is called from `advance_turn_with_events()` only. `start()` sets the encounter to round 1 / turn index 0 and persists it without resolving the active combatant's start-of-turn effects.

Consequently, a player character already at 0 HP and unstable when an encounter starts does not make a death saving throw on their first turn. They only roll after initiative cycles back to them. This makes the first turn behave differently from every subsequent turn.

**Recommended correction:** run the same turn-start resolver after initiative is established in `start()`, in the same database transaction as the encounter start, and expose the result in the start response as `turn_start_death_save`. Preserve the current manual endpoint for compatibility, while ensuring it cannot cause a second save in the same round/turn.

**Regression coverage required:**
- Downed PC is first in initiative: one save is resolved as part of starting the encounter.
- Downed PC is not first: no save is resolved until their first turn is reached.
- Natural 20 updates both the character row and encounter snapshot atomically.
- Natural 1 applies two failures; three failures mark the combatant dead.
- A manual request cannot produce a second save in the same turn.
- Healthy PCs and NPCs do not produce a death-save event.

### Medium — turn-start death-save behavior is split across two service paths

The explicit `death_saving_throw()` and automatic `_resolve_turn_start_death_save()` paths duplicate the state transition and HP synchronization logic. They currently implement the same rules, but future changes can drift.

**Recommended correction:** extract a single private resolver that accepts the combatant, dice input, and transaction connection, and have both entry points call it. Keep endpoint-specific validation outside the shared transition.

### Medium — encounter snapshots are authoritative for combat state but only partially constrained

`CombatantState` validates the death-save counter ranges and prevents simultaneous `stable` and `dead` flags. It does not fully validate cross-field combinations such as a stable or dead combatant being conscious, or a stable combatant having fewer than three successes. Invalid combinations could therefore be loaded from or written to persisted snapshots if introduced by a future service path.

**Recommended correction:** define and test the valid cross-field invariants before adding more combat states. Avoid retroactively rejecting legacy snapshots without a compatibility/migration strategy.

## Areas checked

- Encounter start, turn advancement, completion, and expected-position checks.
- Initiative ordering and round rollover.
- Atomic encounter snapshot writes and character HP synchronization for natural-20 recovery.
- Weapon damage against standing, unconscious, stable, and dead targets.
- Death-save counters, stabilization, death, and massive-damage handling.
- Campaign scoping of encounter and character/creature persistence.

## Follow-up sequence

1. Fix first-turn automatic death-save resolution and add regression tests.
2. Consolidate manual and automatic death-save state transitions.
3. Add cross-field combatant invariants with legacy-snapshot compatibility tests.
4. Continue with action/reaction economy only after this audit's high-priority finding is closed.

This document records implementation findings, not a claim that every D&D 5e combat rule is implemented. Movement, reactions, opportunity attacks, spell damage, saving-throw damage, and broader condition/action interactions remain outside the reviewed weapon-attack path.
