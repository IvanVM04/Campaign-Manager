# D&D 5e 2014 Rules Engine — Foundation

## Scope

This module implements a deterministic subset of the 2014 fifth-edition rules.
It is deliberately independent of FastAPI, SQLite, repositories, character
persistence and language-model providers.

The first supported mechanics are:

- Generic dice rolls and d20 rolls.
- Advantage and disadvantage.
- Ability score modifiers.
- Character proficiency bonus by level.
- Generic ability checks and skill checks, including proficiency and expertise.
- Saving throws, including saving-throw proficiency.

This is not yet a complete character sheet, combat engine, attack resolver,
spell system or character progression system.

## Rule references

The implementation follows the 2014 rules baseline as presented in the
System Reference Document 5.1:

- Ability checks: d20 + relevant ability modifier, plus proficiency when an
  applicable skill/tool proficiency applies; success when the total equals
  or exceeds the DC.
- Saving throws: d20 + the relevant ability modifier, plus proficiency when
  the character is proficient in that saving throw.
- Advantage/disadvantage: roll two d20s and use the higher/lower result.
  If both apply, they cancel and only one d20 is rolled.
- Proficiency bonus by character level: +2 at levels 1–4, +3 at 5–8,
  +4 at 9–12, +5 at 13–16 and +6 at 17–20.
- Expertise doubles proficiency for eligible ability checks. It is not
  applied by this foundation to saving throws.

Primary SRD reference:
https://media.wizards.com/2023/downloads/dnd/SRD_CC_v5.1.pdf

Readable rule references:
https://www.dndbeyond.com/sources/dnd/basic-rules-2014/using-ability-scores

## Determinism and auditability

DiceRoller accepts a random source through its constructor. Tests inject a
sequence source, so the exact dice faces and all derived results are repeatable.
Production use defaults to random.SystemRandom.

CheckResult preserves the ability, raw d20 faces, selected face, roll mode,
ability modifier, proficiency applied, situational modifier, total, DC and
success state. Narrative code should describe these results; it must not
recalculate or override them.

## Turn adjudication integration

The campaign runtime now wires a structured `MechanicsAdjudicator` before
narration. It may request no check, ask the player for clarification, or
propose an ability check, skill check or saving throw. Its JSON response is
strictly validated; unknown fields, unsupported skills/abilities and
out-of-range DCs/modifiers are rejected.

The adjudicator does not roll dice. The application resolves accepted checks
through `DiceRoller` and the character-aware rules functions, then passes the
immutable result (faces, selected die, modifier, total, DC and outcome) to
`DMService` as authoritative context. A clarification stops the turn before
narration, extraction or world mutation. The turn API also returns a structured
`mechanics` object for clients.

The LLM still proposes the DC and identifies the relevant test. This is a
deliberate first integration boundary, not a claim that adjudication is fully
deterministic. Future work should add rule-backed DC guidance, tool checks,
contested checks and richer action adjudication. Until then, invalid or
ambiguous model output fails closed instead of silently continuing.

## Boundaries

- The ruleset is explicitly dnd5e_2014.
- No 2024 rule text or mechanics are included.
- The deterministic rules engine does not decide whether a check is warranted or choose a DC. The application adjudicator proposes these; the rules engine only resolves the accepted test.
- The rules engine does not invent proficiency. Callers must supply whether a
  character is proficient for the specific check or save.
- Character-aware ability checks, skill checks and saving throws now read CharacterState; broader character mechanics remain future work.
- No rule content beyond the SRD-compatible mechanics above is copied into
  this project.
