# D&D 5e (2014) armor rules foundation

The armor catalogue is connected to campaign item definitions and equipped item instances. Player-character Armor Class is derived from the currently equipped body armor and optional shield when equipment is queried, an encounter is created, or a player character is targeted by an attack.

## Supported rules

- Unarmored AC: 10 + Dexterity modifier.
- Light armor: listed AC + full Dexterity modifier.
- Medium armor: listed AC + Dexterity modifier, maximum +2.
- Heavy armor: listed AC without Dexterity modifier.
- Shield: +2 AC, independent of body armor.
- Strength requirements and Stealth-disadvantage properties are returned as
  explicit derived flags for application-layer enforcement.

The catalogue includes padded, leather, studded leather, hide, chain shirt,
scale mail, breastplate, half plate, ring mail, chain mail, splint, plate and
shield.

## Deliberate boundary

Strength-based speed penalties, class-feature AC alternatives (such as Unarmored Defense), magic-item bonuses and immediate refresh of every active encounter snapshot after an equipment change remain out of scope. Attack resolution recalculates a player target's AC from current equipment and writes that value back into the encounter snapshot when the target is attacked. NPC armor remains represented by its stored creature AC. The rules engine remains deterministic and has no persistence or provider dependencies.\n\n## Armor proficiency\n\nCharacters store proficiency categories `light`, `medium`, `heavy` and `shields`. The equipment endpoint reports whether each equipped armor item is proficient, the unproficient item keys, whether Strength/Dexterity checks, saves and attacks should have disadvantage, and whether spellcasting is blocked. Combat weapon attacks using Strength or Dexterity apply that disadvantage. The current application does not yet expose spellcasting or general ability-check/save resolution hooks, so those reported flags are ready for those systems but do not claim to enforce unavailable actions. Characters with no declared armor proficiencies are treated as untrained; class names are not guessed or mapped automatically.


## Item integration

Item definitions may set `armor_key` to one of the catalogue keys. Body armor
uses the `body` equipment slot; shields use `off_hand`. The database rejects
hybrid weapon/armor definitions and mismatched armor slots. Physical ownership
continues to live on `item_instances.owner_id`; `equipped_items` remains the
campaign-scoped slot projection.
