# Combat and character-state audit — 2026-11-12

**Scope:** local single-player D&D 5e (2014) vertical slice. This audit covers
persisted state ownership and the implementation in the character-rest /
combat-consistency PR. It is not a claim of complete 5e rules coverage.

## Canonical state and projections

| State | Canonical owner | Derived/projection | Transaction owner |
|---|---|---|---|
| Player-character HP | `CharacterState.current_hp` | Encounter `CombatantState.current_hp`, character sheet | Attack/death-save/rest application use case |
| NPC HP | `CreatureState.current_hp` | Encounter `CombatantState.current_hp` | Combat attack/encounter application use case |
| Hit Dice | `CharacterState.hit_die_sides`, `hit_dice_used` | Sheet availability = level minus used | Character rest use case |
| Active conditions/exhaustion | `PersistentEffect` rows | `EffectiveConditionService` creates a `ConditionSet` overlay | Caller-owned combat/clock/rest transaction |
| Encounter turn/position/action/reaction | `CombatEncounterState` snapshot | Encounter API response | `CombatEncounterService` mutation |
| Fictional campaign time | `CampaignClock` | Clock API response | `CampaignClockService` or character rest use case |
| Timed campaign effects | `PersistentEffect` + timer rows | Active/expired status | Campaign clock/rest transaction |
| Generic resources | World `Resource` and `ResourceBalance` | World inventory/resource views | World resource application |
| Spell slots/class features | Not yet modelled | None | Deferred; do not simulate as generic resource balances |

A persisted effect is not a second character-condition state. It remains the
source of truth; a consumer projects its currently active mechanical effect
onto encounter conditions. Narrative effects remain non-mechanical and must
not become condition modifiers by naming convention.

## Audit finding corrected: stale encounter conditions

Combat attacks already queried active persistent effects through
`EffectiveConditionService` on the attack transaction connection.
Movement and reaction eligibility previously relied only on the condition set
captured in the encounter snapshot at creation time. An incapacitating effect
applied later could therefore fail to block movement/reactions, and a newly
applied exhaustion effect could fail to reduce movement speed.

The encounter service now overlays active effects inside the same
`IMMEDIATE` transaction used by movement/reaction validation and persistence.
The base snapshot conditions are preserved and active persistent effects are
added for that decision. Regression tests cover incapacitation and exhaustion
level 2. There is no second write to the encounter snapshot merely to mirror
the effect.

## HP and encounter rollback

Player HP remains canonical in `CharacterState`; NPC HP remains canonical in
`CreatureState`. An encounter combatant's HP is a combat projection. Combat
attack and death-save use cases update canonical HP and the encounter
projection in one caller-owned transaction. PR #202 failure-injection tests
cover creation/start, death-save synchronization, turn/effect progression,
completion, movement and reaction rollback.

The rest use case does not update encounter HP snapshots: rests are rejected
while any encounter in the campaign is active. Outside combat, it changes only
the canonical character row.

## Hit Dice and rests added in migration 030

- The pure rules helper maps the 2014 core classes to d6/d8/d10/d12. Class
  names are still free text and multiclass levels are not represented, so
  unrecognised/multiclass labels use a documented d8 fallback. This is a safe
  compatibility default, not class validation.
- Migration 030 backfills the die size for existing characters and adds used
  Hit Dice plus the campaign-time marker for the previous long-rest start.
- A short rest advances fictional time by 60 minutes. A character can spend
  available Hit Dice; each die heals `max(0, roll + Constitution modifier)`,
  capped at maximum HP. Dice can be rolled locally or supplied manually.
- A long rest advances fictional time by 480 minutes, restores HP to maximum
  and recovers up to half the character's total Hit Dice (minimum one, never
  more than previously spent). A character cannot benefit from another long
  rest until 24 campaign hours have elapsed since the prior rest started.
- Both rest workflows compare the caller's expected campaign-clock value,
  reject a campaign with an active encounter and atomically persist character
  state, clock advancement and campaign-time effect expiry in one
  `IMMEDIATE` transaction. Failure injection covers rollback of clock/effect
  expiry when the character-state write fails.
- The rules slice assumes the rest is uninterrupted. It does not yet track
  strenuous activity interruption or class/race feature-based rest benefits.

## What is deliberately not implemented

1. Spell slots, pact magic, Ki/focus points, rage uses, superiority dice,
   channel divinity, wild shape and other class/subclass resources.
2. Race/background, typed class progression, multiclassing, spell lists,
   prepared/known spells, features, feats, XP/level-up or automatic HP/AC
   progression.
3. Ammunition tracking, weapon charges and feature-specific attack economies.
4. Rest interruption, watch/encounter risk during a long rest, food/water
   requirements, exhaustion recovery from long rests and feature-specific
   recovery exceptions.

Those mechanics must be introduced with typed canonical state, explicit
rules-engine recovery functions and transaction tests. World
`ResourceBalance` remains suitable for campaign quantities such as gold or
supplies, not as a substitute for character spell slots or class resources.

## Next implementation boundary

The first character-resource foundation is Hit Dice. The next vertical slice
should introduce one selected class's typed progression (including features
and resource refresh), then derive its sheet/attack display from the same
persisted data used by deterministic mechanics. Do not build a universal
resource counter before those class contracts are chosen.
