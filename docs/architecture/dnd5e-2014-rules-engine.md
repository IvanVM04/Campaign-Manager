# D&D 5e 2014 Rules Engine — Foundation

**Verified:** 2026-11-18  
**Rules baseline:** D&D 5e 2014 / System Reference Document 5.1. This is a bounded implementation subset, not a complete rules engine.

## Scope

The deterministic rules package is deliberately independent of FastAPI, SQLite, repositories and language-model provider adapters. The application layer supplies validated character/world data and chooses when a supported mechanics decision is required.

The current implementation includes:

- Generic dice rolls and d20 rolls.
- Advantage and disadvantage.
- Ability score modifiers.
- Character proficiency bonus by level.
- Ability checks and skill checks, including proficiency and expertise.
- Saving throws, including saving-throw proficiency.
- Weapon attack profiles: finesse, ranged/melee ability selection, weapon proficiency and versatile damage dice.
- Natural-attack profiles: Strength/Dexterity modifier, optional proficiency bonus and validated damage dice.
- A bounded combat slice: initiative, attacks, damage, defenses, HP/death-track transitions, selected conditions, movement/reactions, death saves and encounter state.
- Character short/long rests, Hit Dice and campaign-time effect expiry in application services using deterministic rules helpers.

It does not implement all character creation/progression, multiclass features, complete spellcasting, all class resources, all conditions, the full action economy or every 2014 rule.

## Rule references and determinism

The implementation follows the 2014 rules baseline as presented in SRD 5.1:

- Ability checks: d20 + relevant ability modifier, plus proficiency when an applicable proficiency applies; success at or above the DC.
- Saving throws: d20 + relevant ability modifier, plus proficiency when applicable.
- Advantage/disadvantage: roll two d20s and use the higher/lower result. If both apply, they cancel.
- Proficiency bonus by character level: +2 at levels 1–4, +3 at 5–8, +4 at 9–12, +5 at 13–16 and +6 at 17–20.
- Expertise doubles proficiency for eligible checks; this foundation does not apply it to saving throws.

Primary SRD reference:
https://media.wizards.com/2023/downloads/dnd/SRD_CC_v5.1.pdf

Readable reference:
https://www.dndbeyond.com/sources/dnd/basic-rules-2014/using-ability-scores

`DiceRoller` accepts an injected random source. Tests use deterministic sources; production automatic rolls use the backend's `random.SystemRandom` source. Mechanics results preserve faces, selected die, roll mode, modifiers, total, DC and outcome. Narrative must not recalculate or override them.

## Adjudication boundary

The structured `MechanicsAdjudicator` decides whether the current actionable intent requires a supported check and proposes the check/ability/skill/DC within its validated contract. It does not roll dice or mutate world state. The backend resolves the accepted decision using the rules engine and trusted character data.

The current adjudicator may propose a DC; the rules engine does not independently decide whether a check is warranted or choose a DC. Rule-backed DC guidance, tool checks, contested checks and richer action adjudication remain future improvements. Invalid or unsupported model output fails closed.

## Current dice modes and durable challenges

Native `POST /turn` and the SillyTavern resolve flow accept `dice_mode="automatic"` (default) or `dice_mode="manual"`.

- **Automatic:** the backend generates random values and applies the same deterministic rules calculations. The LLM may request or narrate the roll but cannot choose the result.
- **Manual:** when a supported d20 check is needed, the turn pauses with a pending challenge. The player supplies one d20 result, or two for advantage/disadvantage. The backend validates integer values from 1 to 20 and the expected count, then calculates the final result from the stored adjudication.
- The original ability/skill, DC, modifier and advantage/disadvantage state are retained. The submission does not let the player or LLM alter those values.
- Pending roll challenge details and accepted results are persisted in the durable turn-resolution record. SillyTavern exposes a manual-roll state GET endpoint so the extension can recover after a browser/extension restart. Re-submitting the same accepted result is idempotent; different results for the same challenge are rejected.
- Manual player-entered faces are not cryptographic proof that physical dice were rolled. This is honest input plus rules validation, not anti-cheat verification.

The current policy is a turn-level automatic/manual choice, not the future fine-grained policy by campaign, actor and check category requested in product requirements v0.2. Standalone `POST /dice/roll` is a dice-tray operation and does not create a turn or mutate campaign state.

## Combat rules and encounter state (2014)

The combat package owns deterministic application workflows and calls pure rules functions. Canonical character/creature state remains authoritative for HP; encounter combatants are synchronized projections.

Current supported behavior includes:

- Initiative and explicit tie handling.
- Attack rolls against supplied AC; natural 1 misses and natural 20 hits critically.
- Critical hits double damage dice, not flat modifiers.
- SRD damage types with immunity, resistance and vulnerability; resistance and vulnerability to the same instance cancel.
- Encounter preparation/active/completed state, initiative order, round and active combatant.
- Typed conditions and 2014 exhaustion effects used by supported attack/movement/reaction rules.
- Persisted encounter state, manual/automatic attacks, player/NPC weapon and natural-attack profiles, damage defenses, HP/death track, death saves, grid movement and opportunity attacks.
- Persistent effect projection is shared with movement/reaction validation; clock/rest operations expire time-based effects in their transaction.

This is not the complete 2014 combat loop. Multiattack, all bonus/action features, cover/range rules breadth, ammunition/loading, special weapon rules, concentration and spell effects remain incomplete.

## Boundaries and future rules modules

- The active ruleset is explicitly `dnd5e_2014`; 2024 rules are not mixed into it.
- The rules engine does not import services, persistence, HTTP or provider clients.
- The engine only calculates implemented mechanics from trusted inputs; it does not grant proficiency or invent missing statistics.
- D&D 5e 2014 is the default included rules package. Importable custom rules modules are an approved product requirement but are **not implemented**. Their format should first be declarative, versioned, dependency-aware and validated; arbitrary executable plugin code must not bypass the backend's rule/permission boundary.
- D&D 2024 and other rulesets are future/non-priority work and must remain isolated as separate rulesets.

No rule content beyond the SRD-compatible mechanics above is copied into this project.
